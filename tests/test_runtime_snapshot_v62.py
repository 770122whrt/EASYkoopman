"""Snapshot ownership and value equivalence; CPU fixtures, not Isaac evidence."""
from types import SimpleNamespace

import torch


def test_batch_freezes_alias_before_next_getter_and_preserves_types():
    from workflows.runtime_snapshot_v62 import SnapshotBatch
    batch = SnapshotBatch()
    shared = torch.tensor([[1., 2., 3.]])
    before = batch.capture(shared)
    shared.add_(10)
    after = batch.capture(shared)
    nested = batch.capture({'bool': torch.tensor(True), 'int': torch.tensor(2**60 + 1),
                            'empty': torch.empty(0, 2), 'tuple': ('x', None)})
    result = batch.finish({'before': before, 'after': after, 'nested': nested})
    assert result == {'before': [[1., 2., 3.]], 'after': [[11., 12., 13.]],
                      'nested': {'bool': True, 'int': 2**60 + 1, 'empty': [], 'tuple': ['x', None]}}
    assert batch.transfer_count == 3
    shared.zero_()
    assert result['before'] == [[1., 2., 3.]]


def test_snapshot_equivalence_with_backend_buffer_reuse():
    from workflows.runtime_snapshot_v62 import BatchedIsaacExecutionSession
    from workflows.control_trace_v23 import ControlTraceSession
    class View:
        def __init__(self):
            self.buffer = torch.zeros(1, 9)
        def __getattr__(self, name):
            def read():
                self.buffer.fill_(sum(map(ord, name)))
                return self.buffer
            return read
    env = SimpleNamespace(num_envs=1, actions_i=torch.tensor([[.1, .2]]),
        thruster_dynamics=SimpleNamespace(state=torch.tensor([[3., 4.]])),
        get_koopman_telemetry_snapshot=lambda: {'token': torch.tensor([1]), 'configuration': 'base'},
        sim=SimpleNamespace(cfg=SimpleNamespace(gravity=(0., 0., -9.81))),
        _robot=SimpleNamespace(root_physx_view=View(),
            data=SimpleNamespace(root_state_w=torch.arange(13.).reshape(1, 13), _sim_timestamp=.25),
            _external_force_b=torch.zeros(1, 1, 3), has_external_wrench=True))
    observer = object.__new__(BatchedIsaacExecutionSession)
    ControlTraceSession.__init__(observer, env, state_getter=lambda e: [[5.5] + [0.]*10],
                                 backend_readback_enabled=True)
    assert observer._snapshot() == ControlTraceSession._snapshot(observer)


def test_batch_noncontiguous_tensor_and_python_ownership():
    from workflows.runtime_snapshot_v62 import SnapshotBatch
    from workflows.control_trace_v23 import _copy
    value = {'tensor': torch.arange(12.).reshape(3, 4).T, 'data': [{'k': [1, 2]}]}
    batch = SnapshotBatch()
    captured = batch.capture(value)
    expected = _copy(value)
    value['data'][0]['k'][0] = 90
    assert batch.finish(captured) == expected
