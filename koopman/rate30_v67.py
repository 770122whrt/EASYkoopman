"""30 Hz issuance with unchanged 120 Hz physics and 60 Hz prediction history.

A macro command is acknowledged four times. Pair entries remain explicit in the
micro history so original actuator origins, prefix timing and horizon stay valid.
"""
import hashlib
import time
import numpy as np
from koopman.bounded_feedback_v46 import BoundedFeedback, FeedbackConfig
from koopman.bounded_mpc_v44 import SearchConfig, COMMAND_ATOL, owned
from koopman.cached_checks_v53 import CachedExecutionLedger
from koopman.control_objective_v44 import checked_reference
from koopman.execution_ledger_v48 import BoundaryObservation, ExecutionCapture, _label
from koopman.inexact_tracking_v66 import InexactRecoveryBaseline
from koopman.plan_continuity_v54 import PlanArbiter as PreviousArbiter, RuntimeCoordinator as PreviousCoordinator
from koopman.runtime_coordinator_v52 import ProgressGuard, RuntimeConfig

FEEDBACK_CONFIG=FeedbackConfig(slew=.02,timeout_ms=10)
SEARCH_CONFIG=SearchConfig(horizon=20,slew=(.02,)*4)
RUNTIME_CONFIG=RuntimeConfig(control_compute_budget_s=1/30,no_improvement_controls=30,zero_progress_controls=15)

def paired(value):
    try:
        a=np.asarray(value,dtype=float)
        return bool(a.ndim==2 and a.shape[1]==4 and len(a)>0 and len(a)%2==0
                    and np.isfinite(a).all() and np.array_equal(a[::2],a[1::2]))
    except (ValueError,TypeError):return False

class ExecutionLedger(CachedExecutionLedger):
    def __init__(self,*args,feedback_config=FEEDBACK_CONFIG,**kwargs):
        if abs(feedback_config.slew-.02)>1e-12:raise ValueError('rate30_feedback_slew')
        super().__init__(*args,feedback_config=feedback_config,**kwargs)

    def capture(self, observation, reference, *, reference_id):
        with self._guard():
            self._binding_check()
            index = self._live.physics_index
            if self._pending is not None or index % 4:raise ValueError('execution_pending_or_half_boundary')
            if (not isinstance(observation, BoundaryObservation) or observation.physics_index != index
                    or observation.episode_id != self._reset.episode_id or observation.reset_id != self._reset.reset_id):
                raise ValueError('execution_observation_binding')
            if self._domain.check_states(observation.state[None]):raise ValueError('execution_state_out_of_support')
            ref = checked_reference(reference); _label(reference_id)
            if index == 0 and (reference_id != self._initial_reference_id
                    or not BoundedFeedback._same_pose_values(ref, self._initial_reference, 1e-12)
                    or not BoundedFeedback._same_pose_values(observation.state, self._reset.state, 1e-6)):
                raise ValueError('startup_reference_or_reset_changed')
            if reference_id == self._reference_id:
                if not BoundedFeedback._same_pose_values(ref, self._reference, 1e-12):
                    raise ValueError('reference_changed_without_new_identity')
            else:
                self._reference_id = reference_id; self._reference = owned(ref)
                self._reference_revision += 1
            origin = self._live.snapshot(configuration=self._domain.configuration,
                context=self._context, origin_control=index//2, episode_id=self._reset.episode_id)
            value = ExecutionCapture(self._execution_id, self._reset.episode_id, self._reset.reset_id,
                index, self._digest, self._worker_generation, reference_id, self._reference_revision,
                *self._binding, time.perf_counter(), owned(observation.state), owned(ref),
                None if self._previous is None else owned(self._previous, np.float32), origin)
            self._capture = value
            return value

    def acknowledge(self, ticket, actual_command, *, physics_index, episode_id, reset_id):
        with self._guard():
            try:
                self._binding_check(); p = self._pending
                if (p is None or not p['dispatched'] or ticket != p['ticket']
                        or episode_id != self._reset.episode_id or reset_id != self._reset.reset_id
                        or type(physics_index) is not int or physics_index != self._live.physics_index
                        or physics_index != p['physics_index']+p['acknowledged']):
                    raise ValueError('acknowledgment_binding_or_sequence')
                actual = self._checked_command(actual_command, self._previous,
                    target=self._startup_target if p['startup'] else None)
                if not np.allclose(actual, p['command'], rtol=0, atol=COMMAND_ATOL):
                    raise ValueError('acknowledgment_command_mismatch')
                if p['acknowledged'] and not np.array_equal(actual, p['actual']):
                    raise ValueError('acknowledgment_four_substep_hold_mismatch')
                following_digest = hashlib.sha256(bytes.fromhex(self._digest)
                    + physics_index.to_bytes(8, 'little')+actual.tobytes()).hexdigest()
                # This is the sole live recurrence write. Everything above is validated first.
                self._live.record_issued(actual.copy(), physics_index=physics_index, episode_id=episode_id)
                self._digest = following_digest; p['acknowledged'] += 1
                if p['acknowledged'] == 1:
                    p['actual'] = actual
                    if p['startup']:self._startup_consumed = True
                if p['acknowledged'] % 2 == 0:
                    self._history.append((physics_index//2, actual))
                if p['acknowledged'] == 4:
                    self._previous = actual
                    self._pending = None
                return dict(physics_index=self._live.physics_index, history_digest=self._digest,
                    interval_complete=self._pending is None, startup_consumed=self._startup_consumed)
            except Exception as exc:
                self._stop_reason = 'execution_ack_failed:'+str(exc)
                raise

class Progress30(ProgressGuard):
    def __init__(self,configuration,*,config=RUNTIME_CONFIG):
        super().__init__(configuration,config=config)

    def observe(self,control_index,*args,**kwargs):
        if type(control_index) is not int or control_index<0 or control_index%2:
            self._stopped='progress_boundary_sequence'
            return dict(status='stop',reason=self._stopped)
        return super().observe(control_index//2,*args,**kwargs)

class RecoveryBaseline(InexactRecoveryBaseline):
    def __init__(self,*args,config=FEEDBACK_CONFIG,**kwargs):
        if abs(config.slew-.02)>1e-12:raise ValueError('rate30_feedback_slew')
        super().__init__(*args,config=config,**kwargs)

    def build(self,state,reference,previous,prefix,*,horizon,deadline):
        if type(horizon) is not int or horizon%2 or not 4<=horizon<=128 or not paired(prefix):
            return dict(status='no_baseline',reason='rate30_baseline_pairing',commands=None)
        result=super().build(state,reference,previous,np.asarray(prefix)[::2],horizon=horizon//2,deadline=deadline)
        if result['status']=='ready':
            result['commands']=owned(np.repeat(result['commands'],2,axis=0),np.float32)
            result['control_rate_hz']=30;result['prediction_grid_hz']=60
        return result

class Rate30Arbiter(PreviousArbiter):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.config.horizon%2 or self.config.prefix_controls%2:
            raise ValueError('rate30_admission_pairing')

    def register(self,request,receipt,**kwargs):
        if (getattr(getattr(request,'capture',None),'physics_index',-1)%4
                or not paired(getattr(request,'prefix',None))):
            raise ValueError('rate30_request_pairing')
        return super().register(request,receipt,**kwargs)

    def ingest(self,event):
        self._owner_check()
        p=event.get('payload') if isinstance(event,dict) else None
        if isinstance(p,dict) and p.get('status') in ('selected','baseline'):
            meta=p.get('metadata');origin=meta.get('origin_control') if isinstance(meta,dict) else None
            if (not paired(p.get('commands')) or type(origin) is not int or origin%2
                    or meta.get('control_rate_hz')!=30 or meta.get('prediction_grid_hz')!=60):
                active=self._active
                self.invalidate('rate30_reply_pairing')
                self._active=active
                return dict(status='rejected',reason='rate30_reply_pairing')
        return super().ingest(event)

    def choose(self,capture):
        if getattr(capture,'physics_index',-1)%4:
            self.invalidate('rate30_capture_boundary')
            return dict(status='fallback',command=None,source=None,reason='rate30_capture_boundary',actual_history_advanced=False)
        return super().choose(capture)

class RuntimeCoordinator(PreviousCoordinator):
    def __init__(self,*args,config=RUNTIME_CONFIG,**kwargs):
        super().__init__(*args,config=config,**kwargs)
        if not isinstance(self.ledger,ExecutionLedger):raise ValueError('rate30_ledger_required')
        self.progress=Progress30(self.ledger._domain.configuration,config=config)
        self.arbiter=Rate30Arbiter(self.ledger,config=self.arbiter.config,clock=self.clock)

def portable_rate30_factory(spec):
    from workflows.runtime_assets_v56 import PortableWorkerSpec
    if (not isinstance(spec,PortableWorkerSpec) or spec.config.horizon!=20
            or any(abs(v-.02)>1e-12 for v in spec.config.slew)
            or abs(spec.feedback_config.slew-.02)>1e-12 or spec.feedback_config.timeout_ms!=10):
        raise ValueError('rate30_worker_spec')
    from koopman.compiled_recovery_v64 import portable_compiled_factory
    from koopman.bounded_mpc_v67 import BoundedMPC
    solver=portable_compiled_factory(spec);old=solver.solver
    solver.baseline=RecoveryBaseline(solver.domain,solver.baseline.context,config=spec.feedback_config)
    solver.solver=BoundedMPC(solver.domain,old.predictor,model_id=solver.domain.model_id,
        config=spec.config,weights=old.weights,share_prefix=False)
    return solver
