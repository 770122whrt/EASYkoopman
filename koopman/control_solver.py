"""Current three-model controller: causal preview, isolated solve, exact admission.

Frozen scientific identities remain unchanged. Earlier implementations are
recoverable from their Git snapshots and frozen experiment source archives.
"""
from dataclasses import dataclass
from types import SimpleNamespace
import hashlib
import math
import os
from pathlib import Path
import time
import numpy as np
from koopman.solver_worker import IsolatedSolverWorker, WorkerLimits
from koopman.support_domain import COMMAND_ATOL
from koopman.control_objective import ObjectiveWeights, control_mask, checked_reference, trajectory_cost
from koopman.command_plan import PreparedCommands
from koopman.disturbance_model import prepare, physical_identity
from koopman.feedback import InexactTrackingFeedback
from koopman.feedback import FeedbackConfig
from workflows.feedback_inverse import MINIMUM_DEADZONE_DISTANCE
from workflows.fit_disturbance import load_record
from koopman.planning_margin import enforce_interior, PLANNING_MARGIN, OPTIMIZER_MARGIN

KINDS = ('physics', 'koopman', 'hybrid')



@dataclass(frozen=True)
class SynchronousLimits(WorkerLimits):
    startup_timeout_s: float=90.
    request_timeout_ms: float=45000.

    def __post_init__(self):
        for x,maximum in ((self.startup_timeout_s,120.),(self.request_timeout_ms,45000.)):
            if isinstance(x,bool) or not math.isfinite(x) or not 0<x<=maximum:
                raise ValueError('synchronous_worker_limit')
        for x in (self.max_request_bytes,self.max_result_bytes):
            if type(x) is not int or not 1024<=x<=4*1024**2:raise ValueError('worker_payload_limit')


class ExactChecker:
    def __init__(self,domain,predictor,*,horizon=10,weights=ObjectiveWeights()):
        from koopman.allocation import PreparedDirectAllocation
        self.domain,self.predictor,self.horizon,self.weights=domain,predictor,horizon,weights
        self.mask=control_mask(domain.configuration)
        self.plant=SimpleNamespace(allocator=PreparedDirectAllocation(domain.configuration))

    def check(self, origin, state, commands, previous, reference):
        result = dict(feasible=False, reason=None, cost=None, predictions=None)
        def reject(reason): result['reason'] = reason; return result
        state = np.asarray(state, dtype=float); old = np.asarray(previous, dtype=float)
        ref = checked_reference(reference)
        if state.shape != (11,) or old.shape != (4,) or not np.isfinite(old).all():
            return reject('check_input')
        if self.domain.check_states(state[None]): return reject('initial_state_out_of_support')
        a = np.asarray(commands, dtype=float)
        if (a.ndim != 2 or a.shape[1] != 4 or not 1 <= len(a) <= self.horizon
                or not np.isfinite(a).all() or np.any(np.abs(a) > .95)):
            return reject('command_bound')
        a = a.astype(np.float32); d = self.domain
        if np.any(np.abs(a*(1-self.mask)) > COMMAND_ATOL): return reject('command_mask')
        if np.any((a < d.command_lower-COMMAND_ATOL) | (a > d.command_upper+COMMAND_ATOL)):
            return reject('command_support')
        if np.any(np.abs(np.diff(np.vstack([old, a.astype(float)]), axis=0)) > .02+COMMAND_ATOL):
            return reject('command_slew')
        micro = np.repeat(a, 2, axis=0)
        prepared = PreparedCommands(origin, micro[None], allocator=self.plant.allocator)
        raw = prepared.pwm_raw[0].astype(float)
        if np.max(np.abs(raw)) > .95+COMMAND_ATOL: return reject('raw_pwm_saturation')
        if np.min(np.abs(np.abs(raw)-float(np.float32(.02)))) <= MINIMUM_DEADZONE_DISTANCE:
            return reject('raw_pwm_deadzone_margin')
        prediction = origin.forecast(state, micro, self.predictor)
        if not prediction['complete']: return reject('prediction_failed')
        bad = d.check_states(prediction['predictions'])
        if bad:
            result['rejection'] = bad
            return reject('predicted_'+bad['reason'])
        result.update(feasible=True, predictions=prediction['predictions'],
                      cost=trajectory_cost(prediction['predictions'], micro, old, ref, self.mask, self.weights))
        return enforce_interior(result, self.plant.allocator, commands)

    def deadzone_flat(self,commands):
        raw=np.asarray([self.plant.allocator.command(u,pre_tam=True)['pwm_raw'] for u in commands])
        return bool(np.all(np.abs(raw)<float(np.float32(.02))))


def physical_ramp(previous,target,domain,mask,horizon):
    """A causal initialization toward the inverse-physics target, never a ticket."""
    old=np.asarray(previous,dtype=float).copy();target=np.asarray(target,dtype=float)
    if old.shape!=(4,) or target.shape!=(4,) or not np.isfinite(target).all():
        raise ValueError('physical_initialization_shape')
    if np.any(np.abs(target*(1-mask))>1e-7):raise ValueError('physical_initialization_mask')
    target=np.clip(target,domain.command_lower,domain.command_upper)*mask
    rows=[]
    for _ in range(horizon):
        old=old+np.clip(target-old,-.02,.02);rows.append(old.copy())
    return np.asarray(rows)


def feedback_preview(origin, state, previous, reference, feedback, checker, *, timeout_s=30.):
    if not np.isfinite(timeout_s) or not 0 < timeout_s <= 60: raise ValueError('preview_budget')
    start = time.perf_counter(); x = np.array(state, dtype=float, copy=True)
    old = np.array(previous, dtype=float, copy=True); ref = checked_reference(reference)
    result = dict(status='no_preview', reason=None, commands=None, predictions=None,
                  cost=None, completed_macro_steps=0, runtime_eligible=False,
                  real_future_data_used=False, actual_history_advanced=False)
    sequence = []; predicted = None
    def finish(reason):
        result.update(reason=reason, elapsed_seconds=time.perf_counter()-start)
        return result
    for _ in range(checker.horizon):
        if time.perf_counter()-start >= timeout_s: return finish('preview_timeout')
        decision = feedback.decide(x.copy(), ref.copy(), previous=old.copy())
        if decision['status'] != 'ready': return finish('feedback_'+str(decision.get('reason')))
        sequence.append(np.array(decision['command'], dtype=np.float32, copy=True))
        # Replay from the immutable origin: never append simulated acknowledgments
        # to live history, and never use an observed future trajectory for x.
        checked = checker.check(origin, state, sequence, previous, ref)
        if not checked['feasible']: return finish('prefix_'+str(checked['reason']))
        predicted = checked['predictions']; x = predicted[-1].copy(); old = sequence[-1].copy()
        result['completed_macro_steps'] += 1
    if time.perf_counter()-start >= timeout_s: return finish('preview_timeout')
    result.update(status='ready', commands=np.asarray(sequence), predictions=predicted,
                  cost=checked['cost'])
    return finish(None)


def audit_selection(checker, origin, state, previous, reference, plans, selected, *, required, atol=1e-10):
    """Recompute every supplied reference. Never trust recorded feasibility/cost.

    The caller specifies required causal references from the decision inputs,
    not from a received worker list. This is finite-plan selection, not a proof
    of global optimality of the nonlinear continuous optimization problem.
    """
    if not set(required) <= set(plans): raise ValueError('missing_reference')
    if not np.isfinite(atol) or not 0 <= atol <= 1e-8: raise ValueError('selection_tolerance')
    selected = np.asarray(selected, dtype=float)
    # check() deliberately accepts prefixes for feedback preview; selection
    # must not let broadcasting compare a prefix to a full-horizon reference.
    if selected.shape != (checker.horizon, 4): raise ValueError('selected_plan_shape')
    if not np.isfinite(selected).all(): raise ValueError('selected_plan_nonfinite')
    summaries = {}; feasible = []
    for name, commands in plans.items():
        a = np.asarray(commands, dtype=float)
        if a.shape != (checker.horizon, 4): raise ValueError('selection_plan_shape')
        c = checker.check(origin, state, a, previous, reference)
        summaries[name] = {k:c[k] for k in ('feasible', 'reason', 'cost')}
        if c['feasible']: feasible.append((name, a, c))
    chosen = checker.check(origin, state, selected, previous, reference)
    reason = None
    if not chosen['feasible']: reason = 'selected_infeasible'
    elif not feasible: reason = 'no_feasible_reference'
    elif not any(np.allclose(selected, a, atol=COMMAND_ATOL, rtol=0) for _,a,_ in feasible):
        reason = 'selected_not_in_inventory'
    elif chosen['cost'] > min(c['cost'] for _,_,c in feasible)+atol: reason = 'dominated_selection'
    return dict(accepted=reason is None, reason=reason, references=summaries,
                selected_cost=chosen['cost'], global_optimum_claimed=False)


def audit_observed_pwm(raw, pwm):
    """Check measured backend PWM, not just proximity to a CPU reconstruction."""
    raw=np.asarray(raw,dtype=float);pwm=np.asarray(pwm,dtype=float)
    if (raw.ndim!=1 or raw.shape!=pwm.shape or len(raw) not in (4,6,8)
            or not np.isfinite(raw).all() or not np.isfinite(pwm).all()):
        raise ValueError('observed_pwm_shape')
    distance=float(np.min(np.abs(np.abs(raw)-float(np.float32(.02)))))
    reason=None
    if np.any(np.abs(pwm)>1) or not np.allclose(pwm,np.clip(raw,-1,1),atol=1e-6,rtol=0):
        reason='observed_pwm_clip'
    elif np.max(np.abs(raw))>.95+COMMAND_ATOL:reason='observed_pwm_saturation'
    elif distance<=MINIMUM_DEADZONE_DISTANCE:reason='observed_pwm_deadzone_margin'
    return dict(accepted=reason is None,reason=reason,minimum_margin=distance,
                required_margin=MINIMUM_DEADZONE_DISTANCE)


class _Engine:
    def __init__(self,spec):
        import torch
        torch.set_num_threads(1)
        from koopman.continuous_mpc import ContinuousMPC
        loaded=load_model(spec['model'],spec['sha256']);_verify_domain(loaded,spec['domain'])
        predictor=make_predictor(spec['kind'],loaded,spec['context'])
        self.solver=ContinuousMPC(spec['domain'],predictor,horizon=spec['horizon'],weights=spec['weights'],solve_seconds=30.)

    def __call__(self,request):
        cpu=time.process_time();request=dict(request);request['baseline']=request.pop('initial_guess')
        result=self.solver.solve(**request)
        result.update(worker_pid=os.getpid(),worker_cpu_seconds=time.process_time()-cpu)
        return result


class ProcessTransport:
    def __init__(self,spec,*,limits=SynchronousLimits(),engine_factory=_Engine):
        self.worker=IsolatedSolverWorker(engine_factory,spec,limits=limits)
        keys=('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS');prior={k:os.environ.get(k) for k in keys}
        try:
            for k in keys:os.environ[k]='1'
            self.worker.start()
        finally:
            for k,v in prior.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v
        self.sequence=0
        try:
            event=self._wait()
            if event['status']!='ready':raise RuntimeError('solver_startup:'+str(event))
        except BaseException:self.worker.close();raise
        self.pid=self.worker._process.pid
        if self.pid==os.getpid():raise RuntimeError('worker_not_isolated')

    def _wait(self):
        while True:
            event=self.worker.poll()
            if event is not None:return event
            if self.worker.state in ('closed','failed','timed_out'):
                return dict(status='failed',reason='worker_disabled')
            time.sleep(.001)

    def call(self,request):
        if self.worker.state=='timed_out':
            return dict(status='no_plan',reason='worker_timeout',commands=None,solver={'return_status':'Worker_Timeout'})
        submitted=self.worker.submit('v77-'+str(self.sequence),request);self.sequence+=1
        if submitted['status']!='accepted':raise RuntimeError('worker_submit:'+str(submitted))
        event=self._wait()
        if event['status']=='timeout':
            # Late replies remain invalid. Cleanup occurs on the owned lifecycle.
            return dict(status='no_plan',reason='worker_timeout',commands=None,solver={'return_status':'Worker_Timeout'})
        if event['status']!='result':raise RuntimeError('worker_protocol:'+str(event))
        return event['payload']

    def close(self):return self.worker.close()


class PreviewMPC:
    def __init__(self, checker, worker, feedback_factory, *, preview_enabled=True):
        if type(preview_enabled) is not bool: raise ValueError('preview_switch')
        self.checker, self.worker, self.horizon = checker, worker, checker.horizon
        self.feedback_factory = feedback_factory
        self.preview_enabled = preview_enabled
        self._last = None; self._failures = 0

    def solve(self, *, origin, initial_state, baseline, previous, reference, physical_target=None):
        started = time.perf_counter()
        result = dict(status='no_plan', reason=None, commands=None, predictions=None,
                      cost=None, exact_feasible=False, runtime_eligible=False,
                      search_kind='continuous_nonlinear_program', solver={},
                      preview_enabled=self.preview_enabled, origin_control=origin.origin_control,
                      reference=np.asarray(reference).copy())
        def finish(reason=None):
            result.update(reason=reason, elapsed_seconds=time.perf_counter()-started)
            return result
        try:
            ref = checked_reference(reference); old = np.asarray(previous, dtype=float)
            held = np.asarray(baseline, dtype=float)
            if held.shape != (self.horizon, 4) or old.shape != (4,): return finish('input_shape')
            plans = {'held':held.copy()}; checks = {}; required = ['held']
            def inspect(name, seq):
                plans[name] = np.asarray(seq, dtype=float).copy()
                checks[name] = self.checker.check(origin, initial_state, seq, old, ref)
            inspect('held', held)
            last = self._last
            if (last is not None and origin.origin_control == last['origin']+2
                    and np.array_equal(ref, last['reference'])
                    and np.allclose(old, last['commands'][0], atol=1e-7, rtol=0)):
                required.append('warm')
                inspect('warm', np.vstack([last['commands'][1:], last['commands'][-1]]))
            preview = (feedback_preview(origin, initial_state, old, ref,
                                       self.feedback_factory(), self.checker) if self.preview_enabled else
                       dict(status='disabled', reason='disabled_by_protocol'))
            result['preview'] = {k:v for k,v in preview.items() if k not in ('commands','predictions')}
            if preview['status'] == 'ready':
                required.append('preview'); inspect('preview', preview['commands'])
            # Preserve v77's warm-first initialization when no preview is usable;
            # only the new causal feedback preview may replace that initial guess.
            seed = 'warm' if checks.get('warm',{}).get('feasible') else 'held'
            if checks.get('preview',{}).get('feasible') and (
                    not checks[seed]['feasible'] or checks['preview']['cost'] < checks[seed]['cost']):
                seed = 'preview'
            guess = plans[seed].copy()
            result['initialization_source'] = seed
            if physical_target is not None and self.checker.deadzone_flat(guess):
                guess = physical_ramp(old, physical_target, self.checker.domain, self.checker.mask, self.horizon)
                seed = 'physical_target_ramp'
                result['initialization_sequence'] = guess.copy()
            result['initialization_kind'] = seed
            answer = self.worker.call(dict(origin=origin, initial_state=initial_state,
                         baseline=held, previous=old, reference=ref, initial_guess=guess))
            result['solver'] = answer.get('solver', {})
            for key in ('worker_pid','worker_cpu_seconds','worker_threads','constraint_violation',
                        'candidate_commands','candidate_failure','command_bound_violation',
                        'solution_check','selected_source'):
                result[key] = answer.get(key)
            result['worker_reason'] = answer.get('reason'); result['worker_status'] = answer.get('status')
            failed = answer.get('commands') is None
            result['worker_returned_commands'] = not failed
            self._failures = self._failures+1 if failed else 0
            if self._failures > 3: return finish('consecutive_solver_failures')
            if not failed:
                required.append('worker')
                if np.asarray(answer['commands']).shape != (self.horizon,4): return finish('worker_plan_shape')
                inspect('worker', answer['commands'])
                if not checks['worker']['feasible']: return finish('worker_plan_failed_exact_check')
            feasible = [name for name,c in checks.items() if c['feasible']]
            if not feasible: return finish('no_exact_feasible_solution_found')
            chosen = min(feasible, key=lambda name:checks[name]['cost'])
            commands = plans[chosen].astype(np.float32)
            # Re-evaluate ALL retained references independently of above costs.
            audit = audit_selection(self.checker, origin, initial_state, old, ref,
                                    plans, commands, required=tuple(required))
            result.update(selection_plans=plans, selection_audit=audit, selected_reference=chosen,
                          required_references=required)
            if not audit['accepted']: return finish('selection_audit_'+str(audit['reason']))
            status = {'held':'baseline_retained','warm':'warm_retained','preview':'preview_retained'}.get(chosen)
            if chosen == 'worker':
                status = 'optimized' if checks['held']['feasible'] else 'recovered'
                if answer.get('status') == 'baseline_retained': status = 'initialization_retained'
            if failed: status = 'timeout_retained' if answer.get('reason') in ('solver_timeout','worker_timeout') else 'solver_failure_retained'
            self._last = dict(origin=origin.origin_control, reference=ref.copy(), commands=commands.copy())
            result.update(status=status, commands=commands, cost=checks[chosen]['cost'],
                          predictions=checks[chosen]['predictions'], exact_feasible=True,
                          baseline_cost=checks['held']['cost'], consecutive_solver_failures=self._failures)
            return finish()
        except (ValueError, RuntimeError, TypeError, KeyError, FloatingPointError) as exc:
            result['exception'] = str(exc)
            return finish('invalid_solver_request_or_reply')

    def close(self): return self.worker.close()


@dataclass(frozen=True)
class LoadedModel:
    path: str
    file_sha256: str
    record: dict


def load_model(path,expected_sha256):
    path=Path(path).resolve();sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if sha!=expected_sha256:raise ValueError('v87_artifact_hash')
    record,_=load_record(path)
    return LoadedModel(str(path),sha,record)


def make_predictor(kind,loaded,context):
    from workflows.frozen_physics import from_record
    from koopman.physical_predictor import PhysicalPredictor
    if kind not in KINDS:raise ValueError('v87_model_kind')
    physical=PhysicalPredictor(from_record(loaded.record['physical_prior']),context,identified=True)
    if physical_identity(physical)!=loaded.record['physical_identity']:raise ValueError('v87_context_binding')
    return physical if kind=='physics' else prepare(loaded.record,context,physical,kind=kind)


def verify_support(loaded,assets):
    sources={name:digest for d in assets.domains.values() for name,digest in d.fit_sources}
    if sources!=loaded.record['physical_prior']['fit_episode_hashes']:raise ValueError('v87_common_support_sources')


def model_identity(loaded,kind):
    if kind not in KINDS:raise ValueError('v87_model_kind')
    return dict(kind=kind,prediction_content_sha256=loaded.record['content_sha256'],
        physical_content_sha256=loaded.record['physical_identity'],full_latent_propagation=kind!='physics',
        physical_recalibrated=False,online_learning=False,real_time_qualified=False)


def _verify_domain(loaded,domain):
    sources=loaded.record['physical_prior']['fit_episode_hashes']
    if domain.configuration!='base' or any(sources.get(n)!=s for n,s in domain.fit_sources):
        raise ValueError('v87_domain')


def create_solver(domain,context,kind,*,learned_model,learned_sha256,horizon=20,
                  weights=ObjectiveWeights(depth=4.),preview_enabled=True):
    loaded=load_model(learned_model,learned_sha256);_verify_domain(loaded,domain)
    predictor=make_predictor(kind,loaded,context)
    checker=ExactChecker(domain,predictor,horizon=horizon,weights=weights)
    worker=ProcessTransport(dict(domain=domain,context=context,kind=kind,model=loaded.path,
        sha256=loaded.file_sha256,horizon=horizon,weights=weights),engine_factory=_Engine)
    def factory():return InexactTrackingFeedback(domain,context,config=FeedbackConfig(slew=.02,timeout_ms=2000.))
    solver=PreviewMPC(checker,worker,factory,preview_enabled=preview_enabled)
    solver.model_identity=model_identity(loaded,kind)
    return solver
