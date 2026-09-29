import importlib.util
import numpy as np
from koopman.projected_edmd_v24 import PhysicalContext


def module():
    assert importlib.util.find_spec('workflows.evaluate_projected_edmd_v24')
    from workflows import evaluate_projected_edmd_v24
    return evaluate_projected_edmd_v24


def test_persistence_error_has_physical_units_and_all_control_origins():
    m=module();x=np.zeros((9,11));x[:,1]=1;x[:,0]=np.arange(9)*.1;x[:,5]=np.arange(9)*.2
    r=m.rollout(x,np.zeros((8,6)),None,None,None,'persistence',2)
    assert r['origins']==3 and r['failed_origins']==0
    np.testing.assert_allclose(r['endpoint_rmse'],[.4,0,.8/np.sqrt(3),0],atol=1e-12)
    assert len(r['per_origin_endpoint_squared_error'])==3


def test_rollout_never_uses_intermediate_truth_and_failure_invalidates_aggregate():
    m=module();x=np.zeros((9,11));x[:,1]=1
    class Operator:
        mean=np.zeros(25);scale=np.ones(25)
        def advance_lift(self,z,u):
            out=z.copy();out[:,7:13]+=u;return out
    context=PhysicalContext(20,[.4,.8,1],[0,0,.01],.02,1)
    u=np.ones((8,6))*.1
    a=m.rollout(x,u,Operator(),'linear',context,'projected',4)
    x[1:-1,0]=7
    b=m.rollout(x,u,Operator(),'linear',context,'projected',4)
    np.testing.assert_allclose(a['final_predictions'],b['final_predictions'])
    assert a['path_rmse']!=b['path_rmse']
    u[4]=200
    bad=m.rollout(x,u,Operator(),'linear',context,'projected',4)
    assert bad['failed_origins']==1 and bad['endpoint_rmse'] is None and bad['path_rmse'] is None


def test_sign_invariant_quaternion_metric():
    m=module();a=np.zeros((2,11));a[:,1]=1;b=a.copy();b[:,1]=-1
    np.testing.assert_allclose(m.squared_errors(a,b),0,atol=1e-12)
