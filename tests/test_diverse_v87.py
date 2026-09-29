import importlib
import numpy as np
import pytest


def test_diverse_protocol_is_fixed_disjoint_and_has_active_solver_origins():
    m=importlib.import_module('workflows.protocol_v87')
    q=m.cases()
    assert [sum(x['role']==r for x in q) for r in ('train','validation','test')]==[16,4,4]
    assert len({x['seed'] for x in q})==24
    assert {x['excitation'] for x in q if x['role']=='train'}=={'prbs','multisine','chirp','pulses'}
    for x in q:
        u=m.excitation(x)
        assert u.shape==(320,4) and np.isfinite(u).all()
        np.testing.assert_array_equal(u[:64],0)
        assert x['hidden_drag_fraction']==.2
        # No net unidirectional heave demand during the long collection.
        assert abs(float(u[64:,3].sum()))<1e-5
    assert all(i>256 and i+80<=1280 for i in m.protocol()['prediction_origins'])
    assert m.protocol()['solver_origins']==[384,896]


def test_startup_is_counted_once_and_test_cannot_enter_training():
    from workflows.fit_disturbance_v87 import training_arrays
    from workflows.protocol_v87 import cases
    def episode(q):
        x=np.zeros((1281,11));x[:,0]=q['seed'];x[:,1]=1
        return dict(case=q,states=x,inputs=np.zeros((1280,6)),trace_sha256=f"{q['seed']:064x}")
    train=[episode(q) for q in cases() if q['role']=='train']
    x,y,u=training_arrays(train)
    assert x.shape==y.shape==(16640,11) and u.shape==(16640,6)
    assert np.count_nonzero(x[:,0]==train[0]['case']['seed'])==1280
    assert np.count_nonzero(x[:,0]==train[-1]['case']['seed'])==1024
    with pytest.raises(ValueError,match='training_inventory'):
        training_arrays(train[:-1]+[episode(cases()[-1])])


def test_solver_admission_rechecks_raw_candidate_not_fallback():
    from workflows.solve_disturbance_v87 import check_candidate
    class Checker:
        def check(self,o,x,u,old,r):return dict(feasible=bool(np.max(abs(u))<.1))
    args=(Checker(),None,None,None,None)
    assert not check_candidate(*args,dict(candidate_commands=np.ones((20,4)),commands=np.zeros((20,4))))['feasible']
    assert not check_candidate(*args,dict(candidate_commands=None))['feasible']
    assert check_candidate(*args,dict(candidate_commands=np.zeros((20,4))))['feasible']


def test_train_reads_only_train_and_refuses_overwrite(tmp_path,monkeypatch):
    from workflows import fit_disturbance_v87 as m
    opened=[];fits=[]
    monkeypatch.setattr(m,'verify_manifest',lambda p:'a'*64)
    def load(p,sha):
        q=next(q for q in m.cases() if q['run_id']==p.name);opened.append(q['role'])
        x=np.zeros((1281,11));x[:,0]=5.5;x[:,1]=1
        return dict(case=q,states=x,inputs=np.zeros((1280,6)),trace_sha256=f"{q['seed']:064x}")
    def fit(x,y,u,c,p,*,ridge):
        fits.append(len(x));return dict(test_fixture_only=True)
    monkeypatch.setattr(m,'load_episode',load);monkeypatch.setattr(m,'fit',fit)
    p=tmp_path/'model.json';m.train(tmp_path,'manifest',p)
    assert opened==['train']*16 and fits==[16640]
    with pytest.raises(FileExistsError):m.train(tmp_path,'manifest',p)
    assert fits==[16640]


def test_old_data_cannot_pass_new_protocol():
    from workflows.disturbance_data_v87 import validate_trace
    from workflows.protocol_v86 import cases
    with pytest.raises(ValueError,match='identity_or_completion'):
        validate_trace(dict(case=cases()[0],substeps=[],schema='disturbance-data-v86'),{},'a'*64)


def test_new_control_validation_requires_source_binding_before_native_read():
    from workflows.validate_learned_v82 import validate
    with pytest.raises(ValueError,match='source_binding'):
        validate(dict(source_manifest_sha256='b'*64),None,0,learned_model='absent',
            learned_sha256='a'*64,experiment='v87',expected_manifest_sha='a'*64)


def test_v87_release_includes_adapter_and_protocol(tmp_path):
    import json
    from workflows.prepare_disturbance_v87 import prepare
    from workflows.disturbance_data_v87 import verify_manifest
    p=tmp_path/'release';prepare(p);verify_manifest(p/'manifest.json')
    files=json.loads((p/'manifest.json').read_text())['files']
    assert {'workflows/collect_disturbance_data_v87.py','workflows/protocol_v87.py',
        'koopman/disturbance_lifted_v86.py','easyuuv_nc/data/embodiment/embodiment.usd'}<=set(files)


def test_control_gate_recomputes_rows_and_rejects_one_bad_arm(tmp_path,monkeypatch):
    import json
    from workflows import collect_disturbance_control_v87 as m
    record=dict(collection_manifest_sha256='s',fit_episode_hashes={'train':'train'})
    monkeypatch.setattr(m,'load_record',lambda p:(record,None))
    files=[]
    for role in ('validation','test'):
        rows=[dict(episode=q['run_id'],origin=start,model=arm,complete=True,
            metrics=dict(z_rmse_m=.001,attitude_rmse_rad=.001))
            for q in m.cases() if q['role']==role for start in m.protocol()['prediction_origins']
            for arm in ('physics','koopman','hybrid')]
        report=dict(schema='v87-prediction-evaluation',role=role,model_sha256='m',
            source_manifest_sha256='s',model_fits=0,rows=rows,source_trace_hashes=[role+str(i) for i in range(4)])
        path=tmp_path/(role+'.json');path.write_text(json.dumps(report));files.append(path)
    solver=tmp_path/'solver.json'
    solver.write_text(json.dumps(dict(schema='v87-offline-solver-validation',model_sha256='m',
        source_manifest_sha256='s',distinct_origins=4,arms={arm:dict(passed=True,rows=[dict(
            candidate_check=dict(feasible=True),parent_check=dict(feasible=True))]*4) for arm in ('physics','koopman','hybrid')})))
    m.verify_control_gate('m','physics',*files,solver,model='unused')
    bad=json.loads(files[1].read_text());bad['rows'][1]['metrics']['z_rmse_m']=.003
    files[1].write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='prediction_gate'):
        m.verify_control_gate('m','physics',*files,solver,model='unused')
