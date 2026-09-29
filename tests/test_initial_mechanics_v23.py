"""Static initialization contract; actual first-step physics is checked on Isaac."""
from types import SimpleNamespace

import pytest

from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS


def config(**kwargs):
    values = dict(physics_initialization_mode='authored_static_v1', initial_embodiment_type='uuv6',
                  inertia_sync_mode='declared_v1', embodiment_configs=EMBODIMENT_CONFIGS,
                  domain_randomization=SimpleNamespace(use_custom_randomization=False))
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_legacy_initialization_needs_no_runtime_or_new_config():
    from easyuuv_nc.initialization_v23 import initial_mechanics
    assert initial_mechanics(SimpleNamespace()) is None


@pytest.mark.parametrize('name', ['base', 'uuv6', 'uuv4'])
def test_static_initialization_uses_same_configuration_as_control_chain(name):
    from easyuuv_nc.initialization_v23 import initial_mechanics
    result = initial_mechanics(config(initial_embodiment_type=name))
    assert result['mass_kg'] == EMBODIMENT_CONFIGS[name]['mass']
    assert result['inertia_diagonal_kg_m2'] == EMBODIMENT_CONFIGS[name]['inertia_tensors']


@pytest.mark.parametrize('change', [
    {'physics_initialization_mode': 'unknown'}, {'initial_embodiment_type': 'missing'},
    {'inertia_sync_mode': 'legacy'},
    {'domain_randomization': SimpleNamespace(use_custom_randomization=True)},
])
def test_unvalidated_modes_fail_closed(change):
    from easyuuv_nc.initialization_v23 import initial_mechanics
    with pytest.raises(ValueError):
        initial_mechanics(config(**change))


def test_runtime_switch_is_rejected_before_changing_parameters():
    from test_inertia_sync_v23 import method, runtime
    env, view = runtime()
    env.cfg.physics_initialization_mode = 'authored_static_v1'
    env.cfg.initial_embodiment_type = 'uuv6'
    with pytest.raises(ValueError, match='static_initialization_configuration_switch'):
        method('apply_embodiment_config', mechanical_prefix=True)(env, 'uuv4')
    assert not view.calls


def test_cli_records_initialization_mode():
    from workflows.trace_control_v23 import parser, request
    assert request(parser().parse_args(['--run-id', 'example']))['physics_initialization_mode'] == 'legacy'
    args = parser().parse_args(['--run-id', 'example', '--initialization', 'authored_static_v1'])
    assert request(args)['physics_initialization_mode'] == 'authored_static_v1'
