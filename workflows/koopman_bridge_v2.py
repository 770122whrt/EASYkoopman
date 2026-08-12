"""Atomic EasyUUV runtime-to-Koopman schema-v2 transition bridge."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from easyuuv_nc.embodiments import qualification_record
from koopman.schema_v2 import KOOPMAN_TRANSITION_SCHEMA_V2, validate_transition_v2
from workflows.koopman_logging import reference_vector, state_vector_from_env


_TELEMETRY_FIELDS = frozenset(
    {
        "configuration",
        "raw_action_4",
        "virtual_control_4",
        "motor_pwm_n",
        "applied_wrench_6",
        "fluid_velocity_world_3",
        "thruster_efficiency_n",
        "control_mask_4",
        "mass_kg",
        "inertia_diagonal_kg_m2",
        "com_to_cob_offset_m",
        "volume_m3",
        "drag_multiplier",
        "thruster_dynamics_time_constant_s",
        "water_density_kg_m3",
        "dynamic_viscosity_pa_s",
        "step_token",
        "valid",
    }
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if not detail else f"{reason}:{detail}")


def _plain(value: Any) -> Any:
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return value


def _number(value: Any, *, path: str, telemetry: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("bridge_telemetry_shape" if telemetry else "bridge_state_shape", path)
    result = float(value)
    if not math.isfinite(result):
        _fail("bridge_telemetry_nonfinite" if telemetry else "bridge_state_nonfinite", path)
    return result


def _vector(value: Any, width: int, *, path: str, reason: str) -> list[float]:
    value = _plain(value)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != width:
        _fail(reason, path)
    result: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            _fail(reason, f"{path}[{index}]")
        numeric = float(item)
        if not math.isfinite(numeric):
            nonfinite_reason = (
                "bridge_telemetry_nonfinite"
                if reason == "bridge_telemetry_shape"
                else reason.replace("shape", "nonfinite")
            )
            _fail(nonfinite_reason, f"{path}[{index}]")
        result.append(numeric)
    return result


def _batch_rows(value: Any, *, batch_size: int, width: int, path: str) -> list[list[float]]:
    value = _plain(value)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != batch_size:
        _fail("bridge_telemetry_shape", path)
    return [
        _vector(row, width, path=f"{path}[{index}]", reason="bridge_telemetry_shape")
        for index, row in enumerate(value)
    ]


def _selected_scalar(value: Any, *, batch_size: int, env_index: int, path: str) -> float:
    value = _plain(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
        if not math.isfinite(result):
            _fail("bridge_telemetry_nonfinite", path)
        return result
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != batch_size:
        _fail("bridge_telemetry_shape", path)
    selected = value[env_index]
    if isinstance(selected, Sequence) and not isinstance(selected, (str, bytes)):
        if len(selected) != 1:
            _fail("bridge_telemetry_shape", path)
        selected = selected[0]
    return _number(selected, path=f"{path}[{env_index}]", telemetry=True)


def _batch_ints(value: Any, *, batch_size: int, path: str) -> list[int]:
    value = _plain(value)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != batch_size:
        _fail("bridge_telemetry_shape", path)
    result: list[int] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int):
            _fail("bridge_telemetry_shape", f"{path}[{index}]")
        result.append(item)
    return result


def _batch_bools(value: Any, *, batch_size: int, path: str) -> list[bool]:
    value = _plain(value)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != batch_size:
        _fail("bridge_telemetry_shape", path)
    if any(type(item) is not bool for item in value):
        _fail("bridge_telemetry_shape", path)
    return list(value)


def _snapshot(runtime: Any) -> Mapping[str, Any]:
    getter = getattr(runtime, "get_koopman_telemetry_snapshot", None)
    if not callable(getter):
        _fail("bridge_telemetry_missing", "get_koopman_telemetry_snapshot")
    snapshot = getter()
    if not isinstance(snapshot, Mapping):
        _fail("bridge_telemetry_shape", "snapshot")
    return snapshot


def _require_snapshot_fields(snapshot: Mapping[str, Any]) -> None:
    missing = sorted(_TELEMETRY_FIELDS - set(snapshot))
    if missing:
        _fail("bridge_telemetry_missing", ",".join(missing))


def _state(runtime: Any, env_index: int) -> list[float]:
    try:
        value = state_vector_from_env(runtime, env_index)
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("bridge_state_shape") from exc
    return _vector(value, 11, path="state_11", reason="bridge_state_shape")


def _reference(runtime: Any, env_index: int) -> list[float]:
    try:
        value = reference_vector(float(runtime.cfg.starting_depth), runtime._goal[env_index])
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("bridge_reference_shape") from exc
    return _vector(value, 5, path="reference_5", reason="bridge_reference_shape")


def _action_batch(raw_action_4: Any, *, batch_size: int) -> list[list[float]]:
    value = _plain(raw_action_4)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != batch_size:
        _fail("bridge_action_shape")
    result: list[list[float]] = []
    for row_index, row in enumerate(value):
        row = _plain(row)
        if isinstance(row, (str, bytes)) or not isinstance(row, Sequence) or len(row) != 4:
            _fail("bridge_action_shape", str(row_index))
        normalized: list[float] = []
        for column, item in enumerate(row):
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                _fail("bridge_action_shape", f"{row_index},{column}")
            numeric = float(item)
            if not math.isfinite(numeric):
                _fail("bridge_action_nonfinite", f"{row_index},{column}")
            if numeric < -1.000001 or numeric > 1.000001:
                _fail("bridge_action_out_of_bounds", f"{row_index},{column}")
            normalized.append(numeric)
        result.append(normalized)
    return result


class KoopmanBridgeV2:
    """Bind exactly one batched EasyUUV step to one strict v2 transition."""

    def __init__(
        self,
        *,
        env: Any,
        env_index: int,
        configuration: str,
        scenario: str,
        episode_id: str,
        seed: int,
        task_id: str,
        controller_mode: str,
        source_commit: str,
        evidence_level: str,
        control_dt_s: float,
    ) -> None:
        self.env = env
        self.runtime = getattr(env, "unwrapped", env)
        batch_size = getattr(self.runtime, "num_envs", None)
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            _fail("bridge_telemetry_shape", "num_envs")
        if isinstance(env_index, bool) or not isinstance(env_index, int) or not 0 <= env_index < batch_size:
            _fail("bridge_env_index_out_of_range", str(env_index))
        active_configuration = getattr(self.runtime, "_embodiment_type", None)
        if active_configuration != configuration:
            _fail(
                "bridge_configuration_mismatch",
                f"expected={configuration};actual={active_configuration}",
            )
        try:
            self.topology = qualification_record(configuration)
        except KeyError as exc:
            raise ValueError(f"bridge_configuration_mismatch:{configuration}") from exc
        if isinstance(control_dt_s, bool) or not isinstance(control_dt_s, (int, float)):
            _fail("bridge_control_dt_invalid")
        self.control_dt_s = float(control_dt_s)
        if not math.isfinite(self.control_dt_s) or self.control_dt_s <= 0.0:
            _fail("bridge_control_dt_invalid")
        if isinstance(seed, bool) or not isinstance(seed, int):
            _fail("bridge_provenance_invalid", "seed")

        self.batch_size = batch_size
        self.env_index = env_index
        self.configuration = configuration
        self.scenario = scenario
        self.episode_id = episode_id
        self.seed = seed
        self.task_id = task_id
        self.controller_mode = controller_mode
        self.source_commit = source_commit
        self.evidence_level = evidence_level
        self._step_index = 0

    def step_and_record(self, raw_action_4: Any, *, logger: Any | None = None) -> dict[str, Any]:
        actions = _action_batch(raw_action_4, batch_size=self.batch_size)
        state = _state(self.runtime, self.env_index)
        reference = _reference(self.runtime, self.env_index)
        before = _snapshot(self.runtime)
        if "step_token" not in before:
            _fail("bridge_telemetry_missing", "step_token")
        before_tokens = _batch_ints(
            before["step_token"], batch_size=self.batch_size, path="step_token"
        )

        self.env.step(raw_action_4)

        after = _snapshot(self.runtime)
        _require_snapshot_fields(after)
        if after["configuration"] != self.configuration:
            _fail("bridge_configuration_mismatch", str(after["configuration"]))
        tokens = _batch_ints(after["step_token"], batch_size=self.batch_size, path="step_token")
        valid = _batch_bools(after["valid"], batch_size=self.batch_size, path="valid")
        if not valid[self.env_index]:
            _fail("bridge_telemetry_invalid", str(self.env_index))
        if tokens[self.env_index] <= before_tokens[self.env_index]:
            _fail("bridge_telemetry_stale", str(tokens[self.env_index]))

        count = int(self.topology["thruster_count"])
        raw_rows = _batch_rows(
            after["raw_action_4"], batch_size=self.batch_size, width=4, path="raw_action_4"
        )
        virtual_rows = _batch_rows(
            after["virtual_control_4"],
            batch_size=self.batch_size,
            width=4,
            path="virtual_control_4",
        )
        mask_rows = _batch_rows(
            after["control_mask_4"], batch_size=self.batch_size, width=4, path="control_mask_4"
        )
        motor_rows = _batch_rows(
            after["motor_pwm_n"], batch_size=self.batch_size, width=count, path="motor_pwm_n"
        )
        wrench_rows = _batch_rows(
            after["applied_wrench_6"],
            batch_size=self.batch_size,
            width=6,
            path="applied_wrench_6",
        )
        fluid_rows = _batch_rows(
            after["fluid_velocity_world_3"],
            batch_size=self.batch_size,
            width=3,
            path="fluid_velocity_world_3",
        )
        efficiency_rows = _batch_rows(
            after["thruster_efficiency_n"],
            batch_size=self.batch_size,
            width=count,
            path="thruster_efficiency_n",
        )
        inertia_rows = _batch_rows(
            after["inertia_diagonal_kg_m2"],
            batch_size=self.batch_size,
            width=3,
            path="inertia_diagonal_kg_m2",
        )
        offset_rows = _batch_rows(
            after["com_to_cob_offset_m"],
            batch_size=self.batch_size,
            width=3,
            path="com_to_cob_offset_m",
        )

        selected_action = actions[self.env_index]
        selected_raw = raw_rows[self.env_index]
        if any(abs(actual - expected) > 1.0e-6 for actual, expected in zip(selected_raw, selected_action, strict=True)):
            _fail("bridge_raw_action_mismatch")
        expected_control_mask = [float(value) for value in self.topology["control_mask"]]
        if mask_rows[self.env_index] != expected_control_mask:
            _fail("bridge_control_mask_mismatch")
        selected_virtual = virtual_rows[self.env_index]
        for index, enabled in enumerate(expected_control_mask):
            if enabled == 0.0 and selected_virtual[index] != 0.0:
                _fail("bridge_control_mask_mismatch", f"virtual_control_4[{index}]")

        mass = _selected_scalar(
            after["mass_kg"], batch_size=self.batch_size, env_index=self.env_index, path="mass_kg"
        )
        volume = _selected_scalar(
            after["volume_m3"], batch_size=self.batch_size, env_index=self.env_index, path="volume_m3"
        )
        drag = _selected_scalar(
            after["drag_multiplier"],
            batch_size=self.batch_size,
            env_index=self.env_index,
            path="drag_multiplier",
        )
        tau = _selected_scalar(
            after["thruster_dynamics_time_constant_s"],
            batch_size=self.batch_size,
            env_index=self.env_index,
            path="thruster_dynamics_time_constant_s",
        )
        density = _selected_scalar(
            after["water_density_kg_m3"],
            batch_size=self.batch_size,
            env_index=self.env_index,
            path="water_density_kg_m3",
        )
        viscosity = _selected_scalar(
            after["dynamic_viscosity_pa_s"],
            batch_size=self.batch_size,
            env_index=self.env_index,
            path="dynamic_viscosity_pa_s",
        )

        motor = motor_rows[self.env_index]
        transition: dict[str, Any] = {
            "schema_version": KOOPMAN_TRANSITION_SCHEMA_V2,
            "state_11": state,
            "reference_5": reference,
            "raw_action_4": selected_raw,
            "virtual_control_4": selected_virtual,
            "motor_pwm_padded_8": motor + [0.0] * (8 - count),
            "thruster_mask_8": [1] * count + [0] * (8 - count),
            "applied_wrench_6": wrench_rows[self.env_index],
            "platform_context": {
                "configuration": self.configuration,
                "thruster_count": count,
                "control_channels": list(self.topology["control_channels"]),
                "control_mask": list(self.topology["control_mask"]),
                "allocation_mode": self.topology["allocation_mode"],
                "declared_control_rank": self.topology["declared_control_rank"],
                "mass_kg": mass,
                "inertia_diagonal_kg_m2": inertia_rows[self.env_index],
                "com_to_cob_offset_m": offset_rows[self.env_index],
                "volume_m3": volume,
                "drag_multiplier": drag,
                "thruster_dynamics_time_constant_s": tau,
            },
            "environment_context_oracle": {
                "available": True,
                "method": "easyuuv_runtime_truth",
                "method_version": "1",
                "source_kind": "simulator_ground_truth",
                "source_signals": ["get_koopman_telemetry_snapshot"],
                "values": {
                    "fluid_velocity_world_3": fluid_rows[self.env_index],
                    "water_density_kg_m3": density,
                    "dynamic_viscosity_pa_s": viscosity,
                    "drag_multiplier": drag,
                    "thruster_efficiency_n": efficiency_rows[self.env_index],
                },
                "units": {
                    "fluid_velocity_world_3": "m/s",
                    "water_density_kg_m3": "kg/m^3",
                    "dynamic_viscosity_pa_s": "Pa*s",
                    "drag_multiplier": "1",
                    "thruster_efficiency_n": "1",
                },
                "frames": {
                    "fluid_velocity_world_3": "world",
                    "water_density_kg_m3": "scalar",
                    "dynamic_viscosity_pa_s": "scalar",
                    "drag_multiplier": "platform",
                    "thruster_efficiency_n": "canonical_thruster_order",
                },
                "value_provenance": {
                    key: f"runtime_step_token:{tokens[self.env_index]}"
                    for key in (
                        "fluid_velocity_world_3",
                        "water_density_kg_m3",
                        "dynamic_viscosity_pa_s",
                        "drag_multiplier",
                        "thruster_efficiency_n",
                    )
                },
            },
            "environment_context_estimated": {
                "available": False,
                "method": "",
                "method_version": "",
                "source_kind": "unavailable",
                "source_signals": [],
                "values": {},
                "units": {},
                "frames": {},
                "value_provenance": {},
            },
            "next_state_11": _state(self.runtime, self.env_index),
            "episode_provenance": {
                "configuration": self.configuration,
                "scenario": self.scenario,
                "episode_id": self.episode_id,
                "step_index": self._step_index,
                "seed": self.seed,
                "simulation_time_s": self._step_index * self.control_dt_s,
                "control_dt_s": self.control_dt_s,
                "task_id": self.task_id,
                "controller_mode": self.controller_mode,
                "source_commit": self.source_commit,
                "evidence_level": self.evidence_level,
            },
        }
        validate_transition_v2(transition)
        if logger is not None:
            writer = getattr(logger, "write", None)
            if not callable(writer):
                _fail("bridge_logger_invalid")
            writer(transition)
        self._step_index += 1
        return transition
