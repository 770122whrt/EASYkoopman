"""Repair packaging contracts; no simulator or formal approval in fixtures."""
import pytest


def test_repair_package_refuses_existing_or_outside_destination(tmp_path):
    from workflows.package_projected_repair_v38 import build
    (tmp_path/'.pytest-tmp').mkdir()
    existing=tmp_path/'.pytest-tmp/existing'; existing.mkdir()
    for target in (tmp_path/'outside', existing):
        with pytest.raises(ValueError, match='repair_package_destination'):
            build(tmp_path, tmp_path/'missing-parent', target)
    assert not (tmp_path/'outside').exists()


def test_missing_reaudit_and_tests_cannot_freeze_a_repair(tmp_path):
    from workflows.package_projected_repair_v38 import freeze
    with pytest.raises((FileNotFoundError, ValueError)):
        freeze(tmp_path)
    assert not (tmp_path/'inputs').exists()
    from workflows.package_projected_validation_repair_v38 import freeze as validation_freeze
    with pytest.raises((FileNotFoundError,ValueError)):
        validation_freeze(tmp_path)
    assert not (tmp_path/'inputs').exists()


def test_repair_may_rewire_worker_identity_but_cannot_change_any_scoring_function():
    from workflows.projected_archive_v38 import validate_audit_only_change
    name='workflows/evaluate_projected_formal_v38.py'
    old=b'def work():\n    return 1\ndef score_episode():\n    return 7\n'
    allowed=old.replace(b'return 1',b'return 2')
    validate_audit_only_change(name,old,allowed)
    for bad in (old.replace(b'return 7',b'return 8'),old+b'override = True\n'):
        with pytest.raises(ValueError,match='scientific_source'):
            validate_audit_only_change(name,old,bad)
    with pytest.raises(ValueError,match='scientific_source'):
        validate_audit_only_change('workflows/projected_adapter_v38.py',old,allowed)
