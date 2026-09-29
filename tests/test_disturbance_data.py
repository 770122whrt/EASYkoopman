import hashlib
import json
import numpy as np
import pytest


def test_matrix_pairs_excitation_across_three_levels_without_training():
    from workflows.disturbance_protocol import get_protocol
    cases, protocol, excitation = get_protocol().cases, get_protocol().protocol, get_protocol().excitation
    qs=cases()
    assert len(qs)==24 and len({q['run_id'] for q in qs})==24
    assert {q['role'] for q in qs}=={'validation','test'}
    assert {q['hidden_drag_fraction'] for q in qs}=={0.,.1,.3}
    for role,scale in [('validation',1.25),('test',1.75)]:
        for signal in ('prbs','multisine','chirp','pulses'):
            paired=[q for q in qs if q['role']==role and q['excitation']==signal]
            assert len({q['seed'] for q in paired})==1
            assert all(q['amplitude_scale']==scale for q in paired)
            waves=[excitation(q) for q in paired]
            assert waves[0].shape==(320,4)
            np.testing.assert_array_equal(waves[0][:64],0)
            for w in waves[1:]:np.testing.assert_array_equal(waves[0],w)
    assert protocol()['prediction_origins']==[384,640,896,1152]
    assert protocol()['solver_origins']==[384,896]


def test_frozen_model_exact_bytes_and_no_relabel(tmp_path):
    from workflows.disturbance_data import frozen_model, MODEL_PATH, ROOT, MODEL_SHA256
    record,physical=frozen_model(ROOT/MODEL_PATH)
    assert record['lifted']['training_rows']==16640
    assert hashlib.sha256((ROOT/MODEL_PATH).read_bytes()).hexdigest()==MODEL_SHA256
    bad=tmp_path/'changed.json';bad.write_bytes((ROOT/MODEL_PATH).read_bytes()+b' ')
    with pytest.raises(ValueError,match='current_frozen_model_changed'):frozen_model(bad)




def test_old_trace_rejected_before_runtime_imports():
    from workflows.disturbance_data import validate_trace
    from workflows.disturbance_protocol import get_protocol
    cases = get_protocol("v87").cases
    with pytest.raises(ValueError,match='identity_or_completion'):
        validate_trace(dict(case=cases()[0],substeps=[],schema='disturbance-data-v87'),{},'sha')


def test_evaluation_pairs_all_cells_and_never_supplies_hidden_parameters(tmp_path,monkeypatch):
    from workflows import evaluate_disturbance as m
    from workflows.disturbance_protocol import get_protocol
    cases = get_protocol().cases
    calls=[]
    def step(x,u,c):
        assert x.shape==(1,11) and u.shape==(1,6)
        calls.append(1);return x.copy()
    class Latent:
        def start_forecast(self,x,c):calls.append('initialize');return step
    record=dict(collection_manifest_sha256='old-training-manifest',fit_episode_hashes={'old':'old'},
        training_range=dict(state_min=[0]*11,state_max=[10]*11))
    monkeypatch.setattr(m,'verify_manifest',lambda p,**kw:'new-manifest')
    monkeypatch.setattr(m,'execution_provenance',lambda *a,**kw:{})
    monkeypatch.setattr(m,'frozen_model',lambda p:(record,step))
    monkeypatch.setattr(m,'prepare',lambda *a,**k:Latent())
    def load(path,sha):
        q=next(q for q in cases() if q['run_id']==path.name)
        x=np.zeros((1281,11));x[:,0]=5.5;x[:,1]=1
        return dict(case=q,states=x,inputs=np.zeros((1280,6)),trace_sha256=q['run_id'])
    monkeypatch.setattr(m,'load_episode',load)
    out=tmp_path/'test.json';result=m.evaluate(tmp_path,'manifest','model','test',out)
    assert len(result['rows'])==144 and result['model_fits']==0
    assert calls.count('initialize')==96
    assert len(result['gates'])==3
    assert all(g['passed_windows']==16 for level in result['gates'].values() for g in level.values())
    assert {r['fraction'] for r in result['rows']}=={0.,.1,.3}
    with pytest.raises(FileExistsError):m.evaluate(tmp_path,'manifest','model','test',out)
    record['fit_episode_hashes']['bad']=cases()[12]['run_id']
    with pytest.raises(ValueError,match='overlap'):m.evaluate(tmp_path,'manifest','model','test',tmp_path/'overlap.json')




def test_startup_is_counted_once_and_test_cannot_enter_training():
    from workflows.fit_disturbance import training_arrays
    from workflows.disturbance_protocol import get_protocol
    cases = get_protocol("v87").cases
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



def test_train_reads_only_train_and_refuses_overwrite(tmp_path,monkeypatch):
    from workflows import fit_disturbance as m
    opened=[];fits=[]
    monkeypatch.setattr(m,"execution_provenance",lambda *a,**kw:{})
    monkeypatch.setattr(m,'verify_manifest',lambda p,**kw:'a'*64)
    def load(p,sha,**kw):
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
