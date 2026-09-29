from types import SimpleNamespace
import numpy as np
import pytest


def test_coverage_exposes_constant_and_collinear_columns():
    from workflows.identification_coverage_v29 import matrix_audit
    x=np.arange(8,dtype=float)
    r=matrix_audit(np.c_[np.zeros(8),x,2*x],['zero','first','duplicate'])
    assert r['active_columns']==['first','duplicate'] and r['centered_rank']==1
    assert r['constant_columns']==['zero']
    assert r['maximum_abs_active_correlation']==pytest.approx(1)
    with pytest.raises(ValueError):matrix_audit([[np.nan]],['invalid'])


def test_coverage_rejects_calibration_role_missing_or_duplicate_fit_inventory():
    from workflows.identification_coverage_v29 import validate_fit_inventory
    from workflows.identification_protocol_v29 import cases
    qs=[q for q in cases() if q['role']=='fit']
    episodes=[SimpleNamespace(case=q,acceptance={'training_eligible':True},source_commit='a'*40) for q in qs]
    validate_fit_inventory(episodes)
    for altered in (episodes[:-1],episodes+[episodes[0]],
                    [SimpleNamespace(case=cases()[0],acceptance={'training_eligible':False},source_commit='a'*40)]+episodes[1:]):
        with pytest.raises(ValueError,match='identification_fit_inventory'):validate_fit_inventory(altered)
