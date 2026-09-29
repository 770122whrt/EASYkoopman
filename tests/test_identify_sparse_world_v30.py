from types import SimpleNamespace
import numpy as np
import pytest


def test_fit_rejects_missing_configuration_episodes_before_reading_samples():
    from workflows.identify_sparse_world_v30 import fit_model
    from workflows.identification_protocol_v29 import cases
    q=next(q for q in cases() if q['role']=='fit' and q['configuration']=='base')
    e=SimpleNamespace(case=q,source_commit='a'*40)
    with pytest.raises(ValueError,match='sparse_fit_inventory'):fit_model([e],'nonlinear',['base'])


def test_loaded_operator_rejects_added_height_to_velocity_coefficient():
    from workflows.identify_sparse_world_v30 import validate_matrix
    from koopman.sparse_world_edmd_v30 import core_matrix
    d=np.zeros(6);q=np.ones(6);matrix=core_matrix('nonlinear',d,q,.05)
    validate_matrix(matrix,'nonlinear',d,q,.05)
    matrix[0,10]=.001
    with pytest.raises(ValueError,match='sparse_matrix_constraint'):validate_matrix(matrix,'nonlinear',d,q,.05)


def test_synthetic_neutral_acceleration_fits_and_roundtrips_without_spurious_damping():
    from workflows.identify_sparse_world_v30 import fit_model,from_record
    from workflows.identification_protocol_v29 import cases
    from koopman.projected_edmd_v24 import PhysicalContext
    c=PhysicalContext(1,[1,1,1],[0,0,0],1/997,0.)
    n=np.arange(641,dtype=float);x=np.tile([5.5,1,0,0,0,0,0,0,0,0,0],(641,1)).astype(float)
    x[:,7]=.01*n/120;x[:,0]+=.01*n*(n+1)/(2*120**2)
    a=np.zeros((640,6));a[:,2]=.01
    episodes=[SimpleNamespace(case=q,states=x,acceleration=a,context=c,
        acceptance={'training_eligible':True},source_commit='a'*40,trace_sha256='b'*64)
        for q in cases() if q['role']=='fit' and q['configuration']=='base']
    record,model=fit_model(episodes,'nonlinear',['base'])
    np.testing.assert_allclose(model(x[:-1],a,c),x[1:],atol=1e-9)
    np.testing.assert_allclose(from_record(record)(x[:-1],a,c),x[1:],atol=1e-9)
    assert not np.asarray(record['matrix'])[0,10:16].any()
    assert max(record['damping'])<1e-7
