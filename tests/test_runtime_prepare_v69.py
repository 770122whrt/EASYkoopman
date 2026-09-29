from types import SimpleNamespace
import pytest
import torch

def test_allocation_warmup_runs_actual_topology_on_private_inputs(monkeypatch):
    from workflows.runtime_prepare_v69 import warm_allocation
    import easyuuv_nc.thrust_allocation as allocation
    matrix=torch.eye(6)[:,:4];weight=torch.ones(6);sign=torch.tensor([-1.,1.,-1.,1.])
    env=SimpleNamespace(_use_config_alloc=True,_alloc_B=matrix,_alloc_weight=weight,
        _alloc_channel_sign=sign,_alloc_mode='wls',device='cpu',num_envs=1)
    before=[v.clone() for v in (matrix,weight,sign)];calls=[];real=allocation.allocate
    def inspect(b,wrench,**kwargs):
        calls.append((b.clone(),wrench.clone(),kwargs['mode']))
        result=real(b,wrench,**kwargs);b.add_(9);kwargs['weight'].add_(9)
        return result
    monkeypatch.setattr(allocation,'allocate',inspect)
    result=warm_allocation(env,synchronize=lambda:None)
    assert len(calls)==8 and result['physics_steps']==0
    assert all(torch.equal(c[0],before[0]) and c[2]=='wls' for c in calls)
    assert all(torch.equal(a,b) for a,b in zip((matrix,weight,sign),before))

def test_legacy_does_not_access_missing_allocation():
    from workflows.runtime_prepare_v69 import warm_allocation
    assert warm_allocation(SimpleNamespace(_use_config_alloc=False))['calls']==0

def test_allocation_preparation_failure_is_fatal(monkeypatch):
    from workflows.runtime_prepare_v69 import warm_allocation
    import easyuuv_nc.thrust_allocation as allocation
    def fail(*a,**kw):raise ValueError('allocation failure')
    monkeypatch.setattr(allocation,'allocate',fail)
    env=SimpleNamespace(_use_config_alloc=True,_alloc_B=torch.eye(6),_alloc_weight=None,
        _alloc_channel_sign=torch.ones(4),_alloc_mode='pinv',device='cpu',num_envs=1)
    with pytest.raises(ValueError,match='allocation failure'):warm_allocation(env,synchronize=lambda:None)
