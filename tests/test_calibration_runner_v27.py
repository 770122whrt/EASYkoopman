import pytest


def test_collector_rejects_noncalibration_role_before_source_or_isaac(tmp_path):
    from workflows.collect_calibration_v27 import run_case
    from workflows.workpoint_v27 import cases
    q = dict(cases()[0], role='fit')
    with pytest.raises(ValueError, match='calibration_fixed_case'):
        run_case(q, tmp_path/'forbidden', 'a'*40, {})
    assert not (tmp_path/'forbidden').exists()


def test_no_excitation_eligibility_from_unverified_json_boolean():
    from workflows.run_calibration_v27 import excitation_eligible
    with pytest.raises(ValueError, match='calibration_trace_status'):
        excitation_eligible({'status': 'unknown', 'tail': {'eligible_for_excitation': True}}, 'a'*40, '.')


def test_only_known_and_recomputed_motion_rejection_can_skip_a_case():
    from workflows.validate_calibration_v27 import rejected_trace
    from workflows.workpoint_v27 import cases
    q = cases()[0]
    with pytest.raises(ValueError, match='calibration_rejection_unverified'):
        rejected_trace({'status': 'failed_calibration', 'exception': 'RuntimeError:CUDA error'}, q, 'a'*40)


def test_budget_counts_failed_and_reserved_attempts():
    from workflows.run_calibration_v27 import reservation_seconds
    with pytest.raises(ValueError, match='calibration_process_budget'):
        reservation_seconds({'charged_seconds': 1, 'attempts': [{}]*16})
    with pytest.raises(ValueError, match='calibration_time_budget'):
        reservation_seconds({'charged_seconds': 2390, 'attempts': []})
    assert reservation_seconds({'charged_seconds': 2300, 'attempts': []}) == 100
