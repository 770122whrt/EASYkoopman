"""Collector admission and native exit handling without importing Isaac."""
import importlib
import sys
from pathlib import Path
import pytest


def test_collector_module_import_does_not_launch_or_import_simulator():
    prior=set(sys.modules)
    importlib.import_module('workflows.collect_runtime_v57')
    assert not any(k=='isaaclab_app' or k.startswith('omni.') for k in set(sys.modules)-prior)


def test_unapproved_case_rejected_before_output_or_simulator(tmp_path):
    from workflows.collect_runtime_v57 import collect_case
    from workflows.phase9_preflight_v57 import cases
    with pytest.raises(ValueError,match='approval'):
        collect_case(tmp_path,cases()[0],None)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('native,report',[(1,{'status':'completed_runtime_pending_acceptance'}),
    (0,None),(0,{'status':'stopped_runtime_no_go'}),(0,{'status':'completed_runtime_pending_acceptance','request':{}})])
def test_native_zero_does_not_override_missing_or_failed_report(native,report):
    from workflows.collect_runtime_v57 import classify_exit
    from workflows.phase9_preflight_v57 import cases
    assert classify_exit(native,report,cases()[0],'a'*64)!=0


def test_only_complete_bound_report_and_native_zero_pass_supervisor_envelope():
    from workflows.collect_runtime_v57 import classify_exit
    from workflows.phase9_preflight_v57 import cases
    q=cases()[0]
    report=dict(status='completed_runtime_pending_acceptance',request=q,release_sha256='a'*64,
        model_fits=0,training_eligible=False,worker_closed={'process_stopped':True,'io_threads_stopped':True},
        cleanup_errors=[])
    assert classify_exit(0,report,q,'a'*64)==0
    for missing in (None,False,'0'):
        assert classify_exit(missing,report,q,'a'*64)!=0
    report['worker_closed']['process_stopped']=False
    assert classify_exit(0,report,q,'a'*64)!=0


def test_cleanup_keeps_every_failure_and_still_closes_remaining_resources():
    from types import SimpleNamespace
    from workflows.collect_runtime_v57 import close_resources
    seen=[]
    def close(name,exc=None):
        seen.append(name)
        if exc is not None:raise exc
        return {'process_stopped':True,'io_threads_stopped':True}
    report={'status':'stopped_runtime_no_go','exception':'original','cleanup_errors':[]}
    close_resources(SimpleNamespace(close=lambda:close('worker')),
        SimpleNamespace(close=lambda:close('env',RuntimeError('cleanup'))),
        SimpleNamespace(close=lambda:close('app',SystemExit(0))),report)
    assert seen==['worker','env','app'] and report['exception']=='original'
    assert report['status']=='stopped_runtime_no_go' and report['cleanup_errors']==['environment:RuntimeError:cleanup']


def test_loaded_project_module_from_other_checkout_cannot_pass_inventory(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from workflows.collect_runtime_v57 import check_loaded_sources
    monkeypatch.setattr(sys,'modules',{'koopman.example':SimpleNamespace(__file__=__file__)})
    with pytest.raises(ValueError,match='outside_release'):
        check_loaded_sources(tmp_path,{'manifest':{'files_sha256':{}}})
