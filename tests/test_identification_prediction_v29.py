import numpy as np
import pytest


def test_conditional_rollout_scores_all_excitation_origins_and_never_injects_truth():
    from workflows.identification_prediction_v29 import conditional_rollout
    x=np.tile([5.5,1,0,0,0,0,0,0,0,0,0],(641,1)).astype(float)
    x[:,5]=np.arange(641)*.01
    inputs=np.zeros((640,6));inputs[:,0]=1.2
    def exact(state,a,context):
        y=state.copy();y[:,5]+=a[:,0]/120;return y
    r=conditional_rollout(x,inputs,exact,None,20)
    assert r['origins']==173 and r['origin_control_indices'][0]==128
    assert max(r['endpoint_rmse'])<1e-6
    def wrong(state,a,context):return state
    r=conditional_rollout(x,inputs,wrong,None,20)
    assert r['endpoint_rmse'][2]==pytest.approx(.4/np.sqrt(3))
    assert r['conditional_future_recorded_inputs'] is True


def test_one_failed_origin_invalidates_aggregate_instead_of_survivor_mean():
    from workflows.identification_prediction_v29 import conditional_rollout
    x=np.tile([5.5,1,0,0,0,0,0,0,0,0,0],(641,1)).astype(float)
    def bad(state,a,context):
        y=state.copy();y[0,0]=np.nan;return y
    r=conditional_rollout(x,np.zeros((640,6)),bad,None,1)
    assert not r['complete_aggregate'] and r['endpoint_rmse'] is None and r['failed_origins']>0


def test_policy_forecast_reconstructs_origin_clock_and_uses_predicted_feedback():
    from workflows.identification_prediction_v29 import policy_forecast
    from workflows.actuator_replay_v28 import Float32PWMActuatorState
    from workflows.control_seam_v23 import ControlKernel
    from workflows.workpoint_v27 import mechanics
    from koopman.projected_edmd_v24 import PhysicalContext
    m=mechanics('base');c=PhysicalContext(m['mass_kg'],m['inertia_kg_m2'],m['cob_m'],m['volume_m3'],1.)
    x=np.array([5.5,1,0,0,0,0,0,0,0,0,0],dtype=float);history=np.zeros((256,4))
    seen=[]
    def predictor(state,a,context):
        seen.append(a.copy());y=state.copy();y[:,8]+=.01;return y
    r=policy_forecast(x,history,np.zeros((2,4)),'base',c,predictor)
    assert r['predictions'].shape==(4,11) and r['commands'].shape==(2,4)
    assert not np.array_equal(r['commands'][0],r['commands'][1])
    k=ControlKernel('base');e=Float32PWMActuatorState(k.env._num_thrusters,tau=k.tau,dt=1/120,clock='float32_accumulated_v1')
    for u in history:e.advance_pwm(k.command(u,pre_tam=True)['pwm'])
    assert r['origin_actuator_time_s']==e.elapsed_time
    with pytest.raises(ValueError):policy_forecast(x,history[:-1],np.zeros((2,4)),'base',c,predictor)
