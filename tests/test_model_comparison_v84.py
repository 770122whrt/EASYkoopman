import importlib
import numpy as np
from test_prepared_projected_v40 import context


def api():
    assert importlib.util.find_spec('workflows.compare_models_v84'), 'comparison runner missing'
    return importlib.import_module('workflows.compare_models_v84')


def test_rollout_counts_failure_without_truth_or_silent_fallback():
    m=api();x=np.array([5.5,1,0,0,0,0,0,0,0,0,0.])
    def fail_after_one(x,a,c):
        y=x.copy();y[:,0]+=1.5
        return y
    result=m.forecast(fail_after_one,x,np.zeros((5,6)),context())
    assert len(result['trajectory'])==1
    assert result['failure']=='forecast_state_envelope'


def test_lifted_rollout_carries_hidden_memory_independent_of_readout():
    m=api()
    from koopman.lifted_propagation_v84 import PreparedLifted,feature_names
    d=len(feature_names());A=np.eye(d);B=np.zeros((d,12))
    hidden=d-2;A[4,hidden]=1;A[hidden,-1]=.01
    p=PreparedLifted(A,B,context());x=np.array([5.5,1,0,0,0,0,0,0,0,0,0.])
    r=m.forecast(p,x,np.zeros((3,6)),context())
    np.testing.assert_allclose(np.asarray(r['trajectory'])[:,5],[0,.01,.03])
    relift=m.forecast(p,x,np.zeros((3,6)),context(),relift=True)
    np.testing.assert_allclose(np.asarray(relift['trajectory'])[:,5],0)


def test_prediction_gate_not_based_on_beating_physics_or_average_only():
    m=api();good={'complete':True,'horizon_physics':80,
                 'metrics':{'z_rmse_m':.001,'attitude_rmse_rad':.001}}
    assert m.prediction_gate([good])['eligible_body_prediction']
    bad={**good,'metrics':{'z_rmse_m':.0021,'attitude_rmse_rad':.001}}
    assert not m.prediction_gate([good,bad])['eligible_body_prediction']
    assert not m.prediction_gate([{**good,'complete':False,'metrics':None}])['eligible_body_prediction']
