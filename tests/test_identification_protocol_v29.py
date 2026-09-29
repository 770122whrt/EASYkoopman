import copy
import numpy as np
import pytest


def test_fixed_new_roles_seeds_and_bounds():
    from workflows.identification_protocol_v29 import cases, protocol, validate_case
    qs=cases();assert len(qs)==48 and len({q['run_id'] for q in qs})==48
    assert len({q['seed'] for q in qs})==48
    assert {role:sum(q['role']==role for q in qs) for role in ('preflight','fit','validation')}=={'preflight':8,'fit':24,'validation':16}
    assert sum(q['intervals'] for q in qs)==14848
    assert protocol()['resource_cap']=={'collector_seconds':5400,'native_case_seconds':300,'analysis_seconds':3600,'disk_bytes':4*1024**3}
    for q in qs:
        validate_case(q)
        assert q['training_eligible']==(q['role']=='fit')
        assert q['starting_z_m']==5.5 and q['mode']=='direct_pre_tam_v24'
        with pytest.raises(ValueError,match='identification_case'):
            validate_case(dict(q,role='test'))


def test_excitation_is_exogenous_reproducible_masked_and_bounded():
    from workflows.identification_protocol_v29 import cases,pulse
    from workflows.workpoint_v27 import mechanics
    for q in cases():
        a=pulse(q);np.testing.assert_array_equal(a,pulse(copy.deepcopy(q)))
        assert a.shape==(q['intervals'],4) and a.dtype==np.float32
        assert not a[:128].any()
        assert np.all(np.abs(a)<=[2,1,.5,.25])
        mask=np.array(mechanics(q['configuration'])['control_mask_4'],dtype=bool)
        assert not a[:,~mask].any()
        assert np.linalg.matrix_rank(a[128:,mask])==mask.sum()


def test_paired_prbs_has_zero_mean_and_roles_have_different_excitation():
    from workflows.identification_protocol_v29 import cases,pulse
    base=[q for q in cases() if q['configuration']=='base' and q['excitation']=='prbs']
    fit=next(q for q in base if q['role']=='fit');val=next(q for q in base if q['role']=='validation')
    a=pulse(fit);b=pulse(val)
    np.testing.assert_array_equal(a[128:].sum(0),np.zeros(4))
    assert not np.array_equal(a[128:],b[128:])


@pytest.mark.parametrize('role',['preflight','fit','validation'])
def test_native_status_guard_checks_actual_role_and_rejects_failures(role):
    from workflows.identification_protocol_v29 import cases,guarded_exit_code
    q=next(q for q in cases() if q['role']==role)
    good={'status':'completed_identification_pending_acceptance','request':q,'source_commit':'a'*40,
          'training_eligible':False,'model_fits':0}
    assert guarded_exit_code(0,good,q,'a'*40)==0
    assert guarded_exit_code(7,good,q,'a'*40)==7
    for bad in [None,{},dict(good,status='failed_identification'),dict(good,source_commit='b'*40),
                dict(good,training_eligible=not good['training_eligible']),dict(good,request=dict(q,seed=0))]:
        assert guarded_exit_code(0,bad,q,'a'*40)==1
