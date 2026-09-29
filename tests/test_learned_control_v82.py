"""Learned control wiring and fail-closed identity; no simulator claims."""
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest
from test_prepared_projected_v40 import context, states
from test_preview_trace_v80 import legacy_traces,mpc_development_fixture
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS

ROOT=Path(__file__).resolve().parents[1]
MODEL=Path(os.environ.get('V81_MODEL_DIRECTORY',str(ROOT/
    'docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion')))/'pooled__learned_0.1.json'


def api():
    return importlib.import_module('koopman.preview_solver_v82')


@pytest.fixture
def artifact(tmp_path):
    path=tmp_path/'model.json';path.write_bytes(MODEL.read_bytes())
    return path,hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope='module')
def common_assets():
    if os.environ.get('EASYUUV_V80_TEST_ASSETS'):
        from workflows.runtime_assets_v56 import AssetLocation, load_assets
        return load_assets(AssetLocation(os.environ['EASYUUV_V80_TEST_ASSETS'],'.','assets/v38/inputs',
            '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    from workflows.diagnose_separation_v79 import prepare
    return prepare(ROOT)[1]


def test_two_arms_load_same_record_but_use_different_prediction_matrices(artifact):
    path,sha=artifact;a=api();loaded=a.load_model(path,sha);c=context()
    learned=a.make_predictor('learned_velocity',loaded,c)
    physical=a.make_predictor('matched_physics',loaded,c)
    np.testing.assert_array_equal(learned._symbolic_base._matrix[:,10:16],loaded.record['velocity_matrix'])
    assert np.max(abs(learned._symbolic_base._matrix[:,10:16]-physical._symbolic_base._matrix[:,10:16]))>1e-6
    x=states(4);u=np.zeros((4,6))
    assert np.max(abs(learned(x,u,c)-physical(x,u,c)))>1e-8
    li=a.model_identity(loaded,'learned_velocity');pi=a.model_identity(loaded,'matched_physics')
    assert li['prediction_artifact_sha256']==pi['prediction_artifact_sha256']==sha
    assert li['prediction_content_sha256']!=pi['prediction_content_sha256']
    assert not li['representation_benefit_claimed'] and not li['v38_model_admission_claimed']


def test_external_file_hash_and_internal_content_hash_are_both_checked(artifact):
    path,sha=artifact;a=api()
    with pytest.raises(ValueError,match='artifact_hash'):a.load_model(path,'0'*64)
    r=json.loads(path.read_text());r['velocity_matrix'][-1][0]+=.01
    path.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='artifact_hash'):a.load_model(path,sha)
    with pytest.raises(ValueError,match='hash'):
        a.load_model(path,hashlib.sha256(path.read_bytes()).hexdigest())


def test_nonpooled_model_is_not_admitted_even_with_valid_hash(tmp_path):
    from test_learned_velocity_v81 import record
    p=tmp_path/'subset.json';p.write_text(json.dumps(record()))
    with pytest.raises(ValueError,match='pooled_fit_inventory'):
        api().load_model(p,hashlib.sha256(p.read_bytes()).hexdigest())


def test_old_model_names_are_not_silently_aliased(artifact):
    p,h=artifact;a=api();loaded=a.load_model(p,h)
    with pytest.raises(ValueError,match='model_kind'):a.make_predictor('projected_koopman',loaded,context())
    with pytest.raises(ValueError,match='model_kind'):a.case_spec('base','identified_physics',False,'pitch_pos')


@pytest.mark.parametrize('kind',['learned_velocity','matched_physics'])
def test_worker_constructor_uses_corresponding_new_predictor(artifact,monkeypatch,kind):
    p,h=artifact;a=api();captured={}
    class MPC:
        def __init__(self,domain,predictor,**kwargs):captured['predictor']=predictor;captured['settings']=kwargs
    monkeypatch.setitem(sys.modules,'koopman.continuous_mpc_v80',SimpleNamespace(ContinuousMPC=MPC))
    loaded=a.load_model(p,h)
    domain=SimpleNamespace(fit_sources=tuple(list(loaded.record['physical_prior']['fit_episode_hashes'].items())[:3]))
    engine=a._Engine(dict(domain=domain,context=context(),kind=kind,learned_model=str(p),learned_sha256=h,
        horizon=20,weights=None))
    expected=a.make_predictor(kind,a.load_model(p,h),context())
    np.testing.assert_array_equal(captured['predictor']._symbolic_base._matrix,expected._symbolic_base._matrix)
    assert captured['settings']['solve_seconds']==30. and captured['settings']['horizon']==20


def test_v80_physical_planning_gate_is_reused_without_relaxation(artifact):
    from koopman.preview_solver_v80 import ExactChecker
    a=api();assert a.ExactChecker is ExactChecker
    assert a.PLANNING_MARGIN==3e-6 and a.OPTIMIZER_MARGIN==4e-6


@pytest.mark.parametrize('kind',['learned_velocity','matched_physics'])
def test_parent_checker_and_worker_spec_share_the_authenticated_record(artifact,common_assets,monkeypatch,kind):
    p,h=artifact;a=api();captured={}
    class Transport:
        def __init__(self,spec):captured.update(spec)
    monkeypatch.setattr(a,'ProcessTransport',Transport)
    c=common_assets.context('base')
    solver=a.create_solver(common_assets.domains['base'],c,kind,
        learned_model=p,learned_sha256=h,preview_enabled=False)
    expected=a.make_predictor(kind,a.load_model(p,h),c)
    np.testing.assert_array_equal(solver.checker.predictor._symbolic_base._matrix,expected._symbolic_base._matrix)
    assert captured['kind']==kind and captured['learned_sha256']==h
    assert Path(captured['learned_model'])==p.resolve() and 'fitted' not in captured


def test_model_fit_sources_must_match_common_support_inventory(artifact,common_assets):
    from koopman.learned_velocity_v81 import seal_record
    p,h=artifact;a=api();r=json.loads(p.read_text())
    first=next(iter(r['physical_prior']['fit_episode_hashes']))
    r['physical_prior']['fit_episode_hashes'][first]='0'*64
    p.write_text(json.dumps(seal_record(r)));loaded=a.load_model(p,hashlib.sha256(p.read_bytes()).hexdigest())
    with pytest.raises(ValueError,match='common_fit_sources'):
        a.verify_support(loaded,common_assets)


def test_validator_rejects_wrong_proxy_before_attempting_physics(artifact,common_assets):
    from workflows.validate_learned_v82 import validate
    p,h=artifact;a=api();loaded=a.load_model(p,h);assets=common_assets
    case=a.case_spec('base','learned_velocity',False,'pitch_pos')
    identity=a.model_identity(loaded,'learned_velocity');identity['symbolic_proxy']='projected_koopman'
    d=dict(status='completed_pending_independent_acceptance',cleanup_errors=[],
        cleanup_completed={'environment':True,'simulation_app':True},native_alias_release={'robot_released':True},
        model_fits=0,real_time_qualified=False,timing_mode='synchronous_nonrealtime',case=case,
        model={'kind':'learned_velocity','model_identity':identity})
    with pytest.raises(ValueError,match='model_identity'):
        validate(d,assets,0,learned_model=p,learned_sha256=h)


def learned_development_trace(legacy_traces,artifact,common_assets):
    """In-memory negative-test fixture only; never written as a new run."""
    p,h=artifact;a=api();loaded=a.load_model(p,h)
    d=mpc_development_fixture(legacy_traces)
    d['schema']='learned-control-v82'
    d['case']=a.case_spec('base','learned_velocity',False,'pitch_pos')
    identity=a.model_identity(loaded,'learned_velocity')
    d['model'].pop('frozen_parameter_source_sha256')
    d['model'].update(kind='learned_velocity',model_identity=identity,
        common_support_model_sha256=common_assets.model_sha256,
        prediction_artifact_sha256=h,prediction_content_sha256=identity['prediction_content_sha256'])
    return d


@pytest.mark.parametrize('mutation,reason',[('actual_pwm','observed_pwm_deadzone_margin'),
    ('native_exit','native_or_status'),('common_hash','model_binding'),
    ('prediction_hash','prediction_model_binding'),('clock','clock'),('receipt','history_digest')])
def test_new_model_trace_keeps_physical_and_identity_gates(legacy_traces,artifact,common_assets,mutation,reason):
    from workflows.validate_learned_v82 import validate
    p,h=artifact;d=learned_development_trace(legacy_traces,artifact,common_assets);exit_code=0
    if mutation=='actual_pwm':
        v=float(np.float32(.02))-1.99e-6
        d['substeps'][0]['command']['_last_motor_values_raw'][0][0]=v
        d['substeps'][0]['command']['telemetry']['motor_pwm_n'][0][0]=v
    elif mutation=='native_exit':exit_code=139
    elif mutation=='common_hash':d['model']['common_support_model_sha256']=h
    elif mutation=='prediction_hash':d['model']['prediction_artifact_sha256']=common_assets.model_sha256
    elif mutation=='clock':d['substeps'][0]['backend_after_physics']['cache_sim_timestamp_s']+=.1
    elif mutation=='receipt':d['substeps'][0]['execution_ack_v55']['receipt']['history_digest']='0'*64
    with pytest.raises(ValueError,match=reason):
        validate(d,common_assets,exit_code,learned_model=p,learned_sha256=h)


@pytest.mark.parametrize('configuration',SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('ridge',['0.001','0.1'])
def test_matched_physics_equals_old_identified_for_same_origin_eighty_steps(common_assets,configuration,ridge):
    from koopman.command_state_v39 import CausalCommandState
    from koopman.physical_control_v76 import PhysicalPredictor
    from workflows.identify_sparse_world_v30 import from_record
    path=MODEL.with_name(f'pooled__learned_{ridge}.json');a=api()
    loaded=a.load_model(path,hashlib.sha256(path.read_bytes()).hexdigest());a.verify_support(loaded,common_assets)
    original=from_record(json.loads(common_assets.model_path.read_text()))
    prior=from_record(loaded.record['physical_prior'])
    np.testing.assert_array_equal(prior.matrix[:,10:16],original.matrix[:,10:16])
    np.testing.assert_array_equal(prior.damping,original.damping)
    np.testing.assert_array_equal(prior.quadratic,original.quadratic)
    c=common_assets.context(configuration)
    new=a.make_predictor('matched_physics',loaded,c)
    old=PhysicalPredictor(original,c,identified=True)
    live=CausalCommandState(configuration,c,episode_id='v82_parity',zero_rotor_reset_verified=True)
    command=np.array([.013,-.017,0.,.31],dtype=np.float32)
    for i in range(12):live.record_issued(command,physics_index=i,episode_id='v82_parity')
    origin=live.snapshot(configuration=configuration,context=c,origin_control=6,episode_id='v82_parity')
    q=np.array([1.,.003,-.004,.002]);q/=np.linalg.norm(q)
    state=np.r_[5.5,q,[.003,-.002,.004,.004,-.003,.002]]
    controls=np.tile(command,(20,1));controls[:,0]+=np.linspace(0,.002,20,dtype=np.float32)
    exact0=origin.forecast(state,np.repeat(controls,2,axis=0),old)
    exact1=origin.forecast(state,np.repeat(controls,2,axis=0),new)
    assert exact0['complete'] and exact1['complete'] and exact1['predictions'].shape==(80,11)
    np.testing.assert_array_equal(exact0['predictions'],exact1['predictions'])
    assert live.physics_index==12
