import numpy as np
import pytest

from workflows.feedback_v28 import FeedbackPolicy, cases, pulse, parameters, validate_decision
from workflows.collector_exit_v28 import cleanup_preserving_failure


def state(q=None, omega=(0, 0, 0)):
    return np.r_[5.5, [1, 0, 0, 0] if q is None else q, [0, 0, 0], omega]


def test_pose_dependent_yaw_compensation_and_quaternion_sign():
    policy = FeedbackPolicy('asymmetric')
    q = np.array([np.cos(.2), np.sin(.2), 0, 0])
    a = policy.decide(state(q), np.zeros(4))
    b = policy.decide(state(-q), np.zeros(4))
    assert abs(a['restoring_torque_3_nm'][2]) > 4
    np.testing.assert_allclose(a['target_wrench_6_n_nm'][5], -a['restoring_torque_3_nm'][2])
    np.testing.assert_allclose(a['target_wrench_6_n_nm'], b['target_wrench_6_n_nm'])
    validate_decision(a, state(q), np.zeros(4), 'asymmetric')


def test_damping_opposes_rate_feedback_bounded_and_mask_respected():
    p = FeedbackPolicy('uuv4')
    d = p.decide(state(omega=(10, -10, 10)), np.zeros(4))
    a = np.asarray(d['feedback_acceleration_4'])
    assert a[0] < 0 < a[1]
    assert np.max(np.abs(a[:3])) <= parameters()['angular_feedback_limit_rad_s2']
    assert d['command_4'][2] == 0 and d['target_wrench_6_n_nm'][5] == 0


def test_controller_does_not_read_future_or_rotor_truth_and_replay_rejects_tamper():
    p = FeedbackPolicy('base'); x = state(); d = p.decide(x, np.zeros(4))
    validate_decision(d, x, np.zeros(4), 'base')
    bad = dict(d, state_available_11=state(omega=(.1, 0, 0)).tolist())
    with pytest.raises((ValueError, AssertionError)):
        validate_decision(bad, x, np.zeros(4), 'base')
    bad = dict(d, target_wrench_6_n_nm=[0]*6)
    with pytest.raises((ValueError, AssertionError)):
        validate_decision(bad, x, np.zeros(4), 'base')


def test_common_protocol_new_seeds_and_complete_startup():
    qs = cases()
    assert len(qs) == 16 and len({q['seed'] for q in qs}) == 16
    for q in qs:
        assert q['role'] == 'calibration' and not q['training_eligible']
        a = pulse(q)
        assert a.shape == (q['intervals'], 4) and not a[:128].any()
        assert q['seed'] >= 8530
        if q['configuration'] == 'uuv4': assert not a[:, 2].any()


@pytest.mark.parametrize('failure', [ValueError('motion_limit'), KeyboardInterrupt(), SystemExit(7)])
def test_cleanup_systemexit_zero_cannot_replace_collection_failure(failure):
    seen = []
    def close():
        seen.append(True)
        raise SystemExit(0)
    with pytest.raises(type(failure)) as caught:
        cleanup_preserving_failure(failure, [close])
    assert caught.value is failure and seen == [True]


def test_cleanup_runs_all_and_propagates_cleanup_failure():
    seen = []
    def broken(): raise RuntimeError('close_failed')
    with pytest.raises(RuntimeError, match='close_failed'):
        cleanup_preserving_failure(None, [broken, lambda: seen.append(True)])
    assert seen == [True]
    cleanup_preserving_failure(None, [lambda: None])
    def exit_zero(): raise SystemExit(0)
    cleanup_preserving_failure(None, [exit_zero])


def test_collector_refuses_fit_role_before_creating_output(tmp_path):
    from workflows.collect_feedback_v28 import run_case
    with pytest.raises(ValueError, match='feedback_fixed_case'):
        run_case(dict(cases()[0], role='fit'), tmp_path/'forbidden', 'a'*40, parameters())
    assert not (tmp_path/'forbidden').exists()


def test_unverified_tail_or_unknown_failure_cannot_admit_excitation():
    from workflows.run_feedback_v28 import excitation_eligible
    from workflows.validate_feedback_v28 import rejected_trace
    with pytest.raises(ValueError, match='calibration_trace_status'):
        excitation_eligible({'status': 'unknown', 'tail': {'eligible_for_excitation': True}}, 'a'*40, '.')
    with pytest.raises(ValueError, match='calibration_rejection_unverified'):
        rejected_trace({'status': 'failed_calibration', 'exception': 'RuntimeError:CUDA'}, cases()[0], 'a'*40)


def test_cross_configuration_source_targets_have_headroom_at_cold_start():
    from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
    for name in SUPPORTED_EMBODIMENTS:
        p = FeedbackPolicy(name)
        d = p.decide(state(), np.zeros(4))
        assert validate_decision(d, state(), np.zeros(4), name), name


def test_base_small_descent_keeps_calibrated_heave_without_unrequested_height_pd():
    x = state(); x[0] = 5.497499465942383; x[7] = -.006715366616845131
    d = FeedbackPolicy('base').decide(x, np.zeros(4))
    assert d['feedback_acceleration_4'][3] == 0
    assert validate_decision(d, x, np.zeros(4), 'base')
