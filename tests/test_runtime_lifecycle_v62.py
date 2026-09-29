import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import weakref
import pytest


def api():
    assert (Path(__file__).resolve().parents[1]/'workflows/runtime_lifecycle_v62.py').exists()
    return importlib.import_module('workflows.runtime_lifecycle_v62')


def test_native_dependents_are_collected_before_plugin_unload(tmp_path):
    m=api(); events=[]
    class Native:pass
    class Env:
        def __init__(self):self.native=Native()
        def close(self):events.append('environment_close')
    def make():
        env=Env();view=Native()
        trace=SimpleNamespace(active=False,env=env,contact_getter=lambda:view,
            originals={'close':env.close},instance_values={},actuator_original=env.close,
            actuator_instance_value=None,runtime=None)
        return {'env':env,'runtime':env,'trace':trace},weakref.ref(env),weakref.ref(view),weakref.ref(env.native)
    resources,env_ref,contact_ref,native_ref=make()
    resources['worker']=SimpleNamespace(close=lambda:{'process_stopped':True,'io_threads_stopped':True})
    def unload():
        assert env_ref() is None and contact_ref() is None and native_ref() is None
        events.append('plugin_unload')
    resources['app']=SimpleNamespace(close=unload)
    report={'status':'diagnostic_exception','exception':'original_deadline','cleanup_errors':[]}
    m.close_owned_resources(resources,report,tmp_path)
    assert resources=={}
    assert events==['environment_close','plugin_unload']
    assert report['cleanup_errors']==[] and all(report['cleanup_completed'].values())
    assert report['exception']=='original_deadline'
    assert len(list(tmp_path.glob('cleanup-*.json')))==6


def test_active_observer_is_not_silently_detached():
    m=api();trace=SimpleNamespace(active=True,env=object())
    with pytest.raises(ValueError,match='active_observer'):m.release_observer(trace)
    assert trace.env is not None


def test_close_error_is_retained_and_remaining_resources_close(tmp_path):
    m=api();events=[]
    def fail():raise RuntimeError('close failure')
    resources={'worker':SimpleNamespace(close=fail),'env':SimpleNamespace(close=lambda:events.append('env')),
               'runtime':None,'trace':None,'app':SimpleNamespace(close=lambda:events.append('app'))}
    report={'status':'diagnostic_exception','cleanup_errors':[],'exception':'original'}
    m.close_owned_resources(resources,report,tmp_path)
    assert events==['env','app'] and resources=={}
    assert report['cleanup_errors']==['worker:RuntimeError:close failure']
    assert report['cleanup_completed']['worker'] is False
    assert report['exception']=='original'


def test_failed_worker_join_is_not_counted_as_closed(tmp_path):
    m=api();resources={'worker':SimpleNamespace(close=lambda:{'process_stopped':False,'io_threads_stopped':True}),
        'env':None,'runtime':None,'trace':None,'app':None}
    report={'status':'diagnostic_exception','cleanup_errors':[]}
    m.close_owned_resources(resources,report,tmp_path)
    assert report['cleanup_completed']==dict(worker=False,environment=False,simulation_app=False)
    assert report['cleanup_errors']
