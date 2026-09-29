"""Reporting must keep matched tasks and count all dispatched control sources."""
import copy
import numpy as np
import pytest


@pytest.fixture
def paired_traces():
    import gzip, json, hashlib
    from pathlib import Path
    from koopman.preview_solver_v82 import load_model, model_identity
    root=Path(__file__).resolve().parents[1]
    a=json.loads(gzip.decompress((root/'docs/evidence/phase9/preview-v80-20260926/base-return/base-identified-on-r1/trace.json.gz').read_bytes()))
    path=root/'docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion/pooled__learned_0.1.json'
    loaded=load_model(path,hashlib.sha256(path.read_bytes()).hexdigest())
    b=copy.deepcopy(a);b['schema']='learned-control-v82';b['case']['controller']='learned_velocity'
    b['model']['kind']='learned_velocity';b['model']['common_support_model_sha256']=b['model'].pop('frozen_parameter_source_sha256')
    identity=model_identity(loaded,'learned_velocity');b['model']['model_identity']=identity
    for k in ('prediction_artifact_sha256','prediction_content_sha256'):b['model'][k]=identity[k]
    return a,b


@pytest.mark.parametrize('field',['identity','support_source','initial_z','initial_xy','rotor','actuator_clock','startup','geometry','flow'])
def test_pairing_rejects_confounded_model_or_plant(paired_traces,field):
    from workflows.report_koopman_v82 import check_pair
    a,b=paired_traces
    if field=='identity':b['model']['model_identity']['uses_learned_velocity_matrix']=False
    elif field=='support_source':b['model']['common_support_model_sha256']='0'*64
    elif field=='initial_z':b['reset_record']['snapshot']['state_11'][0][0]+=.1
    elif field=='initial_xy':b['reset_record']['snapshot']['backend']['transform_actor_world_xyzw'][0][0]+=.1
    elif field=='rotor':b['reset_record']['snapshot']['actuator_speed_n'][0][0]+=1
    elif field=='actuator_clock':b['reset_record']['snapshot']['_thruster_dynamics_time_s'][0]+=.1
    elif field=='startup':b['intervals'][0]['decision']['packet']['command'][0]+=.01
    elif field=='geometry':b['geometry']['body_local_corners_m'][0][0]+=.1
    elif field=='flow':b['reset_record']['snapshot']['telemetry']['fluid_velocity_world_3'][0][0]+=.1
    with pytest.raises(ValueError,match='paired_'):check_pair(a,b)


def test_pairing_rejects_task_or_preview_changes_but_allows_model_identity(paired_traces):
    from workflows.report_koopman_v82 import check_pair
    a,b=paired_traces
    check_pair(a,b)
    b['case']['preview_enabled']=False
    with pytest.raises(ValueError,match='paired_case'):check_pair(a,b)
    b['case']['preview_enabled']=True;b['case']['reference'][0]=5.6
    with pytest.raises(ValueError,match='paired_case'):check_pair(a,b)


def test_actual_cost_and_effort_use_physics_time_not_solver_wall_time():
    from workflows.report_koopman_v82 import actual_metrics
    from workflows.protocol_v77 import settings
    from dataclasses import asdict
    x=[5.52,1,0,0,0,0,0,0,0,0,0];u=[0,0,0,.2]
    rows=[dict(state_after_physics_11=[x]) for _ in range(240)]
    intervals=[dict(decision=dict(packet=dict(command=u)),whole_cycle_wall_ms=99999) for _ in range(60)]
    d=dict(case=dict(configuration='base',reference=[5.5,1,0,0,0]),substeps=rows,intervals=intervals,
        model=dict(weights=asdict(settings('depth4_h20')['weights'])),
        solve_audit=[dict(status='preview_retained',selected_reference='preview',solver=None)])
    m=actual_metrics(d)
    assert m['normalized_tracking_score']==pytest.approx(1.)
    assert m['control_squared_integral']==pytest.approx(.08)
    assert m['actual_objective']==pytest.approx(4*.02**2*3+.01*.08+.05*.04/60)
    assert m['cycle_median_ms']==99999
    assert m['selected_reference_counts']=={'preview':1}
    assert m['nlp_return_status_counts']=={'not_returned':1}
