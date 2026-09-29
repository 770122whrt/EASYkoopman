"""Analysis wiring tests use synthetic episodes only; no experimental evidence."""
import copy
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np
import pytest

from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
from koopman.projected_edmd_v24 import PhysicalContext
from workflows.projected_protocol_v38 import cases
from workflows.projected_evaluation_v38 import PATHS
from workflows.workpoint_v27 import mechanics


def fixture():
    q = cases('validation')[0]
    m = mechanics(q['configuration'])
    context = PhysicalContext(m['mass_kg'], m['inertia_kg_m2'], m['cob_m'], m['volume_m3'],
                              EMBODIMENT_CONFIGS[q['configuration']]['drag_multiplier'])
    x = np.tile([5.5, 1., 0., 0., 0., 0., 0., 0., 0., 0., 0.], (1025, 1))
    return SimpleNamespace(case=q, context=context, states=x, arrays={'issued_control': np.zeros((1024, 4))},
        acceleration=np.zeros((1024, 6)), trace_sha256='a'*64, source_commit='b'*40,
        acceptance=dict(status='identification_semantics_passed', role='validation', run_id=q['run_id'],
            source_commit='b'*40, training_eligible=False))


def test_worker_wires_48_records_with_all_origins_and_no_future_policy_truth(monkeypatch, tmp_path):
    import workflows.evaluate_projected_formal_v38 as module
    from workflows.projected_prediction_v38 import replay_planned_inputs
    e = fixture()
    cache = replay_planned_inputs(np.zeros((0,4)), np.zeros((512,4)), 'base', e.context, origin_control=0)
    e.acceleration = cache['acceleration']
    e.arrays.update(pwm=cache['pwm'], causal_rotor_speed=np.vstack([np.zeros(8), cache['rotor_speed']]),
                    actuator_time_s=np.r_[0., cache['physics_time_s']])
    predictors = [(f, s, lambda x, a, c: x.copy()) for f, s in PATHS]
    monkeypatch.setattr(module, 'load_predictors', lambda *args: predictors)
    seen = []
    def policy(initial_state, history, external, configuration, context, predictor, *, deadline):
        assert initial_state.shape == (11,) and history.shape == (256, 4) and external.shape == (128, 4)
        seen.append(1)
        return dict(complete=True, failure=None, predictions=np.tile(initial_state, (256,1)),
            commands=np.zeros((128,4)), origin_actuator_time_s=float(cache['physics_time_s'][255]),
            future_inputs='generated_from_own_predicted_state_and_fixed_external_drive')
    monkeypatch.setattr(module, 'policy_forecast', policy)
    manifest = dict(models={f+'__'+s: {'sha256':'c'*64} for f in ('nonlinear','linear') for s in ('pooled','heldout-base')},
                    execution_sha256={'fixture_only':'d'*64})
    result = module.score_episode(e, Path.cwd(), manifest, tmp_path/'case', deadline=time.monotonic()+60)
    rows = result['scores']
    assert len(rows) == 48 and len(seen) == 6
    assert all(r['trace_sha256'] == 'a'*64 and r['complete_aggregate'] for r in rows)
    assert {r['origins'] for r in rows if r['mode']=='conditional_projected'} == {384,365,325,257}
    assert all(r['origin_control']==0 for r in rows if r['mode']=='full_episode')
    assert all(r['origin_control']==128 for r in rows if r['mode']=='policy_self_recurrence')
    assert result['model_fits']==0
    # Independent code replays conditional origins and scores saved full/policy
    # arrays. Predictor loading/policy remain synthetic test doubles above.
    from workflows.audit_projected_v38 import audit_case
    assert audit_case(e, tmp_path/'case', Path.cwd(), manifest, deadline=time.monotonic()+60) == 48
    stored = module.read(tmp_path/'case/scores.json')
    stored[0]['endpoint_rmse'][0] += .01
    module.dump(tmp_path/'case/scores.json', stored)
    with pytest.raises(ValueError, match='formal_independent_metric'):
        audit_case(e, tmp_path/'case', Path.cwd(), manifest, deadline=time.monotonic()+60)


def test_wrong_role_shape_and_nonheld_command_are_rejected_before_output(tmp_path):
    from workflows.evaluate_projected_formal_v38 import score_episode
    for kind in ('role','shape','held'):
        e = fixture()
        if kind=='role': e.case=dict(e.case,role='fit')
        elif kind=='shape':e.states=e.states[:-1]
        else:e.arrays['issued_control'][1,0]=.1
        with pytest.raises(ValueError):
            score_episode(e, Path.cwd(), {}, tmp_path/kind, deadline=time.monotonic()+60)
        assert not (tmp_path/kind).exists()


def test_success_requires_native_zero_and_complete_bound_worker_result():
    from workflows.evaluate_projected_formal_v38 import verify_worker_result
    q=cases('validation')[0]
    record=dict(status='completed_projected_case',case=q,source_commit='a'*40,freeze_sha256='b'*64,
                model_manifest_digest='c'*64,model_fits=0,scores=[{}]*48)
    # Missing score identities cannot be hidden behind a claimed count.
    with pytest.raises(ValueError):verify_worker_result(0,record,q,'a'*40,'b'*64,'c'*64)
    for native in (1,-9):
        with pytest.raises(ValueError):verify_worker_result(native,record,q,'a'*40,'b'*64,'c'*64)


def test_parallel_limits_are_exactly_bounded():
    from workflows.evaluate_projected_formal_v38 import validate_workers
    for workers in (1,2,4):assert validate_workers(workers)==workers
    for workers in (0,5,True,1.0):
        with pytest.raises(ValueError):validate_workers(workers)
