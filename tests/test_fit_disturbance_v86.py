"""Workflow role isolation, with synthetic loader fixtures confined to tmp_path."""
import numpy as np
import pytest
from workflows.protocol_v86 import cases


def test_training_opens_only_predeclared_training_episodes_and_never_overwrites(tmp_path,monkeypatch):
    from workflows import fit_disturbance_v86 as m
    opened=[];calls=[]
    monkeypatch.setattr(m,'verify_manifest',lambda path:'a'*64)
    def load(path,sha):
        opened.append(path.name);q=next(q for q in cases() if q['run_id']==path.name)
        x=np.zeros((641,11));x[:,0]=5.5;x[:,1]=1.
        return dict(case=q,states=x,inputs=np.zeros((640,6)),trace_sha256=f"{q['seed']:064x}")
    def fit(x,y,u,c,p,*,ridge):
        calls.append((x.shape,y.shape,u.shape,ridge));return {'audit':{},'test_fixture_only':True}
    monkeypatch.setattr(m,'load_episode',load);monkeypatch.setattr(m,'fit',fit)
    path=tmp_path/'model.json';m.train(tmp_path,'manifest',path)
    assert opened==[q['run_id'] for q in cases() if q['role']=='train']
    assert calls==[((2560,11),(2560,11),(2560,6),.001)]
    before=path.read_bytes()
    with pytest.raises(FileExistsError):m.train(tmp_path,'manifest',path)
    assert path.read_bytes()==before
    assert len(calls)==1


def test_evaluation_refuses_a_training_trace_hash_even_under_test_case_name(tmp_path,monkeypatch):
    from workflows import fit_disturbance_v86 as m
    monkeypatch.setattr(m,'verify_manifest',lambda path:'a'*64)
    record=dict(collection_manifest_sha256='a'*64,fit_episode_hashes={'train':'b'*64})
    monkeypatch.setattr(m,'load_record',lambda path:(record,None))
    monkeypatch.setattr(m,'load_episode',lambda path,sha:dict(
        case=next(q for q in cases() if q['run_id']==path.name),trace_sha256='b'*64))
    with pytest.raises(ValueError,match='overlap'):
        m.evaluate(tmp_path,'manifest','model','test',tmp_path/'result.json')
