"""Causal actuator-memory SO(3) rollout and metrics for Phase 8.1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType
from typing import Any

import numpy as np

from koopman.actuator_memory_v21 import ActuatorMemoryProxyV21
from koopman.contracts_v21 import (
    OFFICIAL_ANGULAR_VELOCITY_ABS_MAX_V21,
    OFFICIAL_DEPTH_ABS_MAX_V21,
    OFFICIAL_LINEAR_VELOCITY_ABS_MAX_V21,
    OFFICIAL_ROLLOUT_HORIZONS_V21,
    ROLLOUT_POLICY_VERSION_V21,
)
from koopman.evidence_v2 import canonical_sha256
from koopman.so3_v21 import (
    ANGULAR_VELOCITY_SLICE_V21,
    DEPTH_INDEX_V21,
    LINEAR_VELOCITY_SLICE_V21,
    QUATERNION_SLICE_V21,
    STATE_DIM_V21,
    apply_increment_target_v21,
    normalize_quaternion_v21,
    so3_geodesic_radians_v21,
)


CONTROL_DIM_V21 = 4
ACTUATOR_MEMORY_DIM_V21 = 4
METRIC_SCHEMA_VERSION_V21 = "phase8.1-episode-metrics-v1"
REQUIRED_HORIZONS_V21 = OFFICIAL_ROLLOUT_HORIZONS_V21
REQUIRED_HORIZON_LABELS_V21 = ("one_step", "5", "20", "60", "full")
OFFICIAL_ERROR_METRICS_V21 = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)
_SHA256_V21 = re.compile(r"^[0-9a-f]{64}$")


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _positive(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("rollout_policy_invalid", name)
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        _fail("rollout_policy_invalid", name)
    return result


def _readonly_rows(value: Any, width: int, name: str) -> np.ndarray:
    array = np.array(value, dtype=np.float64, copy=True)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] != width:
        _fail("evaluation_shape_invalid", name)
    if not np.isfinite(array).all():
        _fail("evaluation_nonfinite", name)
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class RolloutAnalysisPolicyV21:
    horizons: tuple[int | str, ...]
    depth_abs_max: float
    linear_velocity_abs_max: float
    angular_velocity_abs_max: float
    version: str = ROLLOUT_POLICY_VERSION_V21
    policy_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        horizons = tuple(self.horizons)
        if horizons != REQUIRED_HORIZONS_V21 or self.version != ROLLOUT_POLICY_VERSION_V21:
            _fail("rollout_policy_invalid")
        object.__setattr__(self, "horizons", horizons)
        for name in (
            "depth_abs_max",
            "linear_velocity_abs_max",
            "angular_velocity_abs_max",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        object.__setattr__(self, "policy_sha256", canonical_sha256(self.payload()))

    def payload(self) -> dict[str, Any]:
        return {
            "angular_velocity_abs_max": self.angular_velocity_abs_max,
            "depth_abs_max": self.depth_abs_max,
            "horizons": list(self.horizons),
            "linear_velocity_abs_max": self.linear_velocity_abs_max,
            "version": self.version,
        }


OFFICIAL_ROLLOUT_POLICY_V21 = RolloutAnalysisPolicyV21(
    horizons=OFFICIAL_ROLLOUT_HORIZONS_V21,
    depth_abs_max=OFFICIAL_DEPTH_ABS_MAX_V21,
    linear_velocity_abs_max=OFFICIAL_LINEAR_VELOCITY_ABS_MAX_V21,
    angular_velocity_abs_max=OFFICIAL_ANGULAR_VELOCITY_ABS_MAX_V21,
)


@dataclass(frozen=True)
class RolloutEpisodeV21:
    episode_id: str
    configuration: str
    states_11: np.ndarray
    actuator_memory_4: np.ndarray
    virtual_control_4: np.ndarray
    targets_11: np.ndarray
    tau_s: float
    control_dt_s: float
    control_mask_4: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not self.episode_id:
            _fail("evaluation_episode_id_invalid")
        if not isinstance(self.configuration, str) or not self.configuration:
            _fail("evaluation_configuration_invalid")
        states = _readonly_rows(self.states_11, STATE_DIM_V21, "states_11")
        memory = _readonly_rows(
            self.actuator_memory_4, ACTUATOR_MEMORY_DIM_V21, "actuator_memory_4"
        )
        controls = _readonly_rows(
            self.virtual_control_4, CONTROL_DIM_V21, "virtual_control_4"
        )
        targets = _readonly_rows(self.targets_11, STATE_DIM_V21, "targets_11")
        if not (
            states.shape[0] == memory.shape[0] == controls.shape[0] == targets.shape[0]
        ):
            _fail("evaluation_shape_invalid", "row_count")
        for row in np.vstack((states[:, QUATERNION_SLICE_V21], targets[:, QUATERNION_SLICE_V21])):
            normalize_quaternion_v21(row)
        proxy = ActuatorMemoryProxyV21(self.tau_s, self.control_dt_s, self.control_mask_4)
        mask = tuple(int(item) for item in proxy.control_mask_4)
        disabled = np.asarray(mask) == 0
        if np.any(memory[:, disabled] != 0.0) or np.any(controls[:, disabled] != 0.0):
            _fail("evaluation_disabled_channel_nonzero")
        object.__setattr__(self, "states_11", states)
        object.__setattr__(self, "actuator_memory_4", memory)
        object.__setattr__(self, "virtual_control_4", controls)
        object.__setattr__(self, "targets_11", targets)
        object.__setattr__(self, "tau_s", proxy.tau_s)
        object.__setattr__(self, "control_dt_s", proxy.control_dt_s)
        object.__setattr__(self, "control_mask_4", mask)

    @property
    def transition_count(self) -> int:
        return int(self.states_11.shape[0])

    @classmethod
    def from_dataset(cls, dataset: Any) -> "RolloutEpisodeV21":
        """Create one trajectory from a validated single-episode v2.1 dataset."""

        configurations = tuple(dataset.configurations)
        episode_ids = tuple(dataset.episode_ids)
        if len(set(configurations)) != 1 or len(set(episode_ids)) != 1:
            _fail("evaluation_episode_mixed")
        contexts = tuple(dataset.platform_contexts)
        provenance = tuple(dataset.episode_provenance)
        tau_values = {float(item["thruster_dynamics_time_constant_s"]) for item in contexts}
        dt_values = {float(item["control_dt_s"]) for item in provenance}
        masks = {tuple(int(value) for value in item["control_mask"]) for item in contexts}
        if len(tau_values) != 1 or len(dt_values) != 1 or len(masks) != 1:
            _fail("evaluation_episode_context_drift")
        return cls(
            episode_id=episode_ids[0],
            configuration=configurations[0],
            states_11=dataset.state_11,
            actuator_memory_4=dataset.actuator_memory_4,
            virtual_control_4=dataset.virtual_control_4,
            targets_11=dataset.Y,
            tau_s=next(iter(tau_values)),
            control_dt_s=next(iter(dt_values)),
            control_mask_4=next(iter(masks)),
        )


@dataclass(frozen=True)
class RolloutTraceV21:
    episode_id: str
    configuration: str
    start: int
    requested_steps: int
    status: str
    reason_code: str | None
    predictions: np.ndarray
    memory_inputs_4: np.ndarray
    attempted_transition_count: int
    completed_transition_count: int
    nonfinite_count: int
    invalid_quaternion_count: int
    quaternion_unit_norm_drift_count: int
    divergence_count: int
    quaternion_projection_count: int = 0

    def __post_init__(self) -> None:
        if self.status not in {"success", "failed"}:
            _fail("rollout_status_invalid")
        if (self.status == "success") != (self.reason_code is None):
            _fail("rollout_reason_invalid")
        predictions = np.array(self.predictions, dtype=np.float64, copy=True).reshape(
            -1, STATE_DIM_V21
        )
        memory = np.array(self.memory_inputs_4, dtype=np.float64, copy=True).reshape(
            -1, ACTUATOR_MEMORY_DIM_V21
        )
        if predictions.shape[0] != self.completed_transition_count:
            _fail("rollout_count_invalid")
        if memory.shape[0] != self.attempted_transition_count:
            _fail("rollout_count_invalid")
        for name in (
            "attempted_transition_count",
            "completed_transition_count",
            "nonfinite_count",
            "invalid_quaternion_count",
            "quaternion_unit_norm_drift_count",
            "divergence_count",
            "quaternion_projection_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _fail("rollout_count_invalid", name)
        if self.quaternion_projection_count != 0:
            _fail("quaternion_projection_forbidden")
        predictions.setflags(write=False)
        memory.setflags(write=False)
        object.__setattr__(self, "predictions", predictions)
        object.__setattr__(self, "memory_inputs_4", memory)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted_transition_count": self.attempted_transition_count,
            "completed_transition_count": self.completed_transition_count,
            "configuration": self.configuration,
            "divergence_count": self.divergence_count,
            "episode_id": self.episode_id,
            "invalid_quaternion_count": self.invalid_quaternion_count,
            "memory_inputs_4": self.memory_inputs_4.tolist(),
            "nonfinite_count": self.nonfinite_count,
            "predictions": self.predictions.tolist(),
            "quaternion_projection_count": self.quaternion_projection_count,
            "quaternion_unit_norm_drift_count": self.quaternion_unit_norm_drift_count,
            "reason_code": self.reason_code,
            "requested_steps": self.requested_steps,
            "start": self.start,
            "status": self.status,
        }


def _exception_reason(exc: Exception) -> str:
    reason = str(exc).split(":", 1)[0]
    if reason in {
        "quaternion_invalid",
        "quaternion_unit_norm_drift",
        "actuator_memory_control_invalid",
        "actuator_memory_disabled_channel_nonzero",
    }:
        return reason
    return "prediction_failed"


def _trace(
    episode: RolloutEpisodeV21,
    *,
    start: int,
    steps: int,
    status: str,
    reason: str | None,
    predictions: Sequence[np.ndarray],
    memory_inputs: Sequence[np.ndarray],
    nonfinite: int = 0,
    invalid: int = 0,
    drift: int = 0,
    divergence: int = 0,
) -> RolloutTraceV21:
    return RolloutTraceV21(
        episode_id=episode.episode_id,
        configuration=episode.configuration,
        start=start,
        requested_steps=steps,
        status=status,
        reason_code=reason,
        predictions=np.asarray(predictions, dtype=np.float64).reshape(-1, STATE_DIM_V21),
        memory_inputs_4=np.asarray(memory_inputs, dtype=np.float64).reshape(
            -1, ACTUATOR_MEMORY_DIM_V21
        ),
        attempted_transition_count=len(memory_inputs),
        completed_transition_count=len(predictions),
        nonfinite_count=nonfinite,
        invalid_quaternion_count=invalid,
        quaternion_unit_norm_drift_count=drift,
        divergence_count=divergence,
    )


def rollout_episode_v21(
    model: Any,
    episode: RolloutEpisodeV21,
    *,
    start: int,
    steps: int,
    policy: RolloutAnalysisPolicyV21,
    platform_score: Any | None = None,
) -> RolloutTraceV21:
    if not isinstance(episode, RolloutEpisodeV21) or not isinstance(
        policy, RolloutAnalysisPolicyV21
    ):
        _fail("evaluation_episode_required")
    if policy.policy_sha256 != OFFICIAL_ROLLOUT_POLICY_V21.policy_sha256:
        _fail("rollout_policy_not_official")
    if (
        isinstance(start, bool)
        or isinstance(steps, bool)
        or not isinstance(start, int)
        or not isinstance(steps, int)
        or start < 0
        or steps <= 0
        or start + steps > episode.transition_count
    ):
        _fail("rollout_window_invalid")
    current = np.array(episode.states_11[start], copy=True)
    proxy = ActuatorMemoryProxyV21.from_validated_state(
        episode.tau_s,
        episode.control_dt_s,
        episode.control_mask_4,
        episode.actuator_memory_4[start],
    )
    predictions: list[np.ndarray] = []
    memory_inputs: list[np.ndarray] = []
    for offset in range(steps):
        memory = proxy.current()
        memory_inputs.append(memory)
        control = episode.virtual_control_4[start + offset]
        try:
            increment = np.asarray(
                model.predict_increment(
                    current,
                    memory,
                    control,
                    platform_score=platform_score,
                ),
                dtype=np.float64,
            )
        except Exception as exc:
            reason = _exception_reason(exc)
            return _trace(
                episode,
                start=start,
                steps=steps,
                status="failed",
                reason=reason,
                predictions=predictions,
                memory_inputs=memory_inputs,
                invalid=int(reason == "quaternion_invalid"),
                drift=int(reason == "quaternion_unit_norm_drift"),
            )
        if increment.shape != (10,):
            return _trace(
                episode,
                start=start,
                steps=steps,
                status="failed",
                reason="prediction_shape_invalid",
                predictions=predictions,
                memory_inputs=memory_inputs,
            )
        if not np.isfinite(increment).all():
            return _trace(
                episode,
                start=start,
                steps=steps,
                status="failed",
                reason="prediction_nonfinite",
                predictions=predictions,
                memory_inputs=memory_inputs,
                nonfinite=1,
            )
        try:
            predicted = apply_increment_target_v21(current, increment)
        except ValueError as exc:
            reason = _exception_reason(exc)
            return _trace(
                episode,
                start=start,
                steps=steps,
                status="failed",
                reason=reason,
                predictions=predictions,
                memory_inputs=memory_inputs,
                invalid=int(reason == "quaternion_invalid"),
                drift=int(reason == "quaternion_unit_norm_drift"),
            )
        diverged = (
            abs(float(predicted[DEPTH_INDEX_V21])) > policy.depth_abs_max
            or np.any(
                np.abs(predicted[LINEAR_VELOCITY_SLICE_V21])
                > policy.linear_velocity_abs_max
            )
            or np.any(
                np.abs(predicted[ANGULAR_VELOCITY_SLICE_V21])
                > policy.angular_velocity_abs_max
            )
        )
        if diverged:
            return _trace(
                episode,
                start=start,
                steps=steps,
                status="failed",
                reason="rollout_diverged",
                predictions=predictions,
                memory_inputs=memory_inputs,
                divergence=1,
            )
        predictions.append(predicted)
        try:
            proxy.advance(control)
        except ValueError as exc:
            return _trace(
                episode,
                start=start,
                steps=steps,
                status="failed",
                reason=_exception_reason(exc),
                predictions=predictions,
                memory_inputs=memory_inputs,
            )
        current = predicted
    return _trace(
        episode,
        start=start,
        steps=steps,
        status="success",
        reason=None,
        predictions=predictions,
        memory_inputs=memory_inputs,
    )


@dataclass(frozen=True)
class HorizonMetricV21:
    label: str
    status: str
    reason_code: str | None
    values: Mapping[str, float | None]
    transition_count: int
    window_count: int
    nonfinite_count: int
    invalid_quaternion_count: int
    quaternion_unit_norm_drift_count: int
    divergence_count: int
    quaternion_projection_count: int = 0

    def __post_init__(self) -> None:
        if self.label not in REQUIRED_HORIZON_LABELS_V21:
            _fail("metric_horizon_invalid")
        if self.status not in {"success", "failed"} or (
            (self.status == "success") != (self.reason_code is None)
        ):
            _fail("metric_status_invalid")
        values = dict(self.values)
        if tuple(values) != OFFICIAL_ERROR_METRICS_V21:
            _fail("metric_schema_mismatch")
        if self.status == "success":
            if any(value is None or not math.isfinite(float(value)) for value in values.values()):
                _fail("metric_nonfinite")
            values = {key: float(value) for key, value in values.items()}
        elif any(value is not None for value in values.values()):
            _fail("metric_failure_values_invalid")
        for name in (
            "transition_count",
            "window_count",
            "nonfinite_count",
            "invalid_quaternion_count",
            "quaternion_unit_norm_drift_count",
            "divergence_count",
            "quaternion_projection_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _fail("metric_count_invalid", name)
        if self.quaternion_projection_count != 0:
            _fail("quaternion_projection_forbidden")
        object.__setattr__(self, "values", MappingProxyType(values))


@dataclass(frozen=True)
class EpisodeMetricArtifactV21:
    episode_id: str
    configuration: str
    policy_sha256: str
    horizons: Mapping[str, HorizonMetricV21]
    metric_schema_version: str = METRIC_SCHEMA_VERSION_V21

    def __post_init__(self) -> None:
        horizons = dict(self.horizons)
        if not isinstance(self.episode_id, str) or not self.episode_id:
            _fail("metric_episode_id_invalid")
        if not isinstance(self.configuration, str) or not self.configuration:
            _fail("metric_configuration_invalid")
        if not isinstance(self.policy_sha256, str) or not _SHA256_V21.fullmatch(
            self.policy_sha256
        ):
            _fail("metric_policy_hash_invalid")
        if (
            tuple(horizons) != REQUIRED_HORIZON_LABELS_V21
            or self.metric_schema_version != METRIC_SCHEMA_VERSION_V21
        ):
            _fail("metric_schema_mismatch")
        if any(entry.label != label for label, entry in horizons.items()):
            _fail("metric_horizon_invalid")
        object.__setattr__(self, "horizons", MappingProxyType(horizons))


def _metric_values(predictions: np.ndarray, truths: np.ndarray) -> dict[str, float]:
    depth = float(
        np.sqrt(np.mean(np.square(predictions[:, 0] - truths[:, 0])))
    )
    linear = float(
        np.sqrt(
            np.mean(
                np.square(
                    predictions[:, LINEAR_VELOCITY_SLICE_V21]
                    - truths[:, LINEAR_VELOCITY_SLICE_V21]
                )
            )
        )
    )
    angular = float(
        np.sqrt(
            np.mean(
                np.square(
                    predictions[:, ANGULAR_VELOCITY_SLICE_V21]
                    - truths[:, ANGULAR_VELOCITY_SLICE_V21]
                )
            )
        )
    )
    angles = np.asarray(
        so3_geodesic_radians_v21(
            truths[:, QUATERNION_SLICE_V21], predictions[:, QUATERNION_SLICE_V21]
        ),
        dtype=np.float64,
    )
    return {
        "depth_rmse": depth,
        "linear_velocity_rmse": linear,
        "angular_velocity_rmse": angular,
        "so3_geodesic_mean_radians": float(np.mean(angles)),
        "so3_geodesic_rmse_radians": float(np.sqrt(np.mean(np.square(angles)))),
        "so3_geodesic_max_radians": float(np.max(angles)),
    }


def _entry(
    label: str,
    traces: Sequence[RolloutTraceV21],
    predictions: Sequence[np.ndarray],
    truths: Sequence[np.ndarray],
) -> HorizonMetricV21:
    failed = next((trace for trace in traces if trace.status == "failed"), None)
    counts = {
        "nonfinite_count": sum(item.nonfinite_count for item in traces),
        "invalid_quaternion_count": sum(item.invalid_quaternion_count for item in traces),
        "quaternion_unit_norm_drift_count": sum(
            item.quaternion_unit_norm_drift_count for item in traces
        ),
        "divergence_count": sum(item.divergence_count for item in traces),
    }
    if failed is not None:
        return HorizonMetricV21(
            label=label,
            status="failed",
            reason_code=failed.reason_code,
            values={name: None for name in OFFICIAL_ERROR_METRICS_V21},
            transition_count=sum(item.attempted_transition_count for item in traces),
            window_count=len(traces),
            **counts,
        )
    prediction_array = np.asarray(predictions, dtype=np.float64).reshape(-1, STATE_DIM_V21)
    truth_array = np.asarray(truths, dtype=np.float64).reshape(-1, STATE_DIM_V21)
    return HorizonMetricV21(
        label=label,
        status="success",
        reason_code=None,
        values=_metric_values(prediction_array, truth_array),
        transition_count=int(prediction_array.shape[0]),
        window_count=len(traces),
        **counts,
    )


def evaluate_episode_metrics_v21(
    model: Any,
    episode: RolloutEpisodeV21,
    *,
    policy: RolloutAnalysisPolicyV21,
    platform_score: Any | None = None,
) -> EpisodeMetricArtifactV21:
    if episode.transition_count < 60:
        _fail("episode_too_short")
    horizons: dict[str, HorizonMetricV21] = {}
    one = tuple(
        rollout_episode_v21(
            model,
            episode,
            start=index,
            steps=1,
            policy=policy,
            platform_score=platform_score,
        )
        for index in range(episode.transition_count)
    )
    horizons["one_step"] = _entry(
        "one_step",
        one,
        [trace.predictions[-1] for trace in one if trace.status == "success"],
        [
            episode.targets_11[index]
            for index, trace in enumerate(one)
            if trace.status == "success"
        ],
    )
    for length in (5, 20, 60):
        traces = tuple(
            rollout_episode_v21(
                model,
                episode,
                start=start,
                steps=length,
                policy=policy,
                platform_score=platform_score,
            )
            for start in range(episode.transition_count - length + 1)
        )
        horizons[str(length)] = _entry(
            str(length),
            traces,
            [trace.predictions[-1] for trace in traces if trace.status == "success"],
            [
                episode.targets_11[start + length - 1]
                for start, trace in enumerate(traces)
                if trace.status == "success"
            ],
        )
    full = rollout_episode_v21(
        model,
        episode,
        start=0,
        steps=episode.transition_count,
        policy=policy,
        platform_score=platform_score,
    )
    horizons["full"] = _entry(
        "full",
        (full,),
        list(full.predictions),
        list(episode.targets_11[: full.completed_transition_count]),
    )
    return EpisodeMetricArtifactV21(
        episode_id=episode.episode_id,
        configuration=episode.configuration,
        policy_sha256=policy.policy_sha256,
        horizons=horizons,
    )


def aggregate_configuration_metrics_v21(
    artifacts: Sequence[EpisodeMetricArtifactV21],
    *,
    expected_configurations: Sequence[str],
    expected_horizons: Sequence[str],
) -> dict[str, Any]:
    values = tuple(artifacts)
    configurations = tuple(expected_configurations)
    horizons = tuple(expected_horizons)
    if horizons != REQUIRED_HORIZON_LABELS_V21:
        _fail("aggregate_horizon_set_mismatch")
    if len(configurations) != len(set(configurations)):
        _fail("aggregate_configuration_set_mismatch")
    if not values or set(item.configuration for item in values) != set(configurations):
        _fail("aggregate_configuration_set_mismatch")
    if len({item.policy_sha256 for item in values}) != 1:
        _fail("metric_policy_hash_mismatch")
    grouped = {
        configuration: tuple(
            item for item in values if item.configuration == configuration
        )
        for configuration in configurations
    }
    per_configuration: dict[str, dict[str, Any]] = {}
    for configuration, items in grouped.items():
        per_configuration[configuration] = {}
        for horizon in horizons:
            entries = tuple(item.horizons[horizon] for item in items)
            failed = tuple(entry for entry in entries if entry.status == "failed")
            total_count = sum(entry.transition_count for entry in entries)
            metric_values: dict[str, float | None]
            if failed or total_count == 0:
                metric_values = {name: None for name in OFFICIAL_ERROR_METRICS_V21}
            else:
                metric_values = {
                    name: float(
                        sum(float(entry.values[name]) * entry.transition_count for entry in entries)
                        / total_count
                    )
                    for name in OFFICIAL_ERROR_METRICS_V21
                }
            per_configuration[configuration][horizon] = {
                **metric_values,
                "episode_count": len(items),
                "failure_count": len(failed),
                "transition_count": total_count,
            }
    macro: dict[str, dict[str, float | None]] = {}
    worst: dict[str, dict[str, float | None]] = {}
    row_weighted: dict[str, dict[str, float | None]] = {}
    for horizon in horizons:
        macro[horizon] = {}
        worst[horizon] = {}
        row_weighted[horizon] = {}
        for name in OFFICIAL_ERROR_METRICS_V21:
            entries = [
                per_configuration[configuration][horizon][name]
                for configuration in configurations
            ]
            if any(item is None for item in entries):
                macro[horizon][name] = None
                worst[horizon][name] = None
            else:
                numeric = [float(item) for item in entries]
                macro[horizon][name] = float(np.mean(numeric))
                worst[horizon][name] = float(np.max(numeric))
            episode_entries = tuple(item.horizons[horizon] for item in values)
            row_count = sum(item.transition_count for item in episode_entries)
            if (
                row_count == 0
                or any(item.status == "failed" for item in episode_entries)
            ):
                row_weighted[horizon][name] = None
            else:
                row_weighted[horizon][name] = float(
                    sum(
                        float(item.values[name]) * item.transition_count
                        for item in episode_entries
                    )
                    / row_count
                )
    return {
        "equal_configuration_macro": macro,
        "metric_schema_version": METRIC_SCHEMA_VERSION_V21,
        "official_metric_names": list(OFFICIAL_ERROR_METRICS_V21),
        "per_configuration": per_configuration,
        "policy_sha256": values[0].policy_sha256,
        "row_weighted_diagnostic": row_weighted,
        "worst_configuration": worst,
    }
