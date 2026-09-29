import importlib
from types import SimpleNamespace
import weakref
import pytest


def test_retained_environment_must_not_retain_robot_after_close(tmp_path):
    m=importlib.import_module('workflows.runtime_lifecycle_v70')
    events=[]
    class Robot:pass
    class Env:
        def __init__(self):self._robot=Robot();self._is_closed=False
        @property
        def unwrapped(self):return self
        def close(self):
            assert self._robot is not None
            events.append('environment');self._is_closed=True
    env=Env();robot=weakref.ref(env._robot)
    # Models a retained traceback/cell. The environment can outlive application close.
    retained=[env]
    def unload():
        assert robot() is None
        assert retained[0]._is_closed
        events.append('application')
    report=dict(status='diagnostic_returned',cleanup_errors=[])
    m.close_owned_resources(dict(worker=None,env=env,trace=None,runtime=env,
        app=SimpleNamespace(close=unload)),report,tmp_path)
    assert report['cleanup_errors']==[]
    assert events==['environment','application']
    assert report['native_alias_release']['robot_released'] is True


def test_alias_release_requires_completed_environment_close():
    m=importlib.import_module('workflows.runtime_lifecycle_v70')
    robot=object();env=SimpleNamespace(_robot=robot,_is_closed=False)
    with pytest.raises(ValueError,match='environment_not_closed'):m.release_native_aliases(env)
    assert env._robot is robot


def test_missing_robot_is_explicit_noop():
    m=importlib.import_module('workflows.runtime_lifecycle_v70')
    assert m.release_native_aliases(SimpleNamespace())==dict(robot_alias_present=False,robot_released=True)
