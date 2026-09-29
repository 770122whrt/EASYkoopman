import numpy as np
import pytest

from workflows.trace_control_v23 import actions, parser, request


def test_prepared_request_is_bounded_and_does_not_execute_by_default():
    args = parser().parse_args(['--run-id', 'example', '--condition', 'warm'])
    assert not args.execute
    spec = request(args)
    assert spec['observed_intervals'] + spec['preparation_intervals'] == 64
    assert spec['control_history_reset_mode'] == 'legacy'


def test_actions_match_seed_and_mask_without_using_future_state():
    spec = request(parser().parse_args(['--run-id', 'example', '--configuration', 'uuv4', '--excitation', 'prbs']))
    first = actions(spec)
    assert np.array_equal(first, actions(spec))
    assert first.shape == (32, 4)
    assert np.max(np.abs(first)) <= np.float32(.1)
    assert np.all(first[:, 2] == 0)
    assert np.array_equal(first[0], first[3])
    assert not np.array_equal(first, actions({**spec, 'seed': 8202}))


def test_unsupported_runtime_budget_or_seed_cannot_be_added():
    with pytest.raises(SystemExit):
        parser().parse_args(['--run-id', 'example', '--seed', '9999'])
    with pytest.raises(SystemExit):
        parser().parse_args(['--run-id', 'example', '--steps', '512'])


def test_inertia_repair_is_explicit_and_recorded_with_legacy_default():
    assert request(parser().parse_args(['--run-id', 'example']))['inertia_sync_mode'] == 'legacy'
    spec = request(parser().parse_args(['--run-id', 'example', '--inertia-sync', 'declared_v1']))
    assert spec['inertia_sync_mode'] == 'declared_v1'
