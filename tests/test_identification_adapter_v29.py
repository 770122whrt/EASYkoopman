import copy
import numpy as np
import pytest


def fixture_rows():
    from workflows.control_seam_v23 import ControlKernel
    k=ControlKernel('base')
    u=np.array([[0,0,0,.1],[.01,-.01,0,.2]],dtype=np.float32)
    x=np.tile([5.5,1,0,0,0,0,0,0,0,0,0],(5,1)).astype(float)
    x[:,0]=5.5+np.arange(5)*.001
    data={'observed_start_boundary':{'state_11':[x[0].tolist()], 'actuator_speed_n':[[0]*k.env._num_thrusters]},
          'decisions':[{'interval':i,'command_4':a.tolist()} for i,a in enumerate(u)],
          'substeps':[{'control_index':i//2,'reset_generation':[1],
                       'before':{'state_11':[x[i].tolist()]},
                       'state_after_physics_11':[x[i+1].tolist()]} for i in range(4)]}
    return data,k,u,x


def test_physics_rows_keep_order_and_command_only_actuator_history():
    from workflows.identification_adapter_v29 import causal_arrays
    d,k,u,x=fixture_rows();a=causal_arrays(d,k)
    np.testing.assert_array_equal(a['states'],x)
    np.testing.assert_array_equal(a['issued_control'],np.repeat(u,2,axis=0))
    assert a['causal_rotor_speed'].shape==(5,k.env._num_thrusters)
    assert not a['causal_rotor_speed'][0].any()
    assert a['actuator_time_s'].shape==(5,) and a['actuator_time_s'][0]==0
    assert a['actuator_time_s'][1]==float(np.float32(1/120))
    assert not np.array_equal(a['causal_rotor_speed'][1],a['causal_rotor_speed'][2])
    for i,speed in enumerate(a['causal_rotor_speed'][1:]):
        np.testing.assert_allclose(a['wrench'][i],k.B.numpy()@(k.env.cfg.rotor_constant*np.abs(speed)*speed))
    assert not a['states'].flags.writeable


def test_future_targets_and_truth_rotors_cannot_change_causal_inputs():
    from workflows.identification_adapter_v29 import causal_arrays
    d,k,u,x=fixture_rows();a=causal_arrays(d,k)
    other=copy.deepcopy(d)
    other['substeps'][-1]['state_after_physics_11'][0][0]+=100
    for row in other['substeps']:
        row['command']={'actuator_speed_n':[[999]*k.env._num_thrusters]}
    b=causal_arrays(other,k)
    assert a['states'][-1,0]!=b['states'][-1,0]
    for field in ('issued_control','pwm','causal_rotor_speed','actuator_time_s','wrench'):
        np.testing.assert_array_equal(a[field],b[field])


@pytest.mark.parametrize('corruption',['gap','reset','nonzero_initial','decision_order','missing_tick'])
def test_adapter_rejects_broken_clock_history_or_initialization(corruption):
    from workflows.identification_adapter_v29 import causal_arrays
    d,k,u,x=fixture_rows()
    if corruption=='gap':d['substeps'][1]['before']['state_11'][0][0]+=1
    elif corruption=='reset':d['substeps'][2]['reset_generation']=[2]
    elif corruption=='nonzero_initial':d['observed_start_boundary']['actuator_speed_n'][0][0]=1
    elif corruption=='decision_order':d['decisions'][1]['interval']=0
    else:d['substeps'].pop()
    with pytest.raises(ValueError,match='identification_'):causal_arrays(d,k)


def test_old_calibration_identity_and_role_relabel_cannot_enter_new_adapter(tmp_path):
    from workflows.identification_adapter_v29 import adapt_trace
    from workflows.identification_protocol_v29 import cases
    q=next(q for q in cases() if q['role']=='fit')
    with pytest.raises(ValueError,match='identification_'):
        adapt_trace({'status':'completed_calibration_pending_acceptance'},q,'a'*40,'b'*64,tmp_path)


def test_collector_rejects_foreign_case_before_importing_isaac_or_writing(tmp_path):
    from workflows.collect_identification_v29 import run_case
    from workflows.identification_protocol_v29 import cases
    from workflows.feedback_v28 import parameters
    with pytest.raises(ValueError,match='identification_case'):
        run_case(dict(cases()[0],role='test'),tmp_path/'forbidden','a'*40,parameters())
    assert not (tmp_path/'forbidden').exists()


@pytest.mark.parametrize('field,value',[('drag_multiplier',[9]),('dynamic_viscosity_pa_s',.5)])
def test_single_physical_context_rejects_changed_hydrodynamics(field,value):
    from workflows.validate_identification_v29 import validate_hydrodynamics
    from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
    good={'drag_multiplier':[EMBODIMENT_CONFIGS['long_body'].get('drag_multiplier',1.)],
          'dynamic_viscosity_pa_s':.001306}
    validate_hydrodynamics(good,'long_body')
    bad=dict(good);bad[field]=value
    with pytest.raises(ValueError,match='identification_hydrodynamics'):
        validate_hydrodynamics(bad,'long_body')
