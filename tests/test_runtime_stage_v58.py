"""Supervisor fault injection. Linux process-group integration is separate."""
import json
import sys
from pathlib import Path
import pytest


def test_stage_requires_new_approval_before_creating_attempt(tmp_path):
    from workflows.run_runtime_v58 import run_stage
    with pytest.raises(ValueError,match='approval'):run_stage(tmp_path,None)
    assert list(tmp_path.iterdir())==[]


def test_nonzero_collection_stops_before_validation_and_next_case():
    from workflows.run_runtime_v58 import run_sequence
    calls=[]
    def launch(q,kind,remaining):calls.append((q['case_id'],kind));return {'native_exit':7,'group_stopped':True}
    r=run_sequence(launch,lambda q:None,clock=lambda:0.)
    assert r['status']=='stopped_runtime_no_go'
    assert calls==[('p9-v57-base','collector')]


def test_zero_native_exit_does_not_skip_semantic_validation():
    from workflows.run_runtime_v58 import run_sequence
    calls=[]
    def launch(q,kind,remaining):
        calls.append((q['case_id'],kind));return {'native_exit':0 if kind=='collector' else 1,'group_stopped':True}
    r=run_sequence(launch,lambda q:None,clock=lambda:0.)
    assert r['accepted']==[] and r['status']=='stopped_runtime_no_go'
    assert calls==[('p9-v57-base','collector'),('p9-v57-base','validator')]


def test_eight_cases_strictly_sequential_with_no_refit_or_retry():
    from workflows.run_runtime_v58 import run_sequence
    from workflows.phase9_preflight_v57 import cases
    calls=[]
    def launch(q,kind,remaining):calls.append((q['case_id'],kind));return {'native_exit':0,'group_stopped':True}
    r=run_sequence(launch,lambda q: {'case_id':q['case_id']},clock=lambda:0.)
    assert r['status']=='completed_runtime_interface_preflight'
    assert calls==[(q['case_id'],kind) for q in cases() for kind in ('collector','validator')]
    assert len(r['accepted'])==8 and r['model_fits']==0 and r['control_benefit_claim'] is False


def test_collection_does_not_advance_until_semantic_artifact_readback_passes():
    from workflows.run_runtime_v58 import run_sequence
    calls=[]
    def launch(q,kind,remaining):calls.append(kind);return {'native_exit':0,'group_stopped':True}
    def readback(q):raise ValueError('trace_hash_mismatch')
    r=run_sequence(launch,readback,clock=lambda:0.)
    assert calls==['collector','validator'] and r['accepted']==[] and 'trace_hash_mismatch' in r['exception']


def test_unconfirmed_process_group_cleanup_stops_even_after_native_zero():
    from workflows.run_runtime_v58 import run_sequence
    calls=[]
    def launch(q,kind,remaining):calls.append(kind);return {'native_exit':0,'group_stopped':False}
    assert run_sequence(launch,lambda q:None,clock=lambda:0.)['status']=='stopped_runtime_no_go'
    assert calls==['collector']


def test_stage_time_exhaustion_stops_without_issuing_another_case():
    from workflows.run_runtime_v58 import run_sequence
    now=[0.];calls=[]
    def launch(q,kind,remaining):calls.append(kind);now[0]=1801.;return {'native_exit':0,'group_stopped':True}
    r=run_sequence(launch,lambda q:None,clock=lambda:now[0])
    assert calls==['collector'] and r['status']=='stopped_runtime_no_go'


def test_collector_and_validator_share_one_case_deadline():
    from workflows.run_runtime_v58 import run_sequence
    now=[0.];calls=[]
    def launch(q,kind,remaining):
        calls.append(kind);now[0]+=179.
        return {'native_exit':0,'group_stopped':True}
    r=run_sequence(launch,lambda q:None,clock=lambda:now[0])
    assert calls==['collector'] and r['accepted']==[] and r['status']=='stopped_runtime_no_go'


def test_validator_receives_only_remaining_case_time():
    from workflows.run_runtime_v58 import run_sequence
    now=[0.];limits=[]
    def launch(q,kind,remaining):
        limits.append((kind,remaining));now[0]+=100. if kind=='collector' else 10.
        return {'native_exit':0,'group_stopped':True}
    r=run_sequence(launch,lambda q:{'case_id':q['case_id']},clock=lambda:now[0])
    assert r['status']=='completed_runtime_interface_preflight'
    assert limits==[('collector',180.),('validator',80.)]*8


def test_full_size_inventory_counts_release_and_results(tmp_path):
    from workflows.run_runtime_v58 import disk_bytes
    (tmp_path/'source').write_bytes(b'123');(tmp_path/'results').mkdir();(tmp_path/'results/x').write_bytes(b'12345')
    assert disk_bytes(tmp_path)==8


def test_inventory_does_not_follow_a_symlink(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from workflows.run_runtime_v58 import disk_bytes
    monkeypatch.setattr(Path,'rglob',lambda *a:[SimpleNamespace(is_symlink=lambda:True)])
    with pytest.raises(ValueError,match='symlink'):disk_bytes(tmp_path)


@pytest.mark.parametrize('mode',['timeout','native_zero_orphan','disk_guard'])
def test_process_faults_invoke_group_cleanup_including_zero_exit(monkeypatch,tmp_path,mode):
    from workflows import run_runtime_v58 as m
    now=[0.];alive=[False];code=[0 if mode=='native_zero_orphan' else None];killed=[];sizes=[0]
    class Child:
        pid=1234
        def poll(self):return code[0]
        def wait(self,timeout):return code[0]
    def spawn(*a,**kw):
        assert kw['start_new_session'] is True
        alive[0]=True;return Child()
    def kill(pgid,sig):
        killed.append(pgid);alive[0]=False
        if code[0] is None:code[0]=-15
    def size(root):
        sizes[0]+=1
        return 200*1024**2 if mode=='disk_guard' and sizes[0]>1 else 0
    monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m.subprocess,'Popen',spawn)
    monkeypatch.setattr(m,'live_group_members',lambda pg:[4567] if alive[0] else [])
    monkeypatch.setattr(m.os,'killpg',kill,raising=False)
    monkeypatch.setattr(m.time,'sleep',lambda s:now.__setitem__(0,now[0]+s))
    monkeypatch.setattr(m,'disk_bytes',size)
    result=m.bounded_process(['fixture'],tmp_path,tmp_path/'log',timeout_seconds=1.,clock=lambda:now[0])
    assert killed==[1234] and result['group_stopped'] is True
    if mode=='native_zero_orphan':assert result['native_exit']==0 and result['reason']=='completed'
    else:assert result['native_exit']!=0 and result['reason']==('timeout' if mode=='timeout' else 'disk_guard')


@pytest.mark.skipif(sys.platform!='linux',reason='actual Linux process-group cleanup requires target OS')
def test_real_linux_timeout_kills_descendant_processes(tmp_path):
    from workflows.run_runtime_v58 import bounded_process
    command=[sys.executable,'-c','import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);time.sleep(60)']
    result=bounded_process(command,tmp_path,tmp_path/'timeout.log',timeout_seconds=.4)
    assert result['reason']=='timeout' and result['native_exit']!=0 and result['group_stopped'] is True
