"""Episode-safe rollout and quaternion-correct Phase 8 prediction metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any

import numpy as np

from koopman.evidence_v2 import canonical_sha256


STATE_DIM_V2 = 11
CONTROL_DIM_V2 = 4
DEPTH_INDEX_V2 = 0
QUATERNION_SLICE_V2 = slice(1, 5)
LINEAR_VELOCITY_SLICE_V2 = slice(5, 8)
ANGULAR_VELOCITY_SLICE_V2 = slice(8, 11)
METRIC_SCHEMA_VERSION_V2 = "phase8-episode-metrics-v1"
ROLLOUT_POLICY_VERSION_V2 = "phase8-rollout-analysis-policy-v1"
REQUIRED_HORIZONS_V2 = (5, 20, 60, "full")
REQUIRED_HORIZON_LABELS_V2 = ("one_step", "5", "20", "60", "full")
OFFICIAL_ERROR_METRICS_V2 = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)
_EPISODE_FIELDS = frozenset(
    {"configuration", "controls", "episode_id", "states", "targets"}
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _positive_finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("rollout_policy_invalid", name)
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        _fail("rollout_policy_invalid", name)
    return number


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _readonly_matrix(value: Any, *, width: int, name: str) -> np.ndarray:
    array = np.array(value, dtype=np.float64, copy=True)
    if array.ndim != 2 or array.shape[1] != width or array.shape[0] == 0:
        _fail("evaluation_shape_invalid", name)
    if not np.isfinite(array).all():
        _fail("evaluation_nonfinite", name)
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class RolloutAnalysisPolicyV2:
    horizons: tuple[int | str, ...]
    quaternion_epsilon: float
    quaternion_projection_limit: float
    depth_abs_max: float
    linear_velocity_abs_max: float
    angular_velocity_abs_max: float
    version: str = ROLLOUT_POLICY_VERSION_V2
    policy_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        horizons = tuple(self.horizons)
        if horizons != REQUIRED_HORIZONS_V2:
            _fail("rollout_policy_invalid", "horizons")
        if self.version != ROLLOUT_POLICY_VERSION_V2:
            _fail("rollout_policy_invalid", "version")
        for name in (
            "quaternion_epsilon",
            "quaternion_projection_limit",
            "depth_abs_max",
            "linear_velocity_abs_max",
            "angular_velocity_abs_max",
        ):
            object.__setattr__(self, name, _positive_finite(getattr(self, name), name))
        object.__setattr__(self, "horizons", horizons)
        object.__setattr__(self, "policy_sha256", canonical_sha256(self.payload()))

    def payload(self) -> dict[str, Any]:
        return {
            "angular_velocity_abs_max": self.angular_velocity_abs_max,
            "depth_abs_max": self.depth_abs_max,
            "horizons": list(self.horizons),
            "linear_velocity_abs_max": self.linear_velocity_abs_max,
            "quaternion_epsilon": self.quaternion_epsilon,
            "quaternion_projection_limit": self.quaternion_projection_limit,
            "version": self.version,
        }


@dataclass(frozen=True)
class EpisodeTrajectoryV2:
    episode_id: str
    configuration: str
    states: np.ndarray
    controls: np.ndarray
    targets: np.ndarray

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not self.episode_id:
            _fail("evaluation_episode_id_invalid")
        if not isinstance(self.configuration, str) or not self.configuration:
            _fail("evaluation_configuration_invalid")
        states = _readonly_matrix(self.states, width=STATE_DIM_V2, name="states")
        controls = _readonly_matrix(self.controls, width=CONTROL_DIM_V2, name="controls")
        targets = _readonly_matrix(self.targets, width=STATE_DIM_V2, name="targets")
        if states.shape[0] != controls.shape[0] or states.shape != targets.shape:
            _fail("evaluation_shape_invalid", "row_count")
        for name, array in (("states", states), ("targets", targets)):
            if np.any(np.linalg.norm(array[:, QUATERNION_SLICE_V2], axis=1) <= 0.0):
                _fail("quaternion_invalid", name)
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "controls", controls)
        object.__setattr__(self, "targets", targets)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EpisodeTrajectoryV2":
        if not isinstance(value, Mapping) or set(value) != _EPISODE_FIELDS:
            _fail("evaluation_field_set_mismatch")
        return cls(
            episode_id=value["episode_id"],
            configuration=value["configuration"],
            states=value["states"],
            controls=value["controls"],
            targets=value["targets"],
        )

    @property
    def transition_count(self) -> int:
        return int(self.states.shape[0])


def _quaternion_arrays(
    truth: Any, prediction: Any
) -> tuple[np.ndarray, np.ndarray, bool]:
    truth_array = np.asarray(truth, dtype=np.float64)
    prediction_array = np.asarray(prediction, dtype=np.float64)
    single = truth_array.ndim == 1
    if single:
        truth_array = truth_array.reshape(1, -1)
    if prediction_array.ndim == 1:
        prediction_array = prediction_array.reshape(1, -1)
    if (
        truth_array.ndim != 2
        or prediction_array.ndim != 2
        or truth_array.shape != prediction_array.shape
        or truth_array.shape[1] != 4
        or truth_array.shape[0] == 0
    ):
        _fail("quaternion_shape_invalid")
    if not np.isfinite(truth_array).all() or not np.isfinite(prediction_array).all():
        _fail("quaternion_nonfinite")
    return truth_array, prediction_array, single


def _project_prediction_quaternions(
    values: np.ndarray,
    *,
    quaternion_epsilon: float,
    projection_limit: float,
) -> tuple[np.ndarray, np.ndarray]:
    norms = np.linalg.norm(values, axis=1)
    if np.any(norms < quaternion_epsilon):
        _fail("quaternion_invalid")
    corrections = np.abs(norms - 1.0)
    if np.any(corrections > projection_limit):
        _fail("quaternion_projection_limit")
    return values / norms[:, None], corrections


def so3_geodesic_radians(
    truth: Any,
    prediction: Any,
    *,
    quaternion_epsilon: float,
    projection_limit: float,
) -> float | np.ndarray:
    """Return normalized sign-invariant SO(3) geodesic error in radians."""

    epsilon = _positive_finite(quaternion_epsilon, "quaternion_epsilon")
    limit = _positive_finite(projection_limit, "projection_limit")
    truth_array, prediction_array, single = _quaternion_arrays(truth, prediction)
    truth_norms = np.linalg.norm(truth_array, axis=1)
    if np.any(truth_norms < epsilon):
        _fail("quaternion_invalid")
    normalized_truth = truth_array / truth_norms[:, None]
    normalized_prediction, _ = _project_prediction_quaternions(
        prediction_array,
        quaternion_epsilon=epsilon,
        projection_limit=limit,
    )
    dots = np.sum(normalized_truth * normalized_prediction, axis=1)
    angles = 2.0 * np.arccos(np.clip(np.abs(dots), 0.0, 1.0))
    return float(angles[0]) if single else angles


@dataclass(frozen=True)
class RolloutTraceV2:
    episode_id: str
    configuration: str
    start: int
    requested_steps: int
    status: str
    reason_code: str | None
    predictions: np.ndarray
    attempted_transition_count: int
    completed_transition_count: int
    nonfinite_count: int
    invalid_quaternion_count: int
    projection_failure_count: int
    divergence_count: int
    projection_count: int
    projection_correction_max: float

    def __post_init__(self) -> None:
        predictions = np.array(self.predictions, dtype=np.float64, copy=True)
        if predictions.shape != (self.completed_transition_count, STATE_DIM_V2):
            _fail("rollout_trace_invalid", "predictions")
        if predictions.size and not np.isfinite(predictions).all():
            _fail("rollout_trace_invalid", "nonfinite_predictions")
        if self.status not in {"success", "failed"}:
            _fail("rollout_trace_invalid", "status")
        if (self.status == "success") != (self.reason_code is None):
            _fail("rollout_trace_invalid", "reason_code")
        predictions.setflags(write=False)
        object.__setattr__(self, "predictions", predictions)


def _failed_trace(
    *,
    episode: EpisodeTrajectoryV2,
    start: int,
    steps: int,
    reason: str,
    predictions: list[np.ndarray],
    attempted: int,
    nonfinite_count: int,
    invalid_quaternion_count: int,
    projection_failure_count: int,
    divergence_count: int,
    projection_count: int,
    projection_correction_max: float,
) -> RolloutTraceV2:
    return RolloutTraceV2(
        episode_id=episode.episode_id,
        configuration=episode.configuration,
        start=start,
        requested_steps=steps,
        status="failed",
        reason_code=reason,
        predictions=np.asarray(predictions, dtype=np.float64).reshape(-1, STATE_DIM_V2),
        attempted_transition_count=attempted,
        completed_transition_count=len(predictions),
        nonfinite_count=nonfinite_count,
        invalid_quaternion_count=invalid_quaternion_count,
        projection_failure_count=projection_failure_count,
        divergence_count=divergence_count,
        projection_count=projection_count,
        projection_correction_max=projection_correction_max,
    )


def rollout_episode_v2(
    model: Any,
    episode: EpisodeTrajectoryV2,
    *,
    start: int,
    steps: int,
    policy: RolloutAnalysisPolicyV2,
) -> RolloutTraceV2:
    if not isinstance(episode, EpisodeTrajectoryV2):
        _fail("evaluation_episode_required")
    if not isinstance(policy, RolloutAnalysisPolicyV2):
        _fail("rollout_policy_required")
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
    current = np.array(episode.states[start], copy=True)
    predictions: list[np.ndarray] = []
    attempted = 0
    nonfinite_count = 0
    invalid_quaternion_count = 0
    projection_failure_count = 0
    divergence_count = 0
    projection_count = 0
    projection_correction_max = 0.0
    for offset in range(steps):
        attempted += 1
        try:
            predicted = np.asarray(
                model.predict_next(current, episode.controls[start + offset]),
                dtype=np.float64,
            )
        except Exception:
            return _failed_trace(
                episode=episode,
                start=start,
                steps=steps,
                reason="prediction_failed",
                predictions=predictions,
                attempted=attempted,
                nonfinite_count=nonfinite_count,
                invalid_quaternion_count=invalid_quaternion_count,
                projection_failure_count=projection_failure_count,
                divergence_count=divergence_count,
                projection_count=projection_count,
                projection_correction_max=projection_correction_max,
            )
        if predicted.shape != (STATE_DIM_V2,):
            return _failed_trace(
                episode=episode,
                start=start,
                steps=steps,
                reason="prediction_shape_invalid",
                predictions=predictions,
                attempted=attempted,
                nonfinite_count=nonfinite_count,
                invalid_quaternion_count=invalid_quaternion_count,
                projection_failure_count=projection_failure_count,
                divergence_count=divergence_count,
                projection_count=projection_count,
                projection_correction_max=projection_correction_max,
            )
        if not np.isfinite(predicted).all():
            nonfinite_count += 1
            return _failed_trace(
                episode=episode,
                start=start,
                steps=steps,
                reason="prediction_nonfinite",
                predictions=predictions,
                attempted=attempted,
                nonfinite_count=nonfinite_count,
                invalid_quaternion_count=invalid_quaternion_count,
                projection_failure_count=projection_failure_count,
                divergence_count=divergence_count,
                projection_count=projection_count,
                projection_correction_max=projection_correction_max,
            )
        quaternion = predicted[QUATERNION_SLICE_V2].reshape(1, 4)
        norm = float(np.linalg.norm(quaternion))
        if norm < policy.quaternion_epsilon:
            invalid_quaternion_count += 1
            return _failed_trace(
                episode=episode,
                start=start,
                steps=steps,
                reason="quaternion_invalid",
                predictions=predictions,
                attempted=attempted,
                nonfinite_count=nonfinite_count,
                invalid_quaternion_count=invalid_quaternion_count,
                projection_failure_count=projection_failure_count,
                divergence_count=divergence_count,
                projection_count=projection_count,
                projection_correction_max=projection_correction_max,
            )
        correction = abs(norm - 1.0)
        if correction > policy.quaternion_projection_limit:
            projection_failure_count += 1
            return _failed_trace(
                episode=episode,
                start=start,
                steps=steps,
                reason="quaternion_projection_limit",
                predictions=predictions,
                attempted=attempted,
                nonfinite_count=nonfinite_count,
                invalid_quaternion_count=invalid_quaternion_count,
                projection_failure_count=projection_failure_count,
                divergence_count=divergence_count,
                projection_count=projection_count,
                projection_correction_max=max(projection_correction_max, correction),
            )
        predicted = predicted.copy()
        predicted[QUATERNION_SLICE_V2] = quaternion[0] / norm
        if correction > 0.0:
            projection_count += 1
            projection_correction_max = max(projection_correction_max, correction)
        diverged = (
            abs(float(predicted[DEPTH_INDEX_V2])) > policy.depth_abs_max
            or np.any(
                np.abs(predicted[LINEAR_VELOCITY_SLICE_V2])
                > policy.linear_velocity_abs_max
            )
            or np.any(
                np.abs(predicted[ANGULAR_VELOCITY_SLICE_V2])
                > policy.angular_velocity_abs_max
            )
        )
        if diverged:
            divergence_count += 1
            return _failed_trace(
                episode=episode,
                start=start,
                steps=steps,
                reason="rollout_diverged",
                predictions=predictions,
                attempted=attempted,
                nonfinite_count=nonfinite_count,
                invalid_quaternion_count=invalid_quaternion_count,
                projection_failure_count=projection_failure_count,
                divergence_count=divergence_count,
                projection_count=projection_count,
                projection_correction_max=projection_correction_max,
            )
        predictions.append(predicted)
        current = predicted
    return RolloutTraceV2(
        episode_id=episode.episode_id,
        configuration=episode.configuration,
        start=start,
        requested_steps=steps,
        status="success",
        reason_code=None,
        predictions=np.asarray(predictions, dtype=np.float64),
        attempted_transition_count=attempted,
        completed_transition_count=len(predictions),
        nonfinite_count=nonfinite_count,
        invalid_quaternion_count=invalid_quaternion_count,
        projection_failure_count=projection_failure_count,
        divergence_count=divergence_count,
        projection_count=projection_count,
        projection_correction_max=projection_correction_max,
    )


def validate_official_metric_names_v2(names: Sequence[str]) -> tuple[str, ...]:
    values = tuple(names)
    if any(
        token in str(name).lower()
        for name in values
        for token in ("attitude", "quaternion", "orientation", "component")
    ):
        _fail("metric_alias_forbidden")
    if values != OFFICIAL_ERROR_METRICS_V2:
        _fail("metric_schema_mismatch")
    return values


@dataclass(frozen=True)
class HorizonMetricV2:
    label: str
    status: str
    reason_code: str | None
    values: Mapping[str, float | None]
    transition_count: int
    window_count: int
    nonfinite_count: int
    invalid_quaternion_count: int
    projection_failure_count: int
    divergence_count: int
    projection_count: int
    projection_correction_max: float

    def __post_init__(self) -> None:
        if self.label not in REQUIRED_HORIZON_LABELS_V2:
            _fail("metric_horizon_invalid", self.label)
        if self.status not in {"success", "failed"}:
            _fail("metric_status_invalid")
        if (self.status == "success") != (self.reason_code is None):
            _fail("metric_reason_invalid")
        values = dict(self.values)
        validate_official_metric_names_v2(tuple(values))
        if self.status == "success":
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in values.values()
            ):
                _fail("metric_nonfinite")
            values = {name: float(value) for name, value in values.items()}
        elif any(value is not None for value in values.values()):
            _fail("metric_failure_values_invalid")
        for name in (
            "transition_count",
            "window_count",
            "nonfinite_count",
            "invalid_quaternion_count",
            "projection_failure_count",
            "divergence_count",
            "projection_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _fail("metric_count_invalid", name)
        if not math.isfinite(self.projection_correction_max) or self.projection_correction_max < 0.0:
            _fail("metric_projection_invalid")
        object.__setattr__(self, "values", MappingProxyType(values))


@dataclass(frozen=True)
class EpisodeMetricArtifactV2:
    episode_id: str
    configuration: str
    policy_sha256: str
    horizons: Mapping[str, HorizonMetricV2]
    metric_schema_version: str = METRIC_SCHEMA_VERSION_V2

    def __post_init__(self) -> None:
        if self.metric_schema_version != METRIC_SCHEMA_VERSION_V2:
            _fail("metric_schema_mismatch")
        if not _is_sha256(self.policy_sha256):
            _fail("metric_policy_hash_invalid")
        horizons = dict(self.horizons)
        if tuple(horizons) != REQUIRED_HORIZON_LABELS_V2:
            _fail("aggregate_horizon_set_mismatch")
        if any(entry.label != label for label, entry in horizons.items()):
            _fail("metric_horizon_invalid")
        object.__setattr__(self, "horizons", MappingProxyType(horizons))


def _metric_values(predictions: np.ndarray, truths: np.ndarray, policy: RolloutAnalysisPolicyV2) -> dict[str, float]:
    if predictions.shape != truths.shape or predictions.ndim != 2 or predictions.shape[0] == 0:
        _fail("metric_shape_invalid")
    depth_rmse = float(
        np.sqrt(np.mean(np.square(predictions[:, DEPTH_INDEX_V2] - truths[:, DEPTH_INDEX_V2])))
    )
    linear_rmse = float(
        np.sqrt(
            np.mean(
                np.square(
                    predictions[:, LINEAR_VELOCITY_SLICE_V2]
                    - truths[:, LINEAR_VELOCITY_SLICE_V2]
                )
            )
        )
    )
    angular_rmse = float(
        np.sqrt(
            np.mean(
                np.square(
                    predictions[:, ANGULAR_VELOCITY_SLICE_V2]
                    - truths[:, ANGULAR_VELOCITY_SLICE_V2]
                )
            )
        )
    )
    angles = np.asarray(
        so3_geodesic_radians(
            truths[:, QUATERNION_SLICE_V2],
            predictions[:, QUATERNION_SLICE_V2],
            quaternion_epsilon=policy.quaternion_epsilon,
            projection_limit=policy.quaternion_projection_limit,
        ),
        dtype=np.float64,
    )
    return {
        "depth_rmse": depth_rmse,
        "linear_velocity_rmse": linear_rmse,
        "angular_velocity_rmse": angular_rmse,
        "so3_geodesic_mean_radians": float(np.mean(angles)),
        "so3_geodesic_rmse_radians": float(np.sqrt(np.mean(np.square(angles)))),
        "so3_geodesic_max_radians": float(np.max(angles)),
    }


def _entry_from_traces(
    *,
    label: str,
    traces: Sequence[RolloutTraceV2],
    predictions: Sequence[np.ndarray],
    truths: Sequence[np.ndarray],
    policy: RolloutAnalysisPolicyV2,
) -> HorizonMetricV2:
    failed = next((trace for trace in traces if trace.status == "failed"), None)
    counts = {
        "nonfinite_count": sum(trace.nonfinite_count for trace in traces),
        "invalid_quaternion_count": sum(
            trace.invalid_quaternion_count for trace in traces
        ),
        "projection_failure_count": sum(
            trace.projection_failure_count for trace in traces
        ),
        "divergence_count": sum(trace.divergence_count for trace in traces),
        "projection_count": sum(trace.projection_count for trace in traces),
    }
    projection_max = max(
        (trace.projection_correction_max for trace in traces), default=0.0
    )
    if failed is not None:
        return HorizonMetricV2(
            label=label,
            status="failed",
            reason_code=failed.reason_code,
            values={name: None for name in OFFICIAL_ERROR_METRICS_V2},
            transition_count=sum(trace.attempted_transition_count for trace in traces),
            window_count=len(traces),
            projection_correction_max=projection_max,
            **counts,
        )
    prediction_array = np.asarray(predictions, dtype=np.float64).reshape(-1, STATE_DIM_V2)
    truth_array = np.asarray(truths, dtype=np.float64).reshape(-1, STATE_DIM_V2)
    return HorizonMetricV2(
        label=label,
        status="success",
        reason_code=None,
        values=_metric_values(prediction_array, truth_array, policy),
        transition_count=int(prediction_array.shape[0]),
        window_count=len(traces),
        projection_correction_max=projection_max,
        **counts,
    )


def evaluate_episode_metrics_v2(
    model: Any,
    episode: EpisodeTrajectoryV2,
    *,
    policy: RolloutAnalysisPolicyV2,
) -> EpisodeMetricArtifactV2:
    if episode.transition_count < 60:
        _fail("episode_too_short", "horizon=60")
    horizons: dict[str, HorizonMetricV2] = {}

    one_step_traces = tuple(
        rollout_episode_v2(model, episode, start=index, steps=1, policy=policy)
        for index in range(episode.transition_count)
    )
    one_predictions = [trace.predictions[-1] for trace in one_step_traces if trace.status == "success"]
    one_truths = [
        episode.targets[index]
        for index, trace in enumerate(one_step_traces)
        if trace.status == "success"
    ]
    horizons["one_step"] = _entry_from_traces(
        label="one_step",
        traces=one_step_traces,
        predictions=one_predictions,
        truths=one_truths,
        policy=policy,
    )

    for horizon in (5, 20, 60):
        traces = tuple(
            rollout_episode_v2(model, episode, start=start, steps=horizon, policy=policy)
            for start in range(episode.transition_count - horizon + 1)
        )
        predictions = [trace.predictions[-1] for trace in traces if trace.status == "success"]
        truths = [
            episode.targets[start + horizon - 1]
            for start, trace in enumerate(traces)
            if trace.status == "success"
        ]
        horizons[str(horizon)] = _entry_from_traces(
            label=str(horizon),
            traces=traces,
            predictions=predictions,
            truths=truths,
            policy=policy,
        )

    full_trace = rollout_episode_v2(
        model,
        episode,
        start=0,
        steps=episode.transition_count,
        policy=policy,
    )
    horizons["full"] = _entry_from_traces(
        label="full",
        traces=(full_trace,),
        predictions=list(full_trace.predictions),
        truths=list(episode.targets[: full_trace.completed_transition_count]),
        policy=policy,
    )
    return EpisodeMetricArtifactV2(
        episode_id=episode.episode_id,
        configuration=episode.configuration,
        policy_sha256=policy.policy_sha256,
        horizons=horizons,
    )


def evaluate_model_episodes_v2(
    model: Any,
    episodes: Sequence[EpisodeTrajectoryV2],
    *,
    policy: RolloutAnalysisPolicyV2,
) -> tuple[EpisodeMetricArtifactV2, ...]:
    values = tuple(episodes)
    if not values:
        _fail("evaluation_episode_set_empty")
    return tuple(
        evaluate_episode_metrics_v2(model, episode, policy=policy)
        for episode in values
    )


def aggregate_configuration_metrics_v2(
    artifacts: Sequence[EpisodeMetricArtifactV2],
    *,
    expected_configurations: Sequence[str],
    expected_horizons: Sequence[str],
) -> dict[str, Any]:
    values = tuple(artifacts)
    configurations = tuple(expected_configurations)
    horizons = tuple(expected_horizons)
    if horizons != REQUIRED_HORIZON_LABELS_V2:
        _fail("aggregate_horizon_set_mismatch")
    if not values or set(item.configuration for item in values) != set(configurations):
        _fail("aggregate_configuration_set_mismatch")
    if len(configurations) != len(set(configurations)):
        _fail("aggregate_configuration_set_mismatch")
    if any(tuple(item.horizons) != horizons for item in values):
        _fail("aggregate_horizon_set_mismatch")
    if len({item.policy_sha256 for item in values}) != 1:
        _fail("metric_policy_hash_mismatch")
    grouped = {
        configuration: tuple(
            item for item in values if item.configuration == configuration
        )
        for configuration in configurations
    }
    per_configuration: dict[str, dict[str, Any]] = {}
    macro: dict[str, Any] = {}
    worst: dict[str, Any] = {}
    row_weighted: dict[str, Any] = {}
    for configuration, items in grouped.items():
        per_configuration[configuration] = {}
        for horizon in horizons:
            entries = tuple(item.horizons[horizon] for item in items)
            failed = tuple(entry for entry in entries if entry.status == "failed")
            total_count = sum(entry.transition_count for entry in entries)
            if failed:
                metric_values: dict[str, float | None] = {
                    name: None for name in OFFICIAL_ERROR_METRICS_V2
                }
            else:
                metric_values = {
                    name: float(
                        sum(entry.values[name] * entry.transition_count for entry in entries)
                        / total_count
                    )
                    for name in OFFICIAL_ERROR_METRICS_V2
                }
            per_configuration[configuration][horizon] = {
                **metric_values,
                "episode_count": len(items),
                "failure_count": len(failed),
                "transition_count": total_count,
            }
    for horizon in horizons:
        macro[horizon] = {}
        worst[horizon] = {}
        row_weighted[horizon] = {}
        for name in OFFICIAL_ERROR_METRICS_V2:
            configuration_values = [
                per_configuration[configuration][horizon][name]
                for configuration in configurations
            ]
            if any(value is None for value in configuration_values):
                macro[horizon][name] = None
                worst[horizon][name] = None
                row_weighted[horizon][name] = None
                continue
            numeric = [float(value) for value in configuration_values]
            macro[horizon][name] = float(np.mean(numeric))
            worst[horizon][name] = float(np.max(numeric))
            counts = [
                per_configuration[configuration][horizon]["transition_count"]
                for configuration in configurations
            ]
            row_weighted[horizon][name] = float(
                sum(value * count for value, count in zip(numeric, counts, strict=True))
                / sum(counts)
            )
    return {
        "equal_configuration_macro": macro,
        "metric_schema_version": METRIC_SCHEMA_VERSION_V2,
        "official_metric_names": list(OFFICIAL_ERROR_METRICS_V2),
        "per_configuration": per_configuration,
        "policy_sha256": values[0].policy_sha256,
        "row_weighted_diagnostic": row_weighted,
        "worst_configuration": worst,
    }
