"""Complete solver decisions must survive the allocation reuse optimization."""
from dataclasses import replace
import time
import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from test_bounded_mpc_v44 import fixtures


def compare(a,b):
    for key in ('status','reason','candidate_count','candidates','selected_index','runtime_eligible'):
        assert a[key]==b[key], key
    for key in ('commands','predictions','cost','baseline_cost'):
        if a[key] is None: assert b[key] is None
        else: np.testing.assert_allclose(a[key],b[key],rtol=1e-12,atol=1e-12,err_msg=key)


def paired(name='base'):
    from koopman.bounded_mpc_v45 import BoundedMPC
    live,domain,old,args=fixtures(name)
    new=BoundedMPC(domain,old.predictor,model_id=domain.model_id,config=old.config,weights=old.weights,allow_diagnostic=True)
    return live,old,new,args


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('prefix',[0,3])
def test_unchanged_solver_candidates_selection_cost_and_history(name,prefix):
    live,old,new,args=paired(name); args['committed_prefix']=prefix
    compare(new.solve(**args),old.solve(**args))
    assert live.physics_index==0


@pytest.mark.parametrize('kind',['state','command','slew','saturation','prediction','baseline'])
def test_no_go_and_baseline_decisions_are_unchanged(kind):
    _,old,new,args=paired()
    if kind=='state': args['initial_state'][0]=1.
    if kind=='command': args['baseline'][:,3]=.96
    if kind=='slew': args['baseline'][:,3]=.2
    if kind=='saturation': args['baseline'][:]=[.4,.4,0,.4];args['previous'][:]=[.4,.4,0,.4]
    if kind=='prediction': old.predictor=new.predictor=lambda x,u,c:np.full_like(x,np.nan)
    if kind=='baseline': args['reference'][0]=args['initial_state'][0]
    compare(new.solve(**args),old.solve(**args))


def test_whole_solver_uses_only_unique_allocations(monkeypatch):
    from koopman.prepared_allocation_v42 import PreparedDirectAllocation
    live,old,new,args=paired('uuv6_angled'); calls=[]; original=PreparedDirectAllocation.command
    expected=old.solve(**args)
    def counted(self,*a,**kw): calls.append(1); return original(self,*a,**kw)
    monkeypatch.setattr(PreparedDirectAllocation,'command',counted)
    actual=new.solve(**args)
    compare(actual,expected)
    assert len(calls)==9
    assert live.physics_index==0


def test_high_resolution_timeout_still_rejects_without_committing(monkeypatch):
    live,_,new,args=paired(); new.config=replace(new.config,timeout_ms=20.)
    def slow(x,u,c): time.sleep(.03); return x.copy()
    new.predictor=slow
    monkeypatch.setattr(time,'monotonic',lambda:12345.)
    result=new.solve(**args)
    assert result['status']=='no_plan' and result['reason']=='timeout'
    assert live.physics_index==0 and result['runtime_eligible'] is False
