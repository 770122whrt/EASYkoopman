import copy
import pytest


def pair():
    common=dict(configuration='base',mode='simulation_effect',controls=120,
                seed=19500,reference=[5.48,1,0,0,0],reference_id='depth-v65',model_key='nonlinear__pooled')
    a=dict(status='physical_and_causal_replay_passed',case=dict(common,case_id='a',controller='feedback'),
           physical_steps=240,metrics=dict(normalized_tracking_score=1.,depth_rmse_m=.02,
           attitude_rmse_rad=.01,mpc_activations=0))
    b=copy.deepcopy(a);b['case'].update(case_id='b',controller='mpc')
    b['metrics'].update(normalized_tracking_score=.8,depth_rmse_m=.018,mpc_activations=3)
    return a,b


def test_benefit_requires_qualified_matching_arms_and_actual_changed_commands():
    from workflows.compare_effects_v65 import classify_pair
    a,b=pair()
    assert classify_pair(a,b,command_difference=.001)['verdict']=='benefit_in_this_scenario'
    assert classify_pair(a,b,command_difference=0)['verdict']=='no_distinct_mpc_intervention'


@pytest.mark.parametrize('bad',['failed','length','reference','activation','controller'])
def test_reject_invalid_pair(bad):
    from workflows.compare_effects_v65 import classify_pair
    a,b=pair()
    if bad=='failed':b['status']='failed'
    if bad=='length':b['physical_steps']=10
    if bad=='reference':b['case']['reference'][0]=5.49
    if bad=='activation':b['metrics']['mpc_activations']=0
    if bad=='controller':a['case']['controller']='mpc'
    with pytest.raises(ValueError):classify_pair(a,b,command_difference=.001)


def test_small_gain_and_regression_are_not_promoted():
    from workflows.compare_effects_v65 import classify_pair
    a,b=pair();b['metrics']['normalized_tracking_score']=.99
    assert classify_pair(a,b,command_difference=.001)['verdict']=='no_material_benefit_in_this_scenario'
    b['metrics']['normalized_tracking_score']=1.2
    assert classify_pair(a,b,command_difference=.001)['verdict']=='worse_in_this_scenario'
