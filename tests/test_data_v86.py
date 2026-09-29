import importlib
import pytest


def api():
    assert importlib.util.find_spec('workflows.disturbance_data_v86'), 'v86 data admission missing'
    return importlib.import_module('workflows.disturbance_data_v86')


def test_old_trace_or_faked_pending_receipt_is_rejected():
    m=api()
    for report in ({}, {'schema':'disturbance-data-v86','status':'failed'},
                   {'schema':'disturbance-data-v86','status':'completed_pending_independent_acceptance'}):
        with pytest.raises(ValueError,match='v86_trace'):
            m.validate_trace(report,{},'0'*64)


def test_frozen_physics_has_explicit_pre_disturbance_identity():
    m=api();record,physical=m.frozen_physics()
    assert record['family']=='nonlinear'
    assert physical.kind=='identified_physics'
    assert len(m.PHYSICAL_SHA256)==64
