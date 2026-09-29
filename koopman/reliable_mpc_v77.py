"""Synchronous, process-isolated MPC with causal plan reuse and exact admission.

This is a simulation-time interface. It does not promise real-time execution.
The two retained references are already known plans, not a direction grid.
"""
from dataclasses import dataclass
from types import SimpleNamespace
import math
import os
import time
import numpy as np
from koopman.solver_worker_v49 import IsolatedSolverWorker,WorkerLimits
from koopman.control_objective_v44 import ObjectiveWeights,control_mask


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
    """Reuse the frozen admission method without constructing an NLP in Isaac."""
    def __init__(self,domain,predictor,*,horizon=10,weights=ObjectiveWeights()):
        from koopman.prepared_allocation_v42 import PreparedDirectAllocation
        self.domain,self.predictor,self.horizon,self.weights=domain,predictor,horizon,weights
        self.mask=control_mask(domain.configuration)
        self.plant=SimpleNamespace(allocator=PreparedDirectAllocation(domain.configuration))

    def check(self,origin,state,commands,previous,reference):
        from koopman.continuous_mpc_v76 import ContinuousMPC
        if self.domain.check_states(np.asarray(state)[None]):
            return dict(feasible=False,reason='initial_state_out_of_support',cost=None,predictions=None)
        return ContinuousMPC.check(self,origin,state,commands,previous,reference)

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


class _Engine:
    def __init__(self,spec):
        import torch
        torch.set_num_threads(1)
        from koopman.continuous_mpc_v76 import ContinuousMPC
        predictor=make_predictor(spec)
        self.solver=ContinuousMPC(spec['domain'],predictor,horizon=spec['horizon'],weights=spec['weights'],solve_seconds=30.)

    def __call__(self,request):
        cpu=time.process_time()
        request=dict(request);guess=request.pop('initial_guess');request['baseline']=guess
        result=self.solver.solve(**request)
        result.update(worker_pid=os.getpid(),worker_cpu_seconds=time.process_time()-cpu,
                      worker_threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})
        return result


def make_predictor(spec):
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.physical_control_v76 import PhysicalPredictor
    if spec['kind']=='projected_koopman':return prepare_projected(spec['fitted'],spec['context'])
    if spec['kind']=='nominal_physics':return PhysicalPredictor(spec['fitted'],spec['context'])
    raise ValueError('controller_kind')


class ProcessTransport:
    def __init__(self,spec,*,limits=SynchronousLimits()):
        self.worker=IsolatedSolverWorker(_Engine,spec,limits=limits)
        # Isaac startup mutates OPENBLAS_NUM_THREADS. Set the child environment
        # before spawn imports NumPy/CasADi; torch.set_num_threads alone cannot
        # limit their independent BLAS pools. Restore the parent afterwards.
        keys=('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')
        prior={k:os.environ.get(k) for k in keys}
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
        except BaseException:
            self.worker.close();raise
        self.pid=self.worker._process.pid
        assert self.pid!=os.getpid()

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


class ReliableMPC:
    def __init__(self,checker,worker):
        self.checker,self.worker,self.horizon=checker,worker,checker.horizon
        self._last=None;self._failures=0

    def solve(self,*,origin,initial_state,baseline,previous,reference,physical_target=None):
        started=time.perf_counter()
        result=dict(status='no_plan',reason=None,commands=None,predictions=None,cost=None,
                    baseline_cost=None,exact_feasible=False,runtime_eligible=False,
                    warm_start_used=False,search_kind='continuous_nonlinear_program',solver={})
        def finish(reason=None):
            result['reason']=reason;result['elapsed_seconds']=time.perf_counter()-started
            return result
        try:
            base=np.asarray(baseline);old=np.asarray(previous);ref=np.asarray(reference)
            if base.shape!=(self.horizon,4) or old.shape!=(4,) or ref.shape!=(5,):return finish('input_shape')
            def check(plan):return self.checker.check(origin,initial_state,plan,old,ref)
            checked=check(base);result['baseline_check']={k:v for k,v in checked.items() if k!='predictions'}
            result['baseline_cost']=checked['cost'];retained=[];guess=base
            if checked['feasible']:retained.append(('baseline_retained',base,checked))
            last=self._last
            if (last is not None and origin.origin_control==last['origin']+2
                    and np.array_equal(ref,last['reference'])
                    and np.allclose(old,last['commands'][0],atol=1e-7,rtol=0)):
                shifted=np.vstack([last['commands'][1:],last['commands'][-1]])
                warm=check(shifted)
                result['warm_check']={k:v for k,v in warm.items() if k!='predictions'}
                if warm['feasible']:
                    guess=shifted;result['warm_start_used']=True
                    retained.append(('warm_retained',shifted,warm))
            if physical_target is not None and self.checker.deadzone_flat(guess):
                result['initialization_kind']='physical_target_ramp'
                result['initialization_replaced']='shifted_plan' if result['warm_start_used'] else 'feedback_hold'
                guess=physical_ramp(old,physical_target,self.checker.domain,self.checker.mask,self.horizon)
                result['initialization_sequence']=guess.copy()
                result['warm_start_used']=False
            request=dict(origin=origin,initial_state=initial_state,baseline=base,previous=old,reference=ref,initial_guess=guess)
            answer=self.worker.call(request);result['solver']=answer.get('solver',{})
            for k in ('worker_pid','worker_cpu_seconds','worker_threads','constraint_violation'):result[k]=answer.get(k)
            result['worker_reason']=answer.get('reason');result['worker_status']=answer.get('status')
            failed=answer.get('commands') is None
            self._failures=self._failures+1 if failed else 0
            if self._failures>3:return finish('consecutive_solver_failures')
            if not failed:
                commands=np.asarray(answer['commands']);verified=check(commands)
                if not verified['feasible']:return finish('worker_plan_failed_exact_check')
                selected_status='optimized' if checked['feasible'] else 'recovered'
                if result.get('initialization_kind')=='physical_target_ramp' and answer.get('status')=='baseline_retained':
                    selected_status='initialization_retained'
                retained.append((selected_status,commands,verified))
            if not retained:return finish('no_exact_feasible_solution_found')
            status,commands,verified=min(retained,key=lambda item:item[2]['cost'])
            if failed:
                status='timeout_retained' if answer.get('reason') in ('solver_timeout','worker_timeout') else 'solver_failure_retained'
            commands=np.asarray(commands,dtype=np.float32)
            self._last=dict(origin=origin.origin_control,reference=ref.copy(),commands=commands.copy())
            result.update(status=status,commands=commands,predictions=verified['predictions'],cost=verified['cost'],exact_feasible=True,
                          consecutive_solver_failures=self._failures)
            return finish()
        except (ValueError,RuntimeError,TypeError,KeyError,AttributeError,FloatingPointError) as exc:
            result['exception']=str(exc)
            return finish('invalid_solver_request_or_reply')

    def close(self):return self.worker.close()


def create_solver(domain,fitted,context,kind,*,horizon=10,weights=ObjectiveWeights()):
    spec=dict(domain=domain,fitted=fitted,context=context,kind=kind,horizon=horizon,weights=weights)
    checker=ExactChecker(domain,make_predictor(spec),horizon=horizon,weights=weights)
    return ReliableMPC(checker,ProcessTransport(spec))
