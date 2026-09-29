from copy import deepcopy
from test_free_water_v26 import sample
from test_free_water_runtime_v26 import corners
import pytest


def trace_row():
    row=sample();row['backend_after_physics']['cache_sim_timestamp_s']=.02
    geom={'body_path':'/body','body_local_corners_m':corners().tolist(),'ground_world_z_m':0,'minimum_clearance_m':.1}
    row['contact_after_physics_v26']={'normal_force_world_n':[[0,0,0]],'body_paths':['/body'],
                                     'physics_dt_s':.01,'sample_timestamp_s':.02}
    return row,geom


def test_reduction_uses_raw_force_even_if_stored_status_says_pass():
    from workflows.validate_free_water_v26 import contact_screen
    row,g=trace_row();row['free_water_screen_v26']={'screen_pass':True}
    row['contact_after_physics_v26']['normal_force_world_n'][0][2]=3
    assert not contact_screen(row,g)['screen_pass']


@pytest.mark.parametrize('field,value',[('sample_timestamp_s',.01),('body_paths',['/wrong']),
                                       ('physics_dt_s',.02),('normal_force_world_n',[[float('nan'),0,0]])])
def test_contact_timestamp_identity_or_nonfinite_force_rejected(field,value):
    from workflows.validate_free_water_v26 import contact_screen
    row,g=trace_row();row['contact_after_physics_v26'][field]=value
    with pytest.raises(ValueError,match='free_water_contact_binding'):contact_screen(row,g)


def test_failed_simapp_trace_not_accepted_despite_exit_zero():
    from workflows.validate_free_water_v26 import validate_trace
    from workflows.free_water_microtrace_v26 import cases
    with pytest.raises(ValueError,match='free_water_trace_status'):
        validate_trace({'status':'failed_free_water_diagnostic'},cases()[0],'a'*40,'.')


def test_runtime_screen_rejects_small_geometric_clearance_before_actor_contact():
    from workflows.validate_free_water_v26 import contact_screen
    row,g=trace_row();row['backend_after_physics']['transform_actor_world_xyzw'][0][2]=.3
    assert 'hull_clearance_below_minimum' in contact_screen(row,g)['reasons']
