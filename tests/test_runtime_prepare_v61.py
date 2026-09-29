from pathlib import Path
import importlib
import pytest
import torch


def api():
    assert (Path(__file__).resolve().parents[1]/'workflows/runtime_prepare_v61.py').exists()
    return importlib.import_module('workflows.runtime_prepare_v61')


def test_warmup_clones_every_input_and_synchronizes_without_advancing_state():
    m=api(); x=torch.tensor([1.,2.]); sync=[]; seen=[]
    def operation(arg):
        seen.append(arg.clone());arg.add_(1)
        return arg
    r=m.warm_pure_calls([('test',operation,(x,))],synchronize=lambda:sync.append(1),repeats=3)
    assert torch.equal(x,torch.tensor([1.,2.]))
    assert all(torch.equal(q,x) for q in seen)
    assert len(sync)==6
    assert r['physics_steps']==0 and r['calls']==3 and r['startup_seconds']>=0


def test_warmup_failure_is_not_ignored():
    m=api()
    def fail(x):raise ValueError('warmup failed')
    with pytest.raises(ValueError,match='warmup failed'):
        m.warm_pure_calls([('test',fail,(1,))],synchronize=lambda:None)


def test_warmup_rejects_environment_objects_and_unbounded_repeat():
    m=api()
    with pytest.raises(TypeError,match='scratch_input'):
        m.warm_pure_calls([('env',lambda x:x,(object(),))],synchronize=lambda:None)
    for n in (0,65,True):
        with pytest.raises(ValueError):m.warm_pure_calls([],synchronize=lambda:None,repeats=n)


def test_reset_invariance_fails_closed():
    m=api()
    assert m.assert_unchanged({'clock':[0],'actuator':[0]}, {'clock':[0],'actuator':[0]}) is None
    with pytest.raises(ValueError,match='warmup_changed_runtime'):
        m.assert_unchanged({'clock':[0]}, {'clock':[1]})
