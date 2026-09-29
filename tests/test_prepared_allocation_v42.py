"""Prepared prediction allocation must preserve the actual direct control seam."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import torch

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from workflows.control_seam_v23 import ControlKernel


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
def test_prepared_matches_original_float32_allocation_at_random_rails_and_deadzone(name):
    from koopman.prepared_allocation_v42 import PreparedDirectAllocation
    reference, candidate = ControlKernel(name), PreparedDirectAllocation(name)
    rng = np.random.default_rng(420)
    commands = list(rng.uniform(-1, 1, (40, 4)))
    for value in (-1., 0., 1., -.02, .02,
                  np.nextafter(np.float32(.02), np.float32(0)),
                  np.nextafter(np.float32(.02), np.float32(1))):
        for channel in range(4):
            command = np.zeros(4); command[channel] = value
            commands.append(command)
    commands.extend([[1., 1., 1., 1.], [-1., -1., -1., -1.]])
    for command in commands:
        saved = np.array(command, copy=True)
        expected, actual = reference.command(command, pre_tam=True), candidate.command(command, pre_tam=True)
        for key in expected:
            np.testing.assert_allclose(actual[key], expected[key], rtol=1e-12, atol=1e-12)
            assert actual[key].dtype == np.float32
        np.testing.assert_array_equal(command, saved)
    np.testing.assert_allclose(candidate.wrench_matrix, reference.B.numpy(), rtol=1e-12, atol=1e-12)
    assert candidate.rotor_constant == reference.env.cfg.rotor_constant


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
def test_fixed_inverse_is_computed_at_most_once_and_not_during_commands(name, monkeypatch):
    from koopman.prepared_allocation_v42 import PreparedDirectAllocation
    calls, original = [], torch.linalg.pinv
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(torch.linalg, 'pinv', counted)
    prepared = PreparedDirectAllocation(name)
    expected_calls = 1 if name.startswith('uuv') else 0
    assert len(calls) == expected_calls
    for _ in range(10): prepared.command([.1, .2, .3, .4], pre_tam=True)
    assert len(calls) == expected_calls


@pytest.mark.parametrize('name', ['base', 'uuv6_angled', 'uuv4'])
def test_output_mutation_and_parallel_calls_do_not_change_prepared_mapping(name):
    from koopman.prepared_allocation_v42 import PreparedDirectAllocation
    prepared = PreparedDirectAllocation(name)
    action = [.12, -.07, .2, .3]
    expected = prepared.command(action, pre_tam=True)
    changed = prepared.command(action, pre_tam=True)
    for value in changed.values(): value[:] = 99
    with pytest.raises(ValueError): prepared.wrench_matrix[:] = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: prepared.command(action, pre_tam=True), range(8)))
    for result in results:
        for key in expected:
            np.testing.assert_array_equal(result[key], expected[key])
    if name == 'uuv4': assert expected['virtual_control'][2] == 0


@pytest.mark.parametrize('action', [[0, 0, 0], [[0, 0, 0, 0]], [0, 0, 0, np.nan],
                                   [0, np.inf, 0, 0], [0, 0, 0, 1.01]])
def test_invalid_commands_rejected(action):
    from koopman.prepared_allocation_v42 import PreparedDirectAllocation
    with pytest.raises(ValueError): PreparedDirectAllocation('base').command(action, pre_tam=True)


def test_only_fixed_catalog_and_direct_seam_supported():
    from koopman.prepared_allocation_v42 import PreparedDirectAllocation
    for invalid in ('unknown', None, {}):
        with pytest.raises(ValueError): PreparedDirectAllocation(invalid)
    with pytest.raises(ValueError, match='direct'):
        PreparedDirectAllocation('base').command([0, 0, 0, 0])
