import hashlib
import json
import numpy as np
import pytest


def test_matrix_pairs_excitation_across_three_levels_without_training():
    from workflows.protocol_v88 import cases, protocol, excitation
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
    from workflows.disturbance_data_v88 import frozen_model, MODEL_PATH, ROOT, MODEL_SHA256
    record,physical=frozen_model(ROOT/MODEL_PATH)
    assert record['lifted']['training_rows']==16640
    assert hashlib.sha256((ROOT/MODEL_PATH).read_bytes()).hexdigest()==MODEL_SHA256
    bad=tmp_path/'changed.json';bad.write_bytes((ROOT/MODEL_PATH).read_bytes()+b' ')
    with pytest.raises(ValueError,match='v88_frozen_model'):frozen_model(bad)


def test_new_manifest_requires_v88_files_and_support(tmp_path,monkeypatch):
    from workflows import disturbance_data_v88 as m
    monkeypatch.setattr(m,'_verify',lambda *a,**k:'manifest-hash')
    path=tmp_path/'manifest.json'
    path.write_text(json.dumps(dict(schema='v88-source-freeze',files={})))
    with pytest.raises(ValueError,match='v88_manifest_sources'):m.verify_manifest(path)


def test_old_trace_rejected_before_runtime_imports():
    from workflows.disturbance_data_v88 import validate_trace
    from workflows.protocol_v87 import cases
    with pytest.raises(ValueError,match='identity_or_completion'):
        validate_trace(dict(case=cases()[0],substeps=[],schema='disturbance-data-v87'),{},'sha')


def test_evaluation_pairs_all_cells_and_never_supplies_hidden_parameters(tmp_path,monkeypatch):
    from workflows import evaluate_disturbance_v88 as m
    from workflows.protocol_v88 import cases
    calls=[]
    def step(x,u,c):
        assert x.shape==(1,11) and u.shape==(1,6)
        calls.append(1);return x.copy()
    class Latent:
        def start_forecast(self,x,c):calls.append('initialize');return step
    record=dict(collection_manifest_sha256='old-training-manifest',fit_episode_hashes={'old':'old'},
        training_range=dict(state_min=[0]*11,state_max=[10]*11))
    monkeypatch.setattr(m,'verify_manifest',lambda p:'new-manifest')
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


def test_release_contains_v88_model_and_support(tmp_path):
    from workflows.prepare_disturbance_v88 import prepare
    from workflows.disturbance_data_v88 import verify_manifest, REQUIRED_SOURCES
    output=tmp_path/'release';prepare(output);verify_manifest(output/'manifest.json')
    m=json.loads((output/'manifest.json').read_text())
    assert REQUIRED_SOURCES<=set(m['files'])
