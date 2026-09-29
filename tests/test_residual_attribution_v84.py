import numpy as np
import pytest

from workflows.diagnose_residual_v84 import decompose, source_activation


def test_alignment_and_overshoot_distinguish_harmful_correction():
    ep=np.array([[1.,1.,1.], [1.,1.,1.]])
    parts={'aligned':np.array([[.5,-.5,3.],[.5,-.5,3.]])}
    result=decompose(ep,parts,np.ones(2))
    np.testing.assert_allclose(result['delta_mse'],[-.75,1.25,3.])
    np.testing.assert_allclose(result['error_dot_correction'],[.5,-.5,3.])
    assert result['identity_max_abs'] < 1e-14


def test_group_allocation_includes_cross_terms_and_weights():
    ep=np.array([[1.,2.],[3.,4.]])
    parts={'a':np.ones((2,2)), 'b':np.array([[1.,0.],[-1.,2.]])}
    result=decompose(ep,parts,np.array([1.,3.]))
    np.testing.assert_allclose(sum(np.array(g['allocated_delta_mse']) for g in result['groups'].values()),result['delta_mse'])
    expected=np.average((ep-sum(parts.values()))**2-ep**2,axis=0,weights=[1.,3.])
    np.testing.assert_allclose(result['delta_mse'],expected)
    assert result['groups']['b']['remove_group_delta_mse'] != result['groups']['b']['allocated_delta_mse']


def test_activation_uses_source_statistics_and_reports_constant_shift():
    result=source_activation(np.array([[3.,1.],[0.,1.]]),np.array([0.,1.]),np.array([1.,1e-6]),np.array([1.,0.]))
    assert result['max_abs_z']==[3.,0.]
    assert result['source_constant_changed_columns']==[]
    shifted=source_activation(np.array([[0.,2.]]),np.array([0.,1.]),np.array([1.,1e-6]),np.array([1.,0.]))
    assert shifted['source_constant_changed_columns']==[1]
    assert shifted['max_abs_z'][1]==1e6


def test_invalid_weights_fail_closed():
    with pytest.raises(ValueError):
        decompose(np.ones((2,2)),{'a':np.ones((2,2))},np.array([0.,1.]))
