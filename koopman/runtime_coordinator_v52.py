"""Bounded control computation, explicit dispatch and actual substep receipts.

Worker preparation/closure and simulator execution remain outside this class.
Safety observations must come from the real adapter: constructing them is not
proof of contact sensing or geometry. Unit fixtures are not physics evidence.
"""
from dataclasses import dataclass
import math
import time
import uuid

import numpy as np

from koopman.bounded_mpc_v44 import owned
from koopman.control_objective_v44 import control_mask,tracking_terms
from koopman.plan_arbiter_v52 import PlanArbiter,AdmissionConfig
from koopman.recovery_solver_v50 import PlanningRequest


@dataclass(frozen=True)
class RuntimeConfig:
    control_compute_budget_s: float = 1/60
    maximum_xy_displacement_m: float = 2.
    minimum_clearance_m: float = .1
    depth_tracking_band_m: float = .05
    attitude_tracking_band_rad: float = .05
    minimum_improvement_fraction: float = .05
    no_improvement_controls: int = 60
    zero_progress_controls: int = 30

    def __post_init__(self):
        for key,value in vars(self).items():
            if key.endswith('_controls'):
                if type(value) is not int or not 1<=value<=600:raise ValueError('runtime_progress_limit')
            elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
                raise ValueError('runtime_limits')
        if self.minimum_improvement_fraction>=1:raise ValueError('runtime_improvement_fraction')


@dataclass(frozen=True)
class SafetyObservation:
    episode_id: str
    reset_id: str
    physics_index: int
    xy_displacement_m: np.ndarray
    minimum_clearance_m: float
    contact_observed: bool

    def __post_init__(self):
        xy=np.asarray(self.xy_displacement_m,dtype=float)
        if (any(not isinstance(v,str) or not v for v in (self.episode_id,self.reset_id))
                or type(self.physics_index) is not int or self.physics_index<0
                or xy.shape!=(2,) or not np.isfinite(xy).all()
                or isinstance(self.minimum_clearance_m,bool) or not np.isfinite(self.minimum_clearance_m)
                or type(self.contact_observed) is not bool):raise ValueError('runtime_safety_observation')
        object.__setattr__(self,'xy_displacement_m',owned(xy))


class ProgressGuard:
    """Count measured progress at successive confirmed control boundaries.

Static wrench success never counts as reaching the reference. Reference label
changes do not reset accumulated lack of progress. These finite stop rules are
engineering admission conditions, not a proof of stability or infeasibility.
"""
    def __init__(self,configuration,*,config=RuntimeConfig()):
        self.mask=control_mask(configuration);self.config=config
        self._index=None;self._anchor=None;self._without_progress=0;self._zero=0;self._stopped=None

    def observe(self,control_index,state,reference,*,reference_id,last_tracking=None):
        def stop(reason):
            self._stopped=reason;return dict(status='stop',reason=reason)
        if self._stopped is not None:return stop(self._stopped)
        if (type(control_index) is not int or control_index<0 or not isinstance(reference_id,str) or not reference_id
                or (self._index is not None and control_index!=self._index+1)):
            return stop('progress_boundary_sequence')
        self._index=control_index;cfg=self.config
        terms=tracking_terms(np.asarray(state,dtype=float)[None],reference,self.mask)
        score=max(float(np.sqrt(terms['depth'][0]))/cfg.depth_tracking_band_m,
                  float(np.sqrt(terms['attitude'][0]))/cfg.attitude_tracking_band_rad)
        improved=self._anchor is not None and score<=self._anchor*(1-cfg.minimum_improvement_fraction)
        if score<=1:
            self._anchor=None;self._without_progress=0;self._zero=0
        elif self._anchor is None or improved:
            self._anchor=score;self._without_progress=0;self._zero=0
        else:
            self._without_progress+=1
            info={} if last_tracking is None else last_tracking
            self._zero=self._zero+1 if info.get('tracking_status')=='tracking_limited' and info.get('zero_progress') is True else 0
        if self._zero>=cfg.zero_progress_controls:return stop('persistent_zero_progress')
        if self._without_progress>=cfg.no_improvement_controls:return stop('persistent_tracking_no_improvement')
        return dict(status='continue',reason=None,normalized_tracking_error=score,
                    controls_without_improvement=self._without_progress,zero_progress_controls=self._zero)


class RuntimeCoordinator:
    """One dispatch per interval; only acknowledge() advances causal history."""
    def __init__(self,ledger,feedback,worker=None,*,config=RuntimeConfig(),admission=AdmissionConfig(),clock=time.perf_counter):
        from koopman.prepared_projected_v40 import _context_key
        if (feedback.domain.identity!=ledger._domain.identity
                or _context_key(feedback.context)!=_context_key(ledger._context)
                or not isinstance(config,RuntimeConfig)):
            raise ValueError('runtime_policy_binding')
        self.ledger=ledger;self.feedback=feedback;self.worker=worker;self.config=config;self.clock=clock
        self.arbiter=PlanArbiter(ledger,config=admission,clock=clock)
        self.progress=ProgressGuard(ledger._domain.configuration,config=config)
        self._worker_generation=None if worker is None else worker.generation
        self._pending_info=None;self._last_tracking=None;self._prefix_tracking=None
        self.stats=dict(requests=0,mpc_activations=0,confirmed_controls=0,dispatches=0,
                        rejected_replies=0,worker_failures=0)

    def _stop(self,reason,*,actual_history_advanced=False):
        self.arbiter.invalidate(reason);self.ledger.abort(reason)
        return dict(status='stop',reason=str(reason),packet=None,actual_history_advanced=actual_history_advanced)

    def _safety(self,observation,episode_id,reset_id,physics_index):
        if (not isinstance(observation,SafetyObservation) or observation.episode_id!=episode_id
                or observation.reset_id!=reset_id or observation.physics_index!=physics_index):
            raise ValueError('runtime_safety_binding')
        if observation.contact_observed:raise ValueError('runtime_contact')
        if observation.minimum_clearance_m<self.config.minimum_clearance_m:raise ValueError('runtime_clearance')
        if np.linalg.norm(observation.xy_displacement_m)>self.config.maximum_xy_displacement_m:
            raise ValueError('runtime_horizontal_displacement')

    def replace_worker(self,worker):
        """Lifecycle-only: caller has already closed old/prepared new worker."""
        if (worker is None or worker.state!='ready' or worker.generation==self._worker_generation
                or (self.worker is not None and self.worker.state not in ('failed','timed_out','closed'))):
            raise ValueError('runtime_worker_replacement_not_ready')
        self.arbiter.invalidate('worker_replaced');self.ledger.restart_worker_generation()
        self.worker=worker;self._worker_generation=worker.generation;self._prefix_tracking=None

    def step(self,observation,reference,*,reference_id,safety):
        started=self.clock()
        try:
            if self.ledger.stopped:return self._stop(self.ledger.stop_reason)
            self._safety(safety,observation.episode_id,observation.reset_id,observation.physics_index)
            cap=self.ledger.capture(observation,reference,reference_id=reference_id)
            progress=self.progress.observe(cap.physics_index//2,cap.state,cap.reference,
                reference_id=cap.reference_id,last_tracking=self._last_tracking)
            if progress['status']=='stop':return self._stop(progress['reason'])
            if self.worker is not None:
                if self.worker.generation!=self._worker_generation:return self._stop('worker_changed_without_lifecycle')
                event=self.worker.poll()
                if event is not None and event['status']=='result':
                    result=self.arbiter.ingest(event)
                    if result['status']=='rejected':self.stats['rejected_replies']+=1
                elif event is not None and event['status'] in ('failed','timeout'):
                    self.arbiter.invalidate('worker_'+str(event.get('reason')));self.stats['worker_failures']+=1
            choice=self.arbiter.choose(cap);tracking=None
            if choice['status']=='proposal':
                command=choice['command'];source=choice['source']
                if choice.get('activated'):self.stats['mpc_activations']+=1
                if source=='committed_prefix' and choice.get('prefix_source')=='fallback':tracking=self._prefix_tracking
            else:
                self.arbiter.invalidate(choice['reason'])
                fallback=self.feedback.decide(cap.state,cap.reference,previous=cap.previous)
                if fallback['status']!='ready':return self._stop('fallback_'+str(fallback.get('reason')))
                command=fallback['command'];source='fallback'
                tracking={k:fallback.get(k) for k in ('tracking_status','zero_progress')}
            if (self.worker is not None and self.worker.state=='ready' and not self.arbiter.pending and cap.previous is not None):
                prefix=(self.arbiter.following_prefix(cap) if source=='mpc' else
                    np.repeat(command[None],self.arbiter.config.prefix_controls,axis=0) if source=='fallback' else None)
                if prefix is not None:
                    request=PlanningRequest(uuid.uuid4().hex,cap,prefix)
                    receipt=self.worker.submit(request.request_id,request)
                    if receipt['status']=='accepted':
                        self.arbiter.register(request,receipt,prefix_source='mpc' if source=='mpc' else 'fallback')
                        self._prefix_tracking=tracking;self.stats['requests']+=1
                        if source=='fallback':source='committed_prefix'
            if self.clock()-started>=self.config.control_compute_budget_s:return self._stop('control_decision_timeout')
            token=self.ledger.reserve(cap,command,source=source,startup=cap.previous is None)
            packet=self.ledger.dispatch(token);elapsed=self.clock()-started
            if elapsed>=self.config.control_compute_budget_s:return self._stop('control_decision_timeout')
            self._pending_info=dict(tracking=tracking,compute_s=elapsed,ticket=token)
            self.stats['dispatches']+=1
            return dict(status='dispatch',reason=None,packet=packet,progress=progress,
                decision_compute_ms=1000*elapsed,actual_history_advanced=False)
        except (ValueError,RuntimeError,TypeError,KeyError,AttributeError,FloatingPointError) as exc:
            return self._stop('runtime_decision_failed:'+str(exc))

    def acknowledge(self,ticket,actual_command,*,physics_index,episode_id,reset_id,safety):
        started=self.clock();advanced=False
        try:
            ack=self.ledger.acknowledge(ticket,actual_command,physics_index=physics_index,
                episode_id=episode_id,reset_id=reset_id)
            advanced=True
            # Even an unsafe physical substep happened: preserve its actual
            # receipt before stopping, including half-interval histories.
            self._safety(safety,episode_id,reset_id,physics_index+1)
            if self._pending_info is None or self._pending_info['ticket']!=ticket:
                return self._stop('runtime_ack_pending_binding',actual_history_advanced=True)
            self._pending_info['compute_s']+=self.clock()-started
            total=self._pending_info['compute_s']
            if ack['interval_complete']:
                self.stats['confirmed_controls']+=1;self._last_tracking=self._pending_info['tracking'];self._pending_info=None
            if total>=self.config.control_compute_budget_s:return self._stop('control_compute_timeout',actual_history_advanced=True)
            return dict(status='acknowledged',receipt=ack,control_compute_ms=1000*total,
                timing_scope='decision_plus_ack_computation_excludes_simulator_step',actual_history_advanced=True)
        except (ValueError,RuntimeError,TypeError,KeyError,FloatingPointError) as exc:
            return self._stop('runtime_ack_failed:'+str(exc),actual_history_advanced=advanced)
