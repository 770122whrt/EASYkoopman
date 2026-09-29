"""Selection/causality and timeout contracts; not physics performance evidence."""
import importlib
from types import SimpleNamespace
import numpy as np
import pytest


def api():
    assert importlib.util.find_spec('koopman.reliable_mpc_v77'), 'v77 reliable solver interface missing'
    return importlib.import_module('koopman.reliable_mpc_v77')


class Checker:
    horizon=3
    def __init__(self):self.calls=[];self.reject=False
    def check(self,origin,state,commands,previous,reference):
        self.calls.append(np.array(commands))
        ok=not self.reject and np.asarray(commands).shape==(3,4) and np.isfinite(commands).all() and np.max(np.abs(commands))<.5
        return dict(feasible=ok,reason=None if ok else 'support',cost=float(np.sum(np.asarray(commands)**2)) if ok else None,
                    predictions=np.zeros((12,11)) if ok else None)


class Worker:
    def __init__(self):self.requests=[];self.timeout=False;self.bad=False
    def call(self,request):
        self.requests.append(request)
        if self.timeout:return dict(status='no_plan',reason='solver_timeout',commands=None,solver={'return_status':'Maximum_CpuTime_Exceeded'})
        commands=np.full((3,4),.8) if self.bad else np.asarray(request['initial_guess'])*.9
        return dict(status='optimized',reason=None,exact_feasible=True,commands=commands,
                    solver={'return_status':'Solve_Succeeded'},worker_pid=123)
    def close(self):return {'process_stopped':True,'io_threads_stopped':True}


def setup():
    m=api();c=Checker();w=Worker();s=m.ReliableMPC(c,w)
    request=dict(origin=SimpleNamespace(origin_control=2),initial_state=np.zeros(11),
        baseline=np.full((3,4),.1),previous=np.full(4,.1),reference=np.array([5.5,1,0,0,0]))
    return s,c,w,request


def advance(request,result):
    request['origin']=SimpleNamespace(origin_control=request['origin'].origin_control+2)
    request['previous']=result['commands'][0]


def test_reuses_shifted_plan_only_after_next_confirmed_interval():
    s,c,w,r=setup();first=s.solve(**r);advance(r,first);s.solve(**r)
    np.testing.assert_array_equal(w.requests[-1]['initial_guess'],np.vstack([first['commands'][1:],first['commands'][-1]]))


@pytest.mark.parametrize('change',['index','previous','reference'])
def test_old_plan_not_reused_after_history_or_target_change(change):
    s,c,w,r=setup();first=s.solve(**r);advance(r,first)
    if change=='index':r['origin']=SimpleNamespace(origin_control=10)
    if change=='previous':r['previous']=np.full(4,.2)
    if change=='reference':r['reference']=np.array([5.6,1,0,0,0])
    result=s.solve(**r);assert not result['warm_start_used']
    np.testing.assert_array_equal(w.requests[-1]['initial_guess'],r['baseline'])


def test_timeout_can_only_retain_current_exact_feasible_plan():
    s,c,w,r=setup();w.timeout=True;result=s.solve(**r)
    assert result['status']=='timeout_retained' and result['exact_feasible']
    c.reject=True;advance(r,result);rejected=s.solve(**r)
    assert rejected['status']=='no_plan' and rejected['commands'] is None


def test_repeated_timeout_fallback_is_bounded():
    s,c,w,r=setup();w.timeout=True
    for _ in range(3):
        result=s.solve(**r);assert result['exact_feasible'];advance(r,result)
    result=s.solve(**r);assert result['reason']=='consecutive_solver_failures'


def test_worker_claim_cannot_bypass_parent_exact_check():
    s,c,w,r=setup();w.bad=True;result=s.solve(**r)
    assert result['status']=='no_plan' and result['reason']=='worker_plan_failed_exact_check'


def test_infeasible_feedback_does_not_veto_feasible_shifted_plan():
    s,c,w,r=setup();first=s.solve(**r);advance(r,first);r['baseline']=np.full((3,4),.8)
    result=s.solve(**r);assert result['exact_feasible'] and result['baseline_cost'] is None
    assert result['status']=='recovered' and result['warm_start_used']


def test_synchronous_worker_limits_are_explicitly_nonrealtime():
    m=api();limits=m.SynchronousLimits(request_timeout_ms=45000)
    assert limits.request_timeout_ms==45000
    with pytest.raises(ValueError):m.SynchronousLimits(request_timeout_ms=float('inf'))


def test_deadzone_flat_guess_uses_physical_target_only_as_optimizer_initialization():
    s,c,w,r=setup()
    c.deadzone_flat=lambda plan:True
    c.domain=SimpleNamespace(command_lower=np.full(4,-.4),command_upper=np.full(4,.4))
    c.mask=np.array([1,1,0,1])
    r['previous']=np.zeros(4);r['physical_target']=np.array([.2,-.1,0,.3])
    answer=s.solve(**r)
    guess=w.requests[-1]['initial_guess']
    np.testing.assert_allclose(guess,[[.02,-.02,0,.02],[.04,-.04,0,.04],[.06,-.06,0,.06]])
    assert answer['initialization_kind']=='physical_target_ramp'
    assert answer['exact_feasible']
    assert len(w.requests)==1


def test_nonflat_guess_preserves_frozen_warm_start_policy():
    s,c,w,r=setup();c.deadzone_flat=lambda plan:False
    r['physical_target']=np.array([.2,-.1,0,.3]);s.solve(**r)
    np.testing.assert_array_equal(w.requests[-1]['initial_guess'],r['baseline'])


def test_ramp_retained_by_worker_is_not_counted_as_optimized_solution():
    s,c,w,r=setup();c.deadzone_flat=lambda plan:True
    c.domain=SimpleNamespace(command_lower=np.full(4,-.4),command_upper=np.full(4,.4));c.mask=np.ones(4)
    def retained(request):
        return dict(status='baseline_retained',commands=request['initial_guess'],solver={})
    w.call=retained;r['previous']=np.zeros(4);r['physical_target']=np.full(4,.2)
    answer=s.solve(**r)
    assert answer['status']=='initialization_retained'
def test_worker_spawn_overrides_mutated_blas_environment_and_restores_parent(monkeypatch):
    import os
    import koopman.reliable_mpc_v77 as module
    seen={}
    class Worker:
        state='ready'
        def __init__(self,*a,**kw):
            from types import SimpleNamespace
            self._process=SimpleNamespace(pid=os.getpid()+100)
        def start(self):
            seen.update({k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})
        def poll(self):return dict(status='ready')
        def close(self):return {}
    monkeypatch.setattr(module,'IsolatedSolverWorker',Worker)
    monkeypatch.setenv('OPENBLAS_NUM_THREADS','32')
    monkeypatch.setenv('OMP_NUM_THREADS','8')
    monkeypatch.delenv('MKL_NUM_THREADS',raising=False)
    module.ProcessTransport({})
    assert set(seen.values())=={'1'}
    assert os.environ['OPENBLAS_NUM_THREADS']=='32'
    assert os.environ['OMP_NUM_THREADS']=='8'
    assert 'MKL_NUM_THREADS' not in os.environ
