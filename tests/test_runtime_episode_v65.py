from types import SimpleNamespace
import pytest
from test_runtime_episode_v57 import Clock, Session


def run(s, clock, **kwargs):
    from workflows.runtime_episode_v65 import run_intervals
    return run_intervals(s, lambda _: None, [5.5, 1, 0, 0, 0],
                         reference_id='ref', controls=4, clock=clock,
                         sleep=clock.sleep, **kwargs)


class VariableSession(Session):
    def run_interval(self, *args, **kwargs):
        self.cost = .028 if self.calls == 0 else .003
        return super().run_interval(*args, **kwargs)


def test_first_interval_is_bounded_startup_then_once_reanchored():
    c = Clock(); s = VariableSession(c)
    result = run(s, c)
    assert result['startup_ms'] == pytest.approx(28)
    assert result['steady_max_ms'] == pytest.approx(3)
    assert result['steady_deadline_misses'] == 0
    assert c.now == pytest.approx(.028 + 3/60)
    assert s.runtime.ledger.physics_index == 8


def test_startup_limit_is_not_unbounded():
    c = Clock(); s = Session(c, cost=.101)
    with pytest.raises(ValueError, match='startup_deadline'): run(s, c)
    assert s.calls == 1 and s.stopped


def test_later_overrun_is_not_renamed_startup_or_retried():
    c = Clock(); s = Session(c, cost=.028)
    with pytest.raises(ValueError, match='steady_deadline'): run(s, c)
    assert s.calls == 2 and s.runtime.ledger.physics_index == 4


def test_half_interval_failure_preserves_actual_history():
    c = Clock(); s = Session(c, failure_at=2)
    with pytest.raises(RuntimeError, match='half_interval'): run(s, c)
    assert s.runtime.ledger.physics_index == 3


def test_zero_activation_cannot_pass_mpc_integration():
    c = Clock(); s = Session(c); s.runtime.stats['mpc_activations'] = 0
    with pytest.raises(ValueError, match='no_mpc_activation'): run(s, c)


def test_simulation_effects_keep_wall_misses_and_do_not_claim_realtime():
    c = Clock(); s = Session(c, cost=.028)
    s.runtime.stats['mpc_activations'] = 0
    result = run(s, c, mode='simulation_effect', require_mpc=False)
    assert result['steady_deadline_misses'] == 3
    assert result['runtime_qualified'] is False
    assert s.runtime.ledger.physics_index == 8


def test_unqualified_or_unknown_timing_modes_rejected():
    c = Clock(); s = Session(c)
    with pytest.raises(ValueError, match='mode'): run(s, c, mode='ignore_deadlines')


def test_effect_worker_delivers_only_at_next_boundary_and_once():
    from workflows.runtime_episode_v65 import BoundaryWorker
    class Worker:
        generation = 'g'; state = 'ready'
        def submit(self, rid, request):
            self.state = 'busy'
            return dict(status='accepted', request_id=rid)
        def poll(self):
            if self.state == 'busy':
                self.state = 'ready'
                return dict(status='result', elapsed_ms=12, payload={'binding': 'original'})
        def close(self): return {'process_stopped': True}
    w = BoundaryWorker(Worker())
    w.submit('id', object())
    assert w.poll() is None
    w.finish_boundary()
    assert w.poll()['elapsed_ms'] == 12
    assert w.poll() is None


def test_simulation_wait_failure_does_not_become_success():
    from workflows.runtime_episode_v65 import BoundaryWorker
    class Worker:
        generation='g'; state='busy'
        def poll(self): return {'status': 'timeout', 'reason': 'request_deadline'}
    w = BoundaryWorker(Worker()); w._submitted = True
    w.finish_boundary()
    assert w.poll()['status'] == 'timeout'
