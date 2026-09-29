"""Exercise real Python GC state around a bounded episode, no Isaac claim."""
import gc
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest


@pytest.fixture
def measured(monkeypatch):
    # Windows has no resource module; only the RSS observation is substituted.
    monkeypatch.setitem(sys.modules, 'resource', SimpleNamespace(RUSAGE_SELF=0,
        getrusage=lambda _: SimpleNamespace(ru_maxrss=1000)))
    path = Path(__file__).resolve().parents[1]/'workflows/runtime_timing_v67.py'
    spec = importlib.util.spec_from_file_location('timing_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.measured_episode


@pytest.mark.parametrize('fail', [False, True])
def test_gc_deferred_only_within_episode_and_restored_after_exception(measured, fail):
    enabled = gc.isenabled()
    gc.enable()
    original = lambda: 'command'
    feedback = SimpleNamespace(decide=original)
    session = SimpleNamespace(runtime=SimpleNamespace(feedback=feedback,
        ledger=SimpleNamespace(physics_index=0)))
    callbacks = list(gc.callbacks)
    report = {}
    def run():
        assert not gc.isenabled()
        assert feedback.decide() == 'command'
        if fail: raise RuntimeError('episode_failure')
        return 'completed'
    try:
        if fail:
            with pytest.raises(RuntimeError, match='episode_failure'):
                measured(session, report, run, defer_gc=True)
        else:
            assert measured(session, report, run, defer_gc=True) == 'completed'
        assert gc.isenabled() and feedback.decide is original
        assert gc.callbacks == callbacks
        assert report['latency_probe_v67']['gc_restored']
        assert len(report['latency_probe_v67']['feedback']) == 1
    finally:
        if not enabled: gc.disable()
