"""Additive causal runtime-to-Koopman schema-v2.1 Bridge."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import math
from typing import Any

import numpy as np

from easyuuv_nc.embodiments import qualification_record
from koopman.actuator_memory_v21 import ActuatorMemoryProxyV21
from koopman.schema_v21 import (
    KOOPMAN_TRANSITION_SCHEMA_V21,
    validate_transition_v21,
)
from workflows.koopman_bridge_v2 import KoopmanBridgeV2


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _plain(value: Any) -> Any:
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    return value


def _positive_float(value: Any, *, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(reason)
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        _fail(reason)
    return result


def _selected_scalar(value: Any, *, count: int, index: int, path: str) -> float:
    plain = _plain(value)
    if isinstance(plain, (int, float)) and not isinstance(plain, bool):
        result = float(plain)
    else:
        if (
            isinstance(plain, (str, bytes))
            or not isinstance(plain, Sequence)
            or len(plain) != count
        ):
            _fail("bridge_telemetry_shape", path)
        selected = plain[index]
        if isinstance(selected, Sequence) and not isinstance(selected, (str, bytes)):
            if len(selected) != 1:
                _fail("bridge_telemetry_shape", path)
            selected = selected[0]
        if isinstance(selected, bool) or not isinstance(selected, (int, float)):
            _fail("bridge_telemetry_shape", path)
        result = float(selected)
    if not math.isfinite(result):
        _fail("bridge_telemetry_nonfinite", path)
    return result


def build_koopman_transition_v21(fields: Mapping[str, Any]) -> dict[str, Any]:
    transition = deepcopy(dict(fields))
    validate_transition_v21(transition)
    return transition


class KoopmanBridgeV21:
    """Emit ``m[t]`` before applying ``u[t]``, then advance exactly once."""

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
        physics_dt_s: float,
        decimation: int,
        control_dt_s: float,
    ) -> None:
        self.env = env
        self.runtime = getattr(env, "unwrapped", env)
        batch_size = getattr(self.runtime, "num_envs", None)
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            _fail("bridge_telemetry_shape", "num_envs")
        if isinstance(env_index, bool) or not isinstance(env_index, int) or not 0 <= env_index < batch_size:
            _fail("bridge_env_index_out_of_range")
        try:
            topology = qualification_record(configuration)
        except KeyError as exc:
            raise ValueError(f"bridge_configuration_mismatch:{configuration}") from exc
        if getattr(self.runtime, "_embodiment_type", None) != configuration:
            _fail("bridge_configuration_mismatch")

        physics = _positive_float(physics_dt_s, reason="bridge_timing_provenance_invalid")
        control = _positive_float(control_dt_s, reason="bridge_timing_provenance_invalid")
        if isinstance(decimation, bool) or not isinstance(decimation, int) or decimation <= 0:
            _fail("bridge_timing_provenance_invalid", "decimation")
        runtime_physics = _positive_float(
            getattr(getattr(getattr(self.runtime, "sim", None), "cfg", None), "dt", None),
            reason="bridge_timing_provenance_missing",
        )
        runtime_decimation = getattr(getattr(self.runtime, "cfg", None), "decimation", None)
        if (
            isinstance(runtime_decimation, bool)
            or not isinstance(runtime_decimation, int)
            or runtime_decimation <= 0
        ):
            _fail("bridge_timing_provenance_missing", "decimation")
        if physics != runtime_physics or decimation != runtime_decimation:
            _fail("bridge_timing_provenance_mismatch")
        if control != physics * decimation:
            _fail("bridge_timing_relation_mismatch")

        self.batch_size = batch_size
        self.env_index = env_index
        self.configuration = configuration
        self.physics_dt_s = physics
        self.decimation = decimation
        self.control_dt_s = control
        self._control_mask_4 = tuple(topology["control_mask"])
        self._memory = ActuatorMemoryProxyV21(
            self._runtime_tau_s(),
            control,
            self._control_mask_4,
        )
        self._legacy = KoopmanBridgeV2(
            env=env,
            env_index=env_index,
            configuration=configuration,
            scenario=scenario,
            episode_id=episode_id,
            seed=seed,
            task_id=task_id,
            controller_mode=controller_mode,
            source_commit=source_commit,
            evidence_level=evidence_level,
            control_dt_s=control,
        )

    def _runtime_tau_s(self) -> float:
        getter = getattr(self.runtime, "get_koopman_telemetry_snapshot", None)
        if not callable(getter):
            _fail("bridge_telemetry_missing", "get_koopman_telemetry_snapshot")
        snapshot = getter()
        if not isinstance(snapshot, Mapping) or "thruster_dynamics_time_constant_s" not in snapshot:
            _fail("bridge_telemetry_missing", "thruster_dynamics_time_constant_s")
        return _selected_scalar(
            snapshot["thruster_dynamics_time_constant_s"],
            count=self.batch_size,
            index=self.env_index,
            path="thruster_dynamics_time_constant_s",
        )

    def reset(self) -> None:
        """Begin a new reset-local row sequence with exact zero memory."""
        self._memory = ActuatorMemoryProxyV21(
            self._runtime_tau_s(), self.control_dt_s, self._control_mask_4
        )
        self._legacy._step_index = 0

    def current_actuator_memory(self) -> np.ndarray:
        return self._memory.current()

    def step_and_record(
        self,
        raw_action_4: Any,
        *,
        logger: Any | None = None,
    ) -> dict[str, Any]:
        memory_t = self._memory.current()
        legacy = self._legacy.step_and_record(raw_action_4)
        row_tau = float(legacy["platform_context"]["thruster_dynamics_time_constant_s"])
        if row_tau != self._memory.tau_s:
            _fail("bridge_actuator_tau_drift")

        transition = deepcopy(legacy)
        transition["schema_version"] = KOOPMAN_TRANSITION_SCHEMA_V21
        transition["actuator_memory_4"] = memory_t.tolist()
        transition["episode_provenance"]["physics_dt_s"] = self.physics_dt_s
        transition["episode_provenance"]["decimation"] = self.decimation
        transition = build_koopman_transition_v21(transition)

        if logger is not None:
            writer = getattr(logger, "write", None)
            if not callable(writer):
                _fail("bridge_logger_invalid")
            writer(transition)
        self._memory.advance(transition["virtual_control_4"])
        return transition
