"""Isaac-free contracts for Phase 7 runtime telemetry and Koopman Bridge v2."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import torch

from easyuuv_nc.embodiments import (
    EMBODIMENT_CONFIGS,
    SUPPORTED_EMBODIMENTS,
    qualification_record,
)
from easyuuv_nc.thrust_allocation import (
    ThrusterLayout,
    allocate,
    build_wrench_matrix,
    control_channels_to_wrench,
    dof_weight_vector,
)
from koopman.schema_v2 import validate_episode_v2, validate_transition_v2
from workflows.koopman_bridge_v2 import KoopmanBridgeV2, build_koopman_transition_v2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / "easyuuv_nc" / "env" / "easyuuv_env.py"
ENV_SOURCE = ENV_PATH.read_text(encoding="utf-8")
ENV_TREE = ast.parse(ENV_SOURCE)


def _env_method_source(name: str) -> str:
    for node in ENV_TREE.body:
        if isinstance(node, ast.ClassDef) and node.name == "EasyUUVEnv":
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == name:
                    return ast.get_source_segment(ENV_SOURCE, member) or ""
    raise AssertionError(f"EasyUUVEnv.{name} source not found")


def _allocation_for(configuration: str, control: torch.Tensor) -> torch.Tensor:
    config = EMBODIMENT_CONFIGS[configuration]
    allocation = config.get("thrust_allocation")
    if allocation is None:
        from easyuuv_nc.thrust_allocation import LEGACY_CONTROL_TO_MOTOR

        return torch.einsum("mc,...c->...m", LEGACY_CONTROL_TO_MOTOR, control)
    layout = ThrusterLayout.from_specs(allocation["specs"])
    wrench = control_channels_to_wrench(
        control * torch.tensor([-1.0, 1.0, -1.0, 1.0])
    )
    return allocate(
        build_wrench_matrix(layout),
        wrench,
        mode=str(allocation["mode"]),
        weight=dof_weight_vector(allocation.get("controllable_dofs")),
    )


@pytest.mark.parametrize("configuration", SUPPORTED_EMBODIMENTS)
def test_control_mask_and_allocation_shape_cover_exact_eight(configuration: str) -> None:
    record = qualification_record(configuration)
    mask = torch.tensor(record["control_mask"], dtype=torch.float32)
    assert mask.shape == (4,)
    assert tuple(mask.int().tolist()) == tuple(record["control_mask"])

    virtual_control = torch.tensor([[0.25, -0.2, 0.4, 0.3]]) * mask
    motor = _allocation_for(configuration, virtual_control)
    assert motor.shape == (1, record["thruster_count"])
    assert record["thruster_count"] in {8, 6, 4}
    assert record["declared_control_rank"] == sum(record["control_mask"])


@pytest.mark.parametrize("configuration", ("uuv4", "uuv4_angled"))
def test_uuv4_nonzero_raw_yaw_is_masked_before_tam(configuration: str) -> None:
    raw_pid_control = torch.tensor([[0.31, -0.23, 0.79, 0.37]])
    mask = torch.tensor(qualification_record(configuration)["control_mask"])
    virtual_control = raw_pid_control * mask

    assert raw_pid_control[0, 2] != 0.0
    assert virtual_control[0, 2].item() == 0.0
    torch.testing.assert_close(
        _allocation_for(configuration, raw_pid_control),
        _allocation_for(configuration, virtual_control),
        rtol=0.0,
        atol=1.0e-6,
    )


def test_runtime_telemetry_captures_raw_action_before_clip_or_overwrite() -> None:
    source = _env_method_source("_pre_physics_step")
    capture = "self._last_raw_action_4 = actions[:, :4].detach().clone()"
    overwrite = "self._actions[:] = actions"
    clip = "self._actions[:] = torch.clip(self._actions, -1, 1).to(self.device)"
    assert capture in source
    assert source.index(capture) < source.index(overwrite) < source.index(clip)


def test_runtime_control_mask_is_catalog_derived_and_feeds_tam() -> None:
    apply_source = _env_method_source("apply_embodiment_config")
    pid_source = _env_method_source("_pid_control")
    assert "qualification_record(embodiment_type)" in apply_source
    assert "self._control_mask_4" in apply_source
    assert "virtual_control = PID_value * self._control_mask_4" in pid_source
    assert "self._last_pid_value = PID_value.detach().clone()" in pid_source
    assert "self._last_virtual_control_4 = virtual_control.detach().clone()" in pid_source
    assert "cmd = virtual_control * self._alloc_channel_sign" in pid_source


def test_runtime_wrench_and_same_call_context_capture_points_are_ordered() -> None:
    source = _env_method_source("_compute_dynamics")
    efficiency = "self._last_thruster_efficiency_n = self.thruster_efficiency_factors.detach().clone()"
    force_sum = "thruster_forces = torch.sum(thruster_forces, dim=-2)"
    torque_sum = "thruster_torques = torch.sum(thruster_torques, dim=-2)"
    wrench = "self._last_applied_wrench_6 = torch.cat((thruster_forces, thruster_torques), dim=-1).detach().clone()"
    fluid_read = "fluid_vel_w = self.get_current_fluid_velocity()"
    fluid_cache = "self._last_fluid_velocity_w = fluid_vel_w.detach().clone()"
    environment_mix = "forces = density_forces + buoyancy_forces + viscosity_forces + thruster_forces"

    for statement in (efficiency, force_sum, torque_sum, wrench, fluid_read, fluid_cache, environment_mix):
        assert statement in source
    assert source.index(efficiency) < source.index(force_sum)
    assert source.index(force_sum) < source.index(wrench)
    assert source.index(torque_sum) < source.index(wrench)
    assert source.index(wrench) < source.index(environment_mix)
    assert source.index(fluid_read) < source.index(fluid_cache) < source.index(environment_mix)


def test_runtime_telemetry_snapshot_is_clone_only_and_tokenized() -> None:
    source = _env_method_source("get_koopman_telemetry_snapshot")
    for field in (
        "raw_action_4",
        "virtual_control_4",
        "motor_pwm_n",
        "applied_wrench_6",
        "fluid_velocity_world_3",
        "thruster_efficiency_n",
        "step_token",
        "valid",
    ):
        assert f'"{field}"' in source
    assert source.count(".detach().clone()") >= 6


def test_runtime_reset_invalidates_telemetry_and_step_token() -> None:
    source = _env_method_source("_reset_idx")
    assert "self._koopman_telemetry_valid[ids] = False" in source
    assert "self._koopman_telemetry_step_token[ids] = -1" in source
    assert "self._last_raw_action_4[ids] = 0.0" in source
    assert "self._last_applied_wrench_6[ids] = 0.0" in source


def test_runtime_token_advances_only_after_complete_telemetry() -> None:
    source = _env_method_source("_compute_dynamics")
    token = "self._koopman_telemetry_step_token += 1"
    valid = "self._koopman_telemetry_valid[:] = True"
    assert token in source and valid in source
    assert source.index("self._last_applied_wrench_6") < source.index(token)
    assert source.index("self._last_fluid_velocity_w") < source.index(token)
    assert source.index("self._last_thruster_efficiency_n") < source.index(token)
    assert source.index(token) < source.index(valid)


class _FakeRobotData:
    def __init__(self, batch_size: int) -> None:
        self.root_pos_w = torch.tensor(
            [[0.0, 0.0, 2.0 + index] for index in range(batch_size)],
            dtype=torch.float32,
        )
        self.root_quat_w = torch.tensor(
            [[1.0, 0.0, 0.0, 0.0] for _ in range(batch_size)],
            dtype=torch.float32,
        )
        self.root_lin_vel_b = torch.tensor(
            [[0.1 + index, 0.2, 0.3] for index in range(batch_size)],
            dtype=torch.float32,
        )
        self.root_ang_vel_b = torch.tensor(
            [[0.01, 0.02 + index, 0.03] for index in range(batch_size)],
            dtype=torch.float32,
        )


class _FakeBatchedEnv:
    def __init__(self, configuration: str = "base", batch_size: int = 2) -> None:
        topology = qualification_record(configuration)
        self.unwrapped = self
        self.num_envs = batch_size
        self._embodiment_type = configuration
        self.cfg = SimpleNamespace(
            starting_depth=4.5,
            water_rho=997.0,
            water_beta=0.001306,
            decimation=1,
        )
        self.sim = SimpleNamespace(cfg=SimpleNamespace(dt=0.1))
        self._robot = SimpleNamespace(data=_FakeRobotData(batch_size))
        self._goal = torch.tensor(
            [[1.0, 0.0, 0.0, 0.0] for _ in range(batch_size)],
            dtype=torch.float32,
        )
        self.step_calls = 0
        self.freeze_token = False
        self.corrupt: str | None = None
        self._desired_wrench_6 = torch.full((batch_size, 6), 99.0)
        self._snapshot = {
            "configuration": configuration,
            "raw_action_4": torch.zeros((batch_size, 4)),
            "virtual_control_4": torch.zeros((batch_size, 4)),
            "motor_pwm_n": torch.zeros((batch_size, topology["thruster_count"])),
            "applied_wrench_6": torch.zeros((batch_size, 6)),
            "fluid_velocity_world_3": torch.tensor(
                [[0.2 + index, -0.1, 0.05] for index in range(batch_size)]
            ),
            "thruster_efficiency_n": torch.stack(
                [
                    torch.full((topology["thruster_count"],), 0.9 - 0.1 * index)
                    for index in range(batch_size)
                ]
            ),
            "control_mask_4": torch.tensor(topology["control_mask"]).repeat(batch_size, 1),
            "mass_kg": torch.tensor([[20.0 + index] for index in range(batch_size)]),
            "inertia_diagonal_kg_m2": torch.tensor(
                [[0.4 + index, 1.0 + index, 1.2 + index] for index in range(batch_size)]
            ),
            "com_to_cob_offset_m": torch.tensor(
                [[0.01 * index, 0.0, 0.01] for index in range(batch_size)]
            ),
            "volume_m3": torch.tensor([[0.02 + 0.01 * index] for index in range(batch_size)]),
            "drag_multiplier": torch.tensor([1.0 + index for index in range(batch_size)]),
            "thruster_dynamics_time_constant_s": torch.tensor(
                [0.05 + 0.01 * index for index in range(batch_size)]
            ),
            "water_density_kg_m3": 997.0,
            "dynamic_viscosity_pa_s": 0.001306,
            "step_token": torch.tensor([5 + index for index in range(batch_size)]),
            "valid": torch.ones(batch_size, dtype=torch.bool),
        }

    def get_koopman_telemetry_snapshot(self) -> dict:
        result = {
            key: value.detach().clone() if isinstance(value, torch.Tensor) else value
            for key, value in self._snapshot.items()
        }
        if self.corrupt == "missing":
            result.pop("applied_wrench_6")
        elif self.corrupt == "wrong_batch":
            result["motor_pwm_n"] = result["motor_pwm_n"][:1]
        elif self.corrupt == "nonfinite":
            result["applied_wrench_6"][1, 0] = float("nan")
        elif self.corrupt == "configuration":
            result["configuration"] = "uuv6"
        elif self.corrupt == "raw_swap":
            result["raw_action_4"] = result["virtual_control_4"].clone()
            result["raw_action_4"][1, 0] += 0.2
        elif self.corrupt == "mask_swap":
            result["control_mask_4"][1, 2] = 1 - result["control_mask_4"][1, 2]
        return result

    def step(self, actions: torch.Tensor):
        self.step_calls += 1
        topology = qualification_record(self._embodiment_type)
        actions = torch.as_tensor(actions, dtype=torch.float32)
        assert actions.shape == (self.num_envs, 4)
        self._snapshot["raw_action_4"] = actions.clone()
        self._snapshot["virtual_control_4"] = actions * torch.tensor(
            topology["control_mask"], dtype=torch.float32
        )
        count = topology["thruster_count"]
        self._snapshot["motor_pwm_n"] = torch.cat(
            (
                self._snapshot["virtual_control_4"],
                torch.zeros((self.num_envs, max(0, count - 4))),
            ),
            dim=1,
        )[:, :count]
        self._snapshot["applied_wrench_6"] = torch.tensor(
            [[1.0 + index, 2.0, 3.0, 4.0, 5.0, 6.0] for index in range(self.num_envs)]
        )
        if not self.freeze_token:
            self._snapshot["step_token"] += 1
        self._snapshot["valid"][:] = True
        self._robot.data.root_pos_w[:, 2] += 0.1
        return ({"policy": torch.zeros((self.num_envs, 1))}, None, None, None, {})


def _bridge(env: _FakeBatchedEnv, *, env_index: int = 1, configuration: str | None = None):
    return KoopmanBridgeV2(
        env=env,
        env_index=env_index,
        configuration=configuration or env._embodiment_type,
        scenario="fake-current",
        episode_id="episode-007",
        seed=17,
        task_id="EasyUUV-Direct-v1",
        controller_mode="pid",
        source_commit="1" * 40,
        evidence_level="local_contract",
        control_dt_s=0.1,
    )


def test_bridge_one_step_is_atomic_batch_safe_and_strict_v2() -> None:
    env = _FakeBatchedEnv()
    bridge = _bridge(env)
    action_batch = torch.tensor(
        [[-0.1, 0.2, 0.3, 0.4], [0.4, -0.3, 0.2, 0.1]], dtype=torch.float32
    )

    transition = bridge.step_and_record(action_batch)

    assert env.step_calls == 1
    validate_transition_v2(transition)
    assert transition["state_11"][0] == pytest.approx(3.0)
    assert transition["next_state_11"][0] == pytest.approx(3.1)
    assert transition["reference_5"] == [4.5, 1.0, 0.0, 0.0, 0.0]
    assert transition["raw_action_4"] == pytest.approx(action_batch[1].tolist())
    assert transition["applied_wrench_6"] == [2.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert transition["applied_wrench_6"] != env._desired_wrench_6[1].tolist()
    assert transition["platform_context"]["mass_kg"] == 21.0
    assert transition["platform_context"]["inertia_diagonal_kg_m2"] == pytest.approx([1.4, 2.0, 2.2])
    assert transition["environment_context_oracle"]["values"]["fluid_velocity_world_3"] == pytest.approx([1.2, -0.1, 0.05])
    assert transition["environment_context_estimated"]["available"] is False
    assert transition["episode_provenance"]["evidence_level"] == "local_contract"


def test_bridge_consecutive_steps_preserve_state_time_and_step_continuity() -> None:
    env = _FakeBatchedEnv()
    bridge = _bridge(env)
    action = torch.zeros((2, 4))

    first = bridge.step_and_record(action)
    second = bridge.step_and_record(action)

    assert first["next_state_11"] == second["state_11"]
    assert [row["episode_provenance"]["step_index"] for row in (first, second)] == [0, 1]
    assert [row["episode_provenance"]["simulation_time_s"] for row in (first, second)] == [0.0, 0.1]
    validate_episode_v2([first, second])


def test_bridge_writes_only_after_strict_validation() -> None:
    class Recorder:
        def __init__(self) -> None:
            self.rows: list[dict] = []

        def write(self, row: dict) -> None:
            validate_transition_v2(row)
            self.rows.append(row)

    env = _FakeBatchedEnv()
    recorder = Recorder()
    transition = _bridge(env).step_and_record(torch.zeros((2, 4)), logger=recorder)
    assert recorder.rows == [transition]


def test_named_transition_builder_calls_strict_schema_validator(monkeypatch) -> None:
    import workflows.koopman_bridge_v2 as bridge_module

    calls: list[dict] = []

    def strict_validator(payload: dict) -> None:
        calls.append(payload)

    monkeypatch.setattr(bridge_module, "validate_transition_v2", strict_validator)
    payload = {"sentinel": "complete-transition"}
    built = build_koopman_transition_v2(payload)
    assert calls == [payload]
    assert built == payload
    assert built is not payload


def test_named_transition_builder_does_not_return_invalid_payload(monkeypatch) -> None:
    import workflows.koopman_bridge_v2 as bridge_module

    def reject(_payload: dict) -> None:
        raise ValueError("schema_contract_rejected")

    monkeypatch.setattr(bridge_module, "validate_transition_v2", reject)
    with pytest.raises(ValueError, match="schema_contract_rejected"):
        build_koopman_transition_v2({"sentinel": "invalid"})


def test_step_and_record_routes_through_named_transition_builder(monkeypatch) -> None:
    import workflows.koopman_bridge_v2 as bridge_module

    calls: list[dict] = []
    original = bridge_module.build_koopman_transition_v2

    def recording_builder(payload: dict) -> dict:
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(bridge_module, "build_koopman_transition_v2", recording_builder)
    transition = _bridge(_FakeBatchedEnv()).step_and_record(torch.zeros((2, 4)))
    assert len(calls) == 1
    assert transition == calls[0]


@pytest.mark.parametrize(
    ("corrupt", "reason"),
    (
        ("missing", "bridge_telemetry_missing"),
        ("wrong_batch", "bridge_telemetry_shape"),
        ("nonfinite", "bridge_telemetry_nonfinite"),
        ("configuration", "bridge_configuration_mismatch"),
        ("raw_swap", "bridge_raw_action_mismatch"),
        ("mask_swap", "bridge_control_mask_mismatch"),
    ),
)
def test_bridge_rejects_missing_stale_or_semantically_swapped_telemetry(
    corrupt: str, reason: str
) -> None:
    env = _FakeBatchedEnv()
    env.corrupt = corrupt
    with pytest.raises(ValueError, match=reason):
        _bridge(env).step_and_record(torch.zeros((2, 4)))


def test_bridge_rejects_stale_runtime_token() -> None:
    env = _FakeBatchedEnv()
    env.freeze_token = True
    with pytest.raises(ValueError, match="bridge_telemetry_stale"):
        _bridge(env).step_and_record(torch.zeros((2, 4)))


@pytest.mark.parametrize("env_index", (-1, 2))
def test_bridge_rejects_env_index_escape(env_index: int) -> None:
    with pytest.raises(ValueError, match="bridge_env_index_out_of_range"):
        _bridge(_FakeBatchedEnv(), env_index=env_index)


@pytest.mark.parametrize(
    "action",
    (
        torch.zeros(4),
        torch.zeros((1, 4)),
        torch.zeros((2, 3)),
        torch.tensor([[0.0, 0.0, 0.0, 0.0], [float("nan"), 0.0, 0.0, 0.0]]),
    ),
)
def test_bridge_requires_exact_finite_action_batch(action: torch.Tensor) -> None:
    with pytest.raises(ValueError, match="bridge_action_(shape|nonfinite)"):
        _bridge(_FakeBatchedEnv()).step_and_record(action)


def test_bridge_rejects_configuration_mismatch_before_step() -> None:
    env = _FakeBatchedEnv("base")
    with pytest.raises(ValueError, match="bridge_configuration_mismatch"):
        _bridge(env, configuration="uuv6")
    assert env.step_calls == 0


def test_bridge_rejects_state_and_reference_dimension_drift_before_step() -> None:
    state_env = _FakeBatchedEnv()
    state_env._robot.data.root_ang_vel_b = torch.zeros((2, 2))
    with pytest.raises(ValueError, match="bridge_state_shape"):
        _bridge(state_env).step_and_record(torch.zeros((2, 4)))
    assert state_env.step_calls == 0

    reference_env = _FakeBatchedEnv()
    reference_env._goal = torch.zeros((2, 3))
    with pytest.raises(ValueError, match="bridge_reference_shape"):
        _bridge(reference_env).step_and_record(torch.zeros((2, 4)))
    assert reference_env.step_calls == 0


@pytest.mark.parametrize(
    "configuration",
    ("base", "long_body", "heavy_moderate", "asymmetric", "uuv6", "uuv6_angled"),
)
def test_fully_controllable_configurations_retain_prior_allocation_output(
    configuration: str,
) -> None:
    control = torch.tensor([[0.17, -0.29, 0.41, 0.23]])
    mask = torch.tensor(qualification_record(configuration)["control_mask"])
    assert mask.tolist() == [1, 1, 1, 1]
    torch.testing.assert_close(
        _allocation_for(configuration, control * mask),
        _allocation_for(configuration, control),
        rtol=0.0,
        atol=0.0,
    )


def test_default_off_runtime_truth_is_observational_only_source_contract() -> None:
    pid_source = _env_method_source("_pid_control")
    dynamics_source = _env_method_source("_compute_dynamics")
    assert "self._last_pid_value = PID_value.detach().clone()" in pid_source
    assert "forces = density_forces + buoyancy_forces + viscosity_forces + thruster_forces" in dynamics_source
    assert "torques = density_torques + buoyancy_torques + viscosity_torques + thruster_torques" in dynamics_source
    assert dynamics_source.rstrip().endswith("return forces, torques")
    assert "_last_applied_wrench_6 +" not in dynamics_source
    assert "_last_fluid_velocity_w +" not in dynamics_source


def test_bridge_cold_import_does_not_load_isaac_or_torch() -> None:
    script = """
import json
import sys
import workflows.koopman_bridge_v2
blocked = [name for name in sys.modules if name == 'torch' or name.startswith(('gymnasium', 'omni', 'isaaclab'))]
print(json.dumps(blocked))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
