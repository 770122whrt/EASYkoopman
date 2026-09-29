"""Executed-prefix analysis authenticates evidence and never uses future states as input."""
import copy
import importlib
from pathlib import Path
import numpy as np
import pytest


def api():
    assert importlib.util.find_spec('workflows.analyze_executed_prediction_v82')
    return importlib.import_module('workflows.analyze_executed_prediction_v82')


def admitted():
    case={'configuration':'base'}
    data=dict(schema='preview-control-v80',status='completed_pending_independent_acceptance',case=case)
    acceptance=dict(status='accepted_bounded_simulation_time_closed_loop',trace_sha256='a'*64,
        case=case,physics_steps=240,actual_pwm_checks=240,backend_allocation_checks=60,
        acceptance_schema='preview-control-v80-acceptance/1')
    exit_record=dict(native_exit=0,group_stopped=True)
    return data,acceptance,exit_record


@pytest.mark.parametrize('mutation',['trace_hash','collector_exit','validator_exit','group','case','schema'])
def test_admission_rejects_unverified_or_failed_input(mutation):
    a=api();data,acceptance,collector=admitted();validator=copy.deepcopy(collector)
    if mutation=='trace_hash':acceptance['trace_sha256']='b'*64
    elif mutation=='collector_exit':collector['native_exit']=139
    elif mutation=='validator_exit':validator['native_exit']=1
    elif mutation=='group':collector['group_stopped']=False
    elif mutation=='case':acceptance['case']={'configuration':'uuv4'}
    elif mutation=='schema':acceptance['acceptance_schema']='old_unchecked'
    with pytest.raises(ValueError):a.validate_admission(data,acceptance,collector,validator,'a'*64)


def test_admission_accepts_both_versioned_full_acceptances():
    a=api();data,acceptance,exit_record=admitted()
    a.validate_admission(data,acceptance,exit_record,exit_record,'a'*64)
    data['schema']='learned-control-v82';acceptance['acceptance_schema']='learned-control-v82-acceptance/1'
    a.validate_admission(data,acceptance,exit_record,exit_record,'a'*64)


def test_error_normalizes_sign_equivalent_quaternions_and_keeps_components():
    a=api();x=np.array([[5.5,1.,0,0,0,0,0,0,0,0,0]])
    y=x.copy();y[:,1]=-.99999;y[:,5]=.1;y[:,8]=-.2
    result=a.step_errors(x,y)
    assert result['attitude_rad']==[0.]
    np.testing.assert_allclose(result['linear_velocity_norm_m_s'],[.1])
    np.testing.assert_allclose(result['angular_velocity_norm_rad_s'],[.2])
    np.testing.assert_allclose(result['velocity_component_error'][0],[ -.1,0,0,.2,0,0])


def test_prefix_forecast_receives_only_fixed_current_state_and_commands():
    a=api();calls=[];initial=np.arange(11,dtype=float);command=np.array([.01,.02,0,.2])
    class Origin:
        def forecast(self,state,commands,predictor):
            calls.append((state.copy(),commands.copy(),predictor))
            return dict(complete=True,predictions=np.tile(state,(4,1)))
    result=a.predict_prefix(Origin(),initial,command,{'a':object(),'b':object()})
    assert set(result)=={'a','b'} and len(calls)==2
    for state,commands,predictor in calls:
        np.testing.assert_array_equal(state,initial)
        np.testing.assert_array_equal(commands,np.tile(command.astype(np.float32),(2,1)))


def test_success_exit_from_another_run_is_not_accepted():
    a=api();data={'schema':'preview-control-v80','case':dict(configuration='base',
        controller='identified_physics',preview_enabled=True,task='pitch_pos')}
    collector={'command':['python','-m','workflows.collect_preview_v80','--output','/remote/another-run',
        '--configuration','base','--controller','identified_physics','--preview','on','--task','pitch_pos']}
    validator={'command':['python','-m','workflows.validate_preview_v80','--trace','/remote/expected/trace.json.gz',
        '--native-exit','0']}
    with pytest.raises(ValueError,match='native_command_binding'):
        a._native_binding(data,Path('/local/expected/trace.json.gz'),collector,validator)


def test_partial_forecast_failure_remains_in_summary():
    a=api();x=np.array([[5.5,1.,0,0,0,0,0,0,0,0,0]])
    row=dict(model='example',complete=False,completed_physics=1,
             predicted_support_violation=None,step_errors=a.step_errors(x,x))
    result=a._aggregate([row])[0]
    assert result['failed_prefixes']==1 and result['complete_prefixes']==0
    assert result['by_substep'][0]['available']==1
    assert result['by_substep'][3]['missing']==1
    assert result['by_substep'][3]['metrics']=={}


def test_analysis_records_platform_without_asserting_server_equivalence():
    result=api().analysis_platform()
    assert result['numpy']==np.__version__ and result['python'] and result['os']
    assert result['command_dtype']=='float32'
    assert result['platform_matched_to_collection_established'] is False
