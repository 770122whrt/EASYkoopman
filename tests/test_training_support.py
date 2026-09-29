import copy
import numpy as np
import pytest


def fixture():
    from workflows.disturbance_protocol import get_protocol
    cases = get_protocol("v87").cases
    from workflows.disturbance_data import context
    from koopman.support_domain import SupportDomain
    c=context()
    old=SupportDomain('base',tuple([c.mass,*c.inertia,*c.cob,c.volume,c.drag_multiplier,c.rho,c.beta,c.gravity]),
        'a'*64,np.array([5.3,-.08,-.15,.98,-.03,-.02,-.04,-.32,-.2,-.15,0]),
        np.array([5.52,.05,.075,1,.03,.03,.04,.39,.18,.15,.3]),np.full(4,-.08),np.full(4,.08),())
    object.__setattr__(old,'_verified_fit',True)
    rows=[]
    for i,q in enumerate(x for x in cases() if x['role']=='train'):
        x=np.zeros((1281,11));x[:,0]=np.linspace(5.1,5.9,1281);x[:,1]=1
        x[:,8]=np.linspace(-.7,.7,1281)
        rows.append(dict(case=q,states=x,commands=np.full((1280,4),.12),trace_sha256=f'{i:064x}'))
    hashes={e['case']['run_id']:e['trace_sha256'] for e in rows}
    return old,rows,hashes


def test_training_only_expansion_preserves_physical_and_command_constraints():
    from koopman.training_support import derive_record,restore_domain
    old,rows,hashes=fixture();before=old.record()
    record=derive_record(old,rows,'b'*64,hashes)
    domain=restore_domain(record,old,'b'*64,hashes)
    assert old.record()==before and domain.identity!=old.identity
    assert domain._verified_fit and domain.fit_sources==old.fit_sources
    x=rows[0]['states'][0].copy();x[8]=-.52
    assert old.check_states(x[None]) and domain.check_states(x[None]) is None
    assert np.all(domain.command_lower<=old.command_lower)
    assert np.all(domain.command_upper>=.12) and np.all(domain.command_upper<=.95)
    for index,value,reason in [(0,8,'height_limit'),(5,2,'linear_speed_limit'),(8,4,'angular_speed_limit')]:
        bad=x.copy();bad[index]=value
        assert domain.check_states(bad[None])['reason']==reason
    assert domain.state_upper[-1]<=.6


def test_support_rejects_test_data_duplicate_hashes_and_changed_artifact():
    from koopman.training_support import derive_record,restore_domain
    old,rows,hashes=fixture()
    bad=copy.deepcopy(rows);bad[0]['case']['role']='test'
    with pytest.raises(ValueError,match='training'):derive_record(old,bad,'b'*64,hashes)
    bad=copy.deepcopy(rows);bad[1]['trace_sha256']=bad[0]['trace_sha256']
    with pytest.raises(ValueError,match='training'):derive_record(old,bad,'b'*64,hashes)
    record=derive_record(old,rows,'b'*64,hashes)
    record['state_upper'][0]+=1
    with pytest.raises(ValueError,match='hash'):restore_domain(record,old,'b'*64,hashes)


def test_bound_formula_cannot_be_silently_relaxed_even_when_resealed():
    from koopman.training_support import derive_record,restore_domain
    from koopman.lifted_state import seal
    old,rows,hashes=fixture();record=derive_record(old,rows,'b'*64,hashes)
    record['state_upper'][8]=3
    with pytest.raises(ValueError,match='bounds'):restore_domain(seal(record),old,'b'*64,hashes)
    with pytest.raises(ValueError,match='identity'):restore_domain(derive_record(old,rows,'b'*64,hashes),old,'c'*64,hashes)


def test_worker_serialization_keeps_both_provenances_and_exact_bounds():
    import pickle
    from koopman.training_support import derive_record,restore_domain
    old,rows,hashes=fixture()
    domain=restore_domain(derive_record(old,rows,'b'*64,hashes),old,'b'*64,hashes)
    remote=pickle.loads(pickle.dumps(domain))
    assert remote.identity==domain.identity and remote.record()==domain.record()
    assert remote._verified_fit and remote.fit_sources==old.fit_sources
    assert remote.support_training_sources==tuple(sorted(hashes.items()))
