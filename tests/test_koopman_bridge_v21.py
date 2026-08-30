"""Isaac-free causal Bridge-v2.1 contracts."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys
from types import SimpleNamespace, ModuleType

import numpy as np
import pytest
import torch

from easyuuv_nc.embodiments import qualification_record
from koopman.schema_v21 import validate_episode_v21, validate_transition_v21
from workflows.koopman_bridge_v21 import KoopmanBridgeV21


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THRUSTER_DYNAMICS_PATH = PROJECT_ROOT / "easyuuv_nc" / "env" / "thruster_dynamics.py"


class _RobotData:
    def __init__(self, count: int) -> None:
        self.root_pos_w = torch.tensor([[0.0, 0.0, 2.0]] * count)
        self.root_quat_w = torch.tensor([[1.0, 0.0, 0.0, 0.0]] * count)
        self.root_lin_vel_b = torch.tensor([[0.1, 0.2, 0.3]] * count)
        self.root_ang_vel_b = torch.tensor([[0.01, 0.02, 0.03]] * count)


class _FakeEnv:
    def __init__(
        self,
        configuration: str = "base",
        *,
        diagnostic_scale: float = 1.0,
        tau_s: float = 0.2,
    ) -> None:
        topology = qualification_record(configuration)
        self.unwrapped = self
        self.num_envs = 1
        self._embodiment_type = configuration
        self.cfg = SimpleNamespace(
            starting_depth=4.5,
            water_rho=997.0,
            water_beta=0.001306,
            decimation=2,
        )
        self.sim = SimpleNamespace(cfg=SimpleNamespace(dt=0.05))
        self._robot = SimpleNamespace(data=_RobotData(1))
        self._goal = torch.tensor([[1.0, 0.0, 0.0, 0.0]])
        self._diagnostic_scale = diagnostic_scale
        self._snapshot = {
            "configuration": configuration,
            "raw_action_4": torch.zeros((1, 4)),
            "virtual_control_4": torch.zeros((1, 4)),
            "motor_pwm_n": torch.zeros((1, topology["thruster_count"])),
            "applied_wrench_6": torch.zeros((1, 6)),
            "fluid_velocity_world_3": torch.zeros((1, 3)),
            "thruster_efficiency_n": torch.ones((1, topology["thruster_count"])),
            "control_mask_4": torch.tensor(topology["control_mask"]).reshape(1, 4),
            "mass_kg": torch.tensor([[22.0]]),
            "inertia_diagonal_kg_m2": torch.tensor([[0.4, 1.0, 1.2]]),
            "com_to_cob_offset_m": torch.tensor([[0.0, 0.0, 0.01]]),
            "volume_m3": torch.tensor([[0.023]]),
            "drag_multiplier": torch.tensor([1.0]),
            "thruster_dynamics_time_constant_s": torch.tensor([tau_s]),
            "water_density_kg_m3": 997.0,
            "dynamic_viscosity_pa_s": 0.001306,
            "step_token": torch.tensor([0]),
            "valid": torch.ones(1, dtype=torch.bool),
        }

    def get_koopman_telemetry_snapshot(self) -> dict:
        return {
            key: value.detach().clone() if isinstance(value, torch.Tensor) else value
            for key, value in self._snapshot.items()
        }

    def step(self, actions: torch.Tensor):
        action = torch.as_tensor(actions, dtype=torch.float32)
        topology = qualification_record(self._embodiment_type)
        virtual = action * torch.tensor(topology["control_mask"], dtype=torch.float32)
        count = int(topology["thruster_count"])
        self._snapshot["raw_action_4"] = action.clone()
        self._snapshot["virtual_control_4"] = virtual.clone()
        self._snapshot["motor_pwm_n"] = torch.full(
            (1, count), 0.1 * self._diagnostic_scale
        )
        self._snapshot["applied_wrench_6"] = torch.full(
            (1, 6), 0.2 * self._diagnostic_scale
        )
        self._snapshot["fluid_velocity_world_3"] = torch.full(
            (1, 3), 0.3 * self._diagnostic_scale
        )
        self._snapshot["thruster_efficiency_n"] = torch.full(
            (1, count), 0.9 * self._diagnostic_scale
        )
        self._snapshot["step_token"] += 1
        self._robot.data.root_pos_w[:, 2] += 0.1
        return ({"policy": torch.zeros((1, 1))}, None, None, None, {})


def _bridge(env: _FakeEnv) -> KoopmanBridgeV21:
    return KoopmanBridgeV21(
        env=env,
        env_index=0,
        configuration=env._embodiment_type,
        scenario="phase81-local",
        episode_id="episode-001",
        seed=17,
        task_id="EasyUUV-Direct-v1",
        controller_mode="pid",
        source_commit="1" * 40,
        evidence_level="local_contract",
        physics_dt_s=0.05,
        decimation=2,
        control_dt_s=0.1,
    )


def test_bridge_emits_current_memory_then_advances_once() -> None:
    bridge = _bridge(_FakeEnv())
    control = torch.tensor([[0.4, -0.3, 0.2, 0.1]])

    first = bridge.step_and_record(control)
    second = bridge.step_and_record(control)

    validate_transition_v21(first)
    validate_episode_v21([first, second])
    assert np.asarray(first["actuator_memory_4"], dtype=np.float64).tobytes() == np.zeros(
        4, dtype=np.float64
    ).tobytes()
    recorded_tau_s = float(first["platform_context"]["thruster_dynamics_time_constant_s"])
    expected = (1.0 - math.exp(-0.1 / recorded_tau_s)) * control.numpy()[0].astype(
        np.float64
    )
    np.testing.assert_allclose(
        second["actuator_memory_4"], expected, atol=1e-12, rtol=1e-12
    )
    assert first["episode_provenance"]["physics_dt_s"] == 0.05
    assert first["episode_provenance"]["decimation"] == 2


def test_bridge_reset_prevents_cross_episode_memory_inheritance() -> None:
    bridge = _bridge(_FakeEnv())
    bridge.step_and_record(torch.ones((1, 4)) * 0.5)
    assert np.any(bridge.current_actuator_memory() != 0.0)

    bridge.reset()
    row = bridge.step_and_record(torch.zeros((1, 4)))

    assert np.asarray(row["actuator_memory_4"], dtype=np.float64).tobytes() == np.zeros(
        4, dtype=np.float64
    ).tobytes()
    assert row["episode_provenance"]["step_index"] == 0


def test_bridge_reset_refreshes_episode_local_tau_without_inheriting_state() -> None:
    env = _FakeEnv(tau_s=0.2)
    bridge = _bridge(env)
    control = torch.ones((1, 4)) * 0.5
    bridge.step_and_record(control)
    env._snapshot["thruster_dynamics_time_constant_s"][:] = 0.4

    bridge.reset()
    first = bridge.step_and_record(control)
    second = bridge.step_and_record(control)

    assert first["actuator_memory_4"] == [0.0] * 4
    expected = (1.0 - math.exp(-0.1 / float(np.float32(0.4)))) * 0.5
    np.testing.assert_allclose(
        second["actuator_memory_4"], [expected] * 4, atol=1e-12, rtol=1e-12
    )


def test_forbidden_diagnostic_mutations_do_not_change_primary_memory_bytes() -> None:
    control = torch.tensor([[0.25, -0.2, 0.1, 0.3]])
    plain = _bridge(_FakeEnv(diagnostic_scale=1.0))
    mutated = _bridge(_FakeEnv(diagnostic_scale=3.0))

    row_plain = plain.step_and_record(control)
    row_mutated = mutated.step_and_record(control)

    primary_plain = np.asarray(
        row_plain["state_11"]
        + row_plain["actuator_memory_4"]
        + row_plain["virtual_control_4"],
        dtype=np.float64,
    )
    primary_mutated = np.asarray(
        row_mutated["state_11"]
        + row_mutated["actuator_memory_4"]
        + row_mutated["virtual_control_4"],
        dtype=np.float64,
    )
    assert primary_plain.tobytes() == primary_mutated.tobytes()
    assert row_plain["motor_pwm_padded_8"] != row_mutated["motor_pwm_padded_8"]
    assert row_plain["applied_wrench_6"] != row_mutated["applied_wrench_6"]


def test_uuv4_yaw_is_masked_before_memory_advance() -> None:
    bridge = _bridge(_FakeEnv("uuv4"))
    action = torch.tensor([[0.1, -0.2, 0.9, 0.3]])

    first = bridge.step_and_record(action)
    second = bridge.step_and_record(action)

    assert first["virtual_control_4"][2] == 0.0
    assert first["actuator_memory_4"][2] == 0.0
    assert second["actuator_memory_4"][2] == 0.0


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("physics_dt_s", 0.04, "bridge_timing_provenance_mismatch"),
        ("decimation", 3, "bridge_timing_provenance_mismatch"),
        ("control_dt_s", 0.11, "bridge_timing_relation_mismatch"),
    ),
)
def test_bridge_rejects_runtime_timing_disagreement(field: str, value, reason: str) -> None:
    env = _FakeEnv()
    kwargs = {
        "env": env,
        "env_index": 0,
        "configuration": "base",
        "scenario": "phase81-local",
        "episode_id": "episode-001",
        "seed": 17,
        "task_id": "EasyUUV-Direct-v1",
        "controller_mode": "pid",
        "source_commit": "1" * 40,
        "evidence_level": "local_contract",
        "physics_dt_s": 0.05,
        "decimation": 2,
        "control_dt_s": 0.1,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=reason):
        KoopmanBridgeV21(**kwargs)


def test_proxy_control_interval_matches_two_float32_simulator_substeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compat = ModuleType("isaaclab_compat")
    compat.quat_from_euler_xyz = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, "isaaclab_compat", compat)
    spec = importlib.util.spec_from_file_location("_phase81_dynamics", THRUSTER_DYNAMICS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "_phase81_dynamics", module)
    spec.loader.exec_module(module)

    tau_s = 0.2
    bridge = _bridge(_FakeEnv(tau_s=tau_s))
    control = torch.tensor([[0.4, -0.3, 0.2, 0.1]], dtype=torch.float32)
    bridge.step_and_record(control)
    proxy_state = bridge.current_actuator_memory()
    dynamics = module.DynamicsFirstOrder(1, 4, tau_s, torch.device("cpu"))
    dynamics.update(control, torch.tensor([0.05]))
    simulator_state = dynamics.update(control, torch.tensor([0.1])).numpy()[0]

    np.testing.assert_allclose(
        proxy_state,
        simulator_state,
        atol=8 * np.finfo(np.float32).eps,
        rtol=8 * np.finfo(np.float32).eps,
    )


def test_bridge_reuses_proxy_instead_of_copying_recurrence() -> None:
    source = (PROJECT_ROOT / "workflows" / "koopman_bridge_v21.py").read_text(
        encoding="utf-8"
    )

    assert "ActuatorMemoryProxyV21" in source
    assert ".current()" in source
    assert ".advance(" in source
    assert "math.exp" not in source
