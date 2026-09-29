"""Single-control-thread admission of asynchronous plans against actual history.

This object returns proposals, never dispatches or acknowledges execution. A
runtime caller must use the bound ledger and its trusted physics adapter. Wall
age and measured-state gates are initial engineering limits, not stability proofs.
"""
from dataclasses import dataclass
import math
import threading
import time

import numpy as np

from koopman.bounded_feedback_v46 import BoundedFeedback
from koopman.bounded_mpc_v44 import COMMAND_ATOL, owned
from koopman.control_objective_v44 import control_mask, tracking_terms
from koopman.execution_ledger_v48 import ExecutionCapture, ExecutionLedger
from koopman.recovery_solver_v50 import PlanningRequest, request_binding


@dataclass(frozen=True)
class AdmissionConfig:
    horizon: int = 20
    prefix_controls: int = 8
    reply_timeout_s: float = .1
    maximum_plan_age_s: float = .35
    depth_deviation_m: float = .02
    attitude_deviation_rad: float = .02
    linear_velocity_deviation_m_s: float = .02
    angular_velocity_deviation_rad_s: float = .05

    def __post_init__(self):
        if (type(self.horizon) is not int or type(self.prefix_controls) is not int
                or not 1<=self.prefix_controls<self.horizon<=128):
            raise ValueError('admission_horizon')
        for key,value in vars(self).items():
            if key not in ('horizon','prefix_controls') and (isinstance(value,bool)
                    or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0):
                raise ValueError('admission_limits')
        if self.reply_timeout_s>=self.prefix_controls/60 or self.maximum_plan_age_s<self.horizon/60:
            raise ValueError('admission_timing')


def _same_identity(a,b):
    fields=('execution_id','episode_id','reset_id','worker_generation','reference_id','reference_revision',
            'configuration','context_key','model_id','support_id')
    return (all(getattr(a,k)==getattr(b,k) for k in fields)
            and BoundedFeedback._same_pose_values(a.reference,b.reference,1e-12))


class PlanArbiter:
    def __init__(self,ledger,*,config=AdmissionConfig(),clock=time.perf_counter):
        if not isinstance(ledger,ExecutionLedger) or not isinstance(config,AdmissionConfig) or not callable(clock):
            raise ValueError('arbiter_setup')
        self.ledger=ledger;self.config=config;self.clock=clock
        self._owner=threading.get_ident();self._pending=None;self._active=None
        self.last_reason=None

    def _owner_check(self):
        if threading.get_ident()!=self._owner:raise RuntimeError('arbiter_control_thread_required')

    @property
    def pending(self):return self._pending is not None

    @property
    def active(self):return self._active is not None

    def invalidate(self,reason):
        self._owner_check();self._pending=None;self._active=None;self.last_reason=str(reason)

    def _capture_is_current(self,capture):
        with self.ledger._guard():
            self.ledger._binding_check()
            return (capture is self.ledger._capture and capture is not None
                    and capture.physics_index==self.ledger._live.physics_index
                    and capture.history_digest==self.ledger._digest and self.ledger._pending is None)

    def register(self,request,receipt,*,prefix_source='fallback'):
        self._owner_check()
        if self._pending is not None:raise ValueError('arbiter_request_pending')
        if prefix_source not in ('fallback','mpc'):raise ValueError('arbiter_prefix_source')
        if not isinstance(request,PlanningRequest):raise ValueError('arbiter_request')
        if (not isinstance(receipt,dict) or receipt.get('status')!='accepted'
                or receipt.get('request_id')!=request.request_id
                or any(not isinstance(receipt.get(k),str) or not receipt[k] for k in ('generation','key'))):
            raise ValueError('arbiter_submission_receipt')
        c=request.capture
        with self.ledger._guard():
            self.ledger._binding_check();current=self.ledger._capture
            if (current is None or not _same_identity(c,current) or c.physics_index!=current.physics_index
                    or c.history_digest!=current.history_digest or c.previous is None
                    or not BoundedFeedback._same_pose_values(c.state,current.state,1e-12)
                    or not np.array_equal(c.previous,current.previous)
                    or c.origin.origin_control!=current.origin.origin_control
                    or c.origin._actuator.elapsed_time!=current.origin._actuator.elapsed_time
                    or not np.array_equal(c.origin._actuator.current(),current.origin._actuator.current())
                    or self.ledger._pending is not None or len(request.prefix)!=self.config.prefix_controls):
                raise ValueError('arbiter_capture_binding')
            prior=c.previous
            for u in request.prefix:prior=self.ledger._checked_command(u,prior)
        # Own the request's captured state/history and the explicit prefix.
        own=PlanningRequest(request.request_id,request.capture,request.prefix)
        self._pending=dict(request=own,receipt=dict(receipt),registered=self.clock(),plan=None,prefix_source=prefix_source)
        self.last_reason=None

    def ingest(self,event):
        self._owner_check();pending=self._pending
        def reject(reason):
            self.invalidate(reason);return dict(status='rejected',reason=reason)
        if pending is None:return dict(status='rejected',reason='no_registered_request')
        if not isinstance(event,dict):return reject('reply_not_mapping')
        if any(event.get(k)!=pending['receipt'][k] for k in ('generation','key','request_id')):
            return reject('reply_transport_binding')
        elapsed=event.get('elapsed_ms');age=self.clock()-pending['registered']
        if (not isinstance(elapsed,(int,float)) or isinstance(elapsed,bool) or not np.isfinite(elapsed)
                or elapsed<0 or elapsed>1000*self.config.reply_timeout_s
                or age<0 or age>=self.config.reply_timeout_s):
            return reject('reply_late_or_invalid_clock')
        if event.get('status')!='result':return reject('worker_no_result')
        p=event.get('payload');request=pending['request'];c=request.capture
        if not isinstance(p,dict) or p.get('binding')!=request_binding(request):return reject('reply_request_binding')
        if (p.get('status') not in ('selected','baseline') or p.get('runtime_eligible') is not False
                or p.get('actual_history_advanced') is not False):return reject('worker_no_admissible_plan')
        try:
            meta=p['metadata']
            expected=dict(episode_id=c.episode_id,reference_id=c.reference_id,request_id=request.request_id,
                configuration=c.configuration,context_key=list(c.context_key),model_id=c.model_id,
                support_id=c.support_id,origin_control=c.physics_index//2,history_physics_index=c.physics_index,
                committed_prefix=self.config.prefix_controls)
            if any(meta.get(k)!=value for k,value in expected.items()):return reject('reply_solver_metadata')
            if (not np.array_equal(meta['previous_command'],c.previous)
                    or not BoundedFeedback._same_pose_values(meta['reference'],c.reference,1e-12)):
                return reject('reply_solver_origin_values')
            u=np.asarray(p['commands'],dtype=float);x=np.asarray(p['predictions'],dtype=float)
            if (u.shape!=(self.config.horizon,4) or x.shape!=(2*self.config.horizon,11)
                    or not np.isfinite(u).all() or not np.isfinite(x).all()):return reject('reply_plan_shape')
            if not np.array_equal(u[:self.config.prefix_controls].astype(np.float32),request.prefix):
                return reject('reply_prefix_changed')
            if self.ledger._domain.check_states(x):return reject('reply_predicted_state_rejected')
            prior=c.previous
            for command in u:prior=self.ledger._checked_command(command,prior)
            if self.clock()-pending['registered']>=self.config.reply_timeout_s:
                return reject('reply_validation_timeout')
            # No nested packet aliases survive admission. Worker diagnostics are
            # not needed on the control path and remain in the external log.
            pending['plan']=dict(commands=owned(u,np.float32),predictions=owned(x))
            return dict(status='staged',reason=None,activation_control=c.physics_index//2+self.config.prefix_controls)
        except (KeyError,ValueError,TypeError,IndexError,FloatingPointError) as exc:
            return reject('reply_invalid:'+str(exc))

    def _state_matches(self,current,expected):
        cfg=self.config
        terms=tracking_terms(current.state[None],expected[:5],control_mask(current.configuration))
        return bool(terms['depth'][0]<=cfg.depth_deviation_m**2
            and terms['attitude'][0]<=cfg.attitude_deviation_rad**2
            and np.max(np.abs(current.state[5:8]-expected[5:8]))<=cfg.linear_velocity_deviation_m_s
            and np.max(np.abs(current.state[8:]-expected[8:]))<=cfg.angular_velocity_deviation_rad_s)

    def _validate_running(self,capture,registered,commands,predictions):
        c=registered['request'].capture;offset=capture.physics_index//2-c.physics_index//2
        age=self.clock()-registered['registered']
        if not _same_identity(capture,c):return 'plan_binding_changed',offset
        if age<0 or age>self.config.maximum_plan_age_s:return 'plan_wall_age',offset
        if offset<0 or offset>=self.config.horizon:return 'plan_index_expired',offset
        if offset==0 and capture.history_digest!=c.history_digest:return 'origin_history_changed',offset
        try:
            actual=self.ledger.acknowledged_commands(c.physics_index//2,capture.physics_index//2)
        except ValueError:return 'plan_history_unavailable',offset
        if len(commands)<offset or not np.allclose(actual,commands[:offset],rtol=0,atol=COMMAND_ATOL):
            return 'actual_prefix_changed',offset
        expected=c.state if offset==0 or predictions is None else predictions[2*offset-1]
        if not self._state_matches(capture,expected):return 'plan_state_deviation',offset
        return None,offset

    def choose(self,capture):
        self._owner_check()
        activated=False
        def fallback(reason):
            self.invalidate(reason)
            return dict(status='fallback',command=None,source=None,reason=reason,actual_history_advanced=False)
        try:
            if not isinstance(capture,ExecutionCapture) or not self._capture_is_current(capture):
                return fallback('capture_not_current')
            if self._pending is not None:
                pending=self._pending;plan=pending['plan'];prefix=pending['request'].prefix
                check_commands=prefix if plan is None else plan['commands']
                predictions=None if plan is None else plan['predictions']
                reason,offset=self._validate_running(capture,pending,check_commands,predictions)
                if reason:return fallback(reason)
                if offset<self.config.prefix_controls:
                    command=self.ledger._checked_command(prefix[offset],capture.previous)
                    return dict(status='proposal',source='committed_prefix',command=command,
                        plan_index=offset,reason=None,actual_history_advanced=False,activated=False,
                        prefix_source=pending['prefix_source'])
                if offset!=self.config.prefix_controls:return fallback('activation_missed')
                if plan is None:return fallback('activation_without_result')
                self._active=pending;self._pending=None
                activated=True
            if self._active is None:return fallback(self.last_reason or 'no_plan')
            registered=self._active;plan=registered['plan']
            reason,offset=self._validate_running(capture,registered,plan['commands'],plan['predictions'])
            if reason:return fallback(reason)
            if offset<self.config.prefix_controls:return fallback('active_before_activation')
            command=self.ledger._checked_command(plan['commands'][offset],capture.previous)
            return dict(status='proposal',source='mpc',command=command,plan_index=offset,
                        reason=None,actual_history_advanced=False,activated=activated)
        except (ValueError,RuntimeError,IndexError,TypeError,FloatingPointError) as exc:
            return fallback('plan_validation_failed:'+str(exc))

    def following_prefix(self,capture):
        """Use only still-valid, explicitly known commands from an active plan."""
        self._owner_check()
        if self._pending is not None or self._active is None or not self._capture_is_current(capture):return None
        plan=self._active['plan']
        reason,offset=self._validate_running(capture,self._active,plan['commands'],plan['predictions'])
        if reason or offset+self.config.prefix_controls>self.config.horizon:return None
        return owned(plan['commands'][offset:offset+self.config.prefix_controls],np.float32)
