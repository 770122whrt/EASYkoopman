"""Behavior contracts for episode-safe Phase 8 rollout and SO(3) metrics."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from koopman.metrics_v2 import (
    ANGULAR_VELOCITY_SLICE_V2,
    DEPTH_INDEX_V2,
    LINEAR_VELOCITY_SLICE_V2,
    METRIC_SCHEMA_VERSION_V2,
    OFFICIAL_ERROR_METRICS_V2,
    QUATERNION_SLICE_V2,
    EpisodeMetricArtifactV2,
    EpisodeTrajectoryV2,
    HorizonMetricV2,
    RolloutAnalysisPolicyV2,
    aggregate_configuration_metrics_v2,
    evaluate_episode_metrics_v2,
    evaluate_model_episodes_v2,
    rollout_episode_v2,
    so3_geodesic_radians,
    validate_official_metric_names_v2,
)


def _policy(**overrides) -> RolloutAnalysisPolicyV2:
    values = {
        "horizons": (5, 20, 60, "full"),
        "quaternion_epsilon": 1.0e-10,
        "quaternion_projection_limit": 0.25,
        "depth_abs_max": 100.0,
        "linear_velocity_abs_max": 100.0,
        "angular_velocity_abs_max": 100.0,
    }
    values.update(overrides)
    return RolloutAnalysisPolicyV2(**values)


class AdditiveDepthModel:
    def __init__(self) -> None:
        self.inputs: list[np.ndarray] = []

    def predict_next(self, state, control):
        current = np.asarray(state, dtype=float)
        self.inputs.append(current.copy())
        result = current.copy()
        result[0] += float(np.asarray(control)[0])
        return result


class FailingQuaternionModel:
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.calls = 0

    def predict_next(self, state, control):
        self.calls += 1
        result = np.asarray(state, dtype=float).copy()
        if self.calls == 2:
            if self.failure == "zero":
                result[1:5] = 0.0
            elif self.failure == "nonfinite":
                result[0] = np.nan
            elif self.failure == "projection":
                result[1:5] *= 2.0
            elif self.failure == "divergence":
                result[0] = 101.0
        return result


def _episode(
    episode_id: str,
    configuration: str,
    *,
    length: int = 64,
    initial_depth: float = 0.0,
    increment: float = 0.1,
) -> EpisodeTrajectoryV2:
    states = np.zeros((length, 11), dtype=float)
    states[:, 1] = 1.0
    states[:, 0] = initial_depth + increment * np.arange(length)
    controls = np.zeros((length, 4), dtype=float)
    controls[:, 0] = increment
    targets = states.copy()
    targets[:, 0] += increment
    return EpisodeTrajectoryV2(
        episode_id=episode_id,
        configuration=configuration,
        states=states,
        controls=controls,
        targets=targets,
    )


def test_state_group_slices_match_frozen_state11_contract() -> None:
    assert DEPTH_INDEX_V2 == 0
    assert QUATERNION_SLICE_V2 == slice(1, 5)
    assert LINEAR_VELOCITY_SLICE_V2 == slice(5, 8)
    assert ANGULAR_VELOCITY_SLICE_V2 == slice(8, 11)


@pytest.mark.parametrize(
    ("truth", "prediction", "expected"),
    [
        ([1.0, 0.0, 0.0, 0.0], [-1.0, 0.0, 0.0, 0.0], 0.0),
        ([1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0], 0.0),
        (
            [1.0, 0.0, 0.0, 0.0],
            [np.sqrt(0.5), 0.0, 0.0, np.sqrt(0.5)],
            np.pi / 2.0,
        ),
        ([1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], np.pi),
    ],
)
def test_so3_geodesic_is_sign_invariant_and_returns_radians(truth, prediction, expected) -> None:
    actual = so3_geodesic_radians(
        truth,
        prediction,
        quaternion_epsilon=1.0e-10,
        projection_limit=0.25,
    )
    assert actual == pytest.approx(expected, abs=1.0e-12)


def test_so3_geodesic_supports_batch_projection_and_dot_clamp() -> None:
    truth = np.asarray([[1.0, 0.0, 0.0, 0.0], [1.0, 1.0e-16, 0.0, 0.0]])
    prediction = np.asarray([[1.05, 0.0, 0.0, 0.0], [1.0, -1.0e-16, 0.0, 0.0]])
    result = so3_geodesic_radians(
        truth,
        prediction,
        quaternion_epsilon=1.0e-10,
        projection_limit=0.1,
    )
    assert result.shape == (2,)
    assert np.all(result >= 0.0)
    assert np.all(result <= np.pi)
    assert result[0] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("prediction", "limit", "reason"),
    [
        ([0.0, 0.0, 0.0, 0.0], 1.0, "quaternion_invalid"),
        ([np.nan, 0.0, 0.0, 0.0], 1.0, "quaternion_nonfinite"),
        ([2.0, 0.0, 0.0, 0.0], 0.5, "quaternion_projection_limit"),
    ],
)
def test_so3_geodesic_rejects_invalid_or_excessive_projection(prediction, limit, reason) -> None:
    with pytest.raises(ValueError, match=reason):
        so3_geodesic_radians(
            [1.0, 0.0, 0.0, 0.0],
            prediction,
            quaternion_epsilon=1.0e-10,
            projection_limit=limit,
        )


def test_full_rollout_uses_one_true_initial_state_and_recursive_predictions() -> None:
    episode = _episode("episode-a", "base", length=64)
    model = AdditiveDepthModel()
    trace = rollout_episode_v2(
        model,
        episode,
        start=0,
        steps=64,
        policy=_policy(),
    )

    assert trace.status == "success"
    assert trace.reason_code is None
    assert np.allclose(trace.predictions, episode.targets)
    assert len(model.inputs) == 64
    assert np.array_equal(model.inputs[0], episode.states[0])
    assert all(
        np.array_equal(model.inputs[index], trace.predictions[index - 1])
        for index in range(1, 64)
    )
    assert all(
        not np.array_equal(model.inputs[index], episode.states[index])
        or np.array_equal(episode.states[index], trace.predictions[index - 1])
        for index in range(1, 64)
    )


def test_one_step_uses_each_row_and_two_episodes_never_cross_boundaries() -> None:
    first = _episode("episode-a", "base", initial_depth=0.0)
    second = _episode("episode-b", "uuv6", initial_depth=50.0)
    model = AdditiveDepthModel()
    artifacts = evaluate_model_episodes_v2(model, (first, second), policy=_policy())

    assert len(artifacts) == 2
    assert all(artifact.horizons["one_step"].transition_count == 64 for artifact in artifacts)
    assert all(artifact.horizons["full"].status == "success" for artifact in artifacts)
    full_initials = [
        input_state[0]
        for input_state in model.inputs
        if input_state[0] in {0.0, 50.0}
    ]
    assert 0.0 in full_initials
    assert 50.0 in full_initials
    assert not any(49.0 < value < 50.0 for value in model.inputs[0])


def test_finite_horizon_windows_are_episode_local_and_exact() -> None:
    episode = _episode("episode-a", "base", length=64)
    artifact = evaluate_episode_metrics_v2(AdditiveDepthModel(), episode, policy=_policy())

    assert tuple(artifact.horizons) == ("one_step", "5", "20", "60", "full")
    assert artifact.horizons["5"].window_count == 60
    assert artifact.horizons["20"].window_count == 45
    assert artifact.horizons["60"].window_count == 5
    assert artifact.horizons["full"].window_count == 1
    assert all(entry.status == "success" for entry in artifact.horizons.values())
    assert all(entry.values["depth_rmse"] == pytest.approx(0.0) for entry in artifact.horizons.values())


def test_short_episode_fails_explicitly_before_evaluation() -> None:
    with pytest.raises(ValueError, match="episode_too_short:horizon=60"):
        evaluate_episode_metrics_v2(
            AdditiveDepthModel(),
            _episode("short", "base", length=59),
            policy=_policy(),
        )


@pytest.mark.parametrize(
    ("failure", "reason", "count_field"),
    [
        ("zero", "quaternion_invalid", "invalid_quaternion_count"),
        ("nonfinite", "prediction_nonfinite", "nonfinite_count"),
        ("projection", "quaternion_projection_limit", "projection_failure_count"),
        ("divergence", "rollout_diverged", "divergence_count"),
    ],
)
def test_rollout_failures_are_reason_coded_and_never_dropped(failure, reason, count_field) -> None:
    trace = rollout_episode_v2(
        FailingQuaternionModel(failure),
        _episode("failure", "base", length=64),
        start=0,
        steps=5,
        policy=_policy(),
    )
    assert trace.status == "failed"
    assert trace.reason_code == reason
    assert getattr(trace, count_field) == 1
    assert trace.attempted_transition_count == 2
    assert trace.completed_transition_count == 1


def test_metric_schema_rejects_attitude_component_aliases() -> None:
    assert validate_official_metric_names_v2(OFFICIAL_ERROR_METRICS_V2) == OFFICIAL_ERROR_METRICS_V2
    for alias in (
        "attitude_angle_rmse",
        "quaternion_component_rmse",
        "orientation_rmse",
    ):
        with pytest.raises(ValueError, match="metric_alias_forbidden"):
            validate_official_metric_names_v2((*OFFICIAL_ERROR_METRICS_V2, alias))


def test_episode_schema_has_no_reference_or_yaw_target_scoring_route() -> None:
    payload = {
        "episode_id": "uuv4-test",
        "configuration": "uuv4",
        "states": np.zeros((64, 11)),
        "controls": np.zeros((64, 4)),
        "targets": np.zeros((64, 11)),
        "reference_5": np.zeros((64, 5)),
    }
    with pytest.raises(ValueError, match="evaluation_field_set_mismatch"):
        EpisodeTrajectoryV2.from_mapping(payload)
    payload.pop("reference_5")
    payload["yaw_target"] = np.zeros(64)
    with pytest.raises(ValueError, match="evaluation_field_set_mismatch"):
        EpisodeTrajectoryV2.from_mapping(payload)


def _metric_artifact(configuration: str, value: float, count: int) -> EpisodeMetricArtifactV2:
    horizons = {
        label: HorizonMetricV2(
            label=label,
            status="success",
            reason_code=None,
            values={name: float(value) for name in OFFICIAL_ERROR_METRICS_V2},
            transition_count=count,
            window_count=1,
            nonfinite_count=0,
            invalid_quaternion_count=0,
            projection_failure_count=0,
            divergence_count=0,
            projection_count=0,
            projection_correction_max=0.0,
        )
        for label in ("one_step", "5", "20", "60", "full")
    }
    return EpisodeMetricArtifactV2(
        episode_id=f"{configuration}-episode",
        configuration=configuration,
        policy_sha256="a" * 64,
        horizons=horizons,
    )


def test_aggregate_is_equal_configuration_macro_with_mandatory_worst_and_row_diagnostic() -> None:
    aggregate = aggregate_configuration_metrics_v2(
        (
            _metric_artifact("base", 1.0, 100),
            _metric_artifact("uuv6", 3.0, 1),
        ),
        expected_configurations=("base", "uuv6"),
        expected_horizons=("one_step", "5", "20", "60", "full"),
    )
    depth_macro = aggregate["equal_configuration_macro"]["full"]["depth_rmse"]
    depth_worst = aggregate["worst_configuration"]["full"]["depth_rmse"]
    row_weighted = aggregate["row_weighted_diagnostic"]["full"]["depth_rmse"]
    assert aggregate["metric_schema_version"] == METRIC_SCHEMA_VERSION_V2
    assert depth_macro == pytest.approx(2.0)
    assert depth_worst == pytest.approx(3.0)
    assert row_weighted == pytest.approx(103.0 / 101.0)
    assert row_weighted != pytest.approx(depth_macro)


@pytest.mark.parametrize(
    ("artifacts", "configurations", "horizons", "reason"),
    [
        (
            (_metric_artifact("base", 1.0, 10),),
            ("base", "uuv6"),
            ("one_step", "5", "20", "60", "full"),
            "aggregate_configuration_set_mismatch",
        ),
        (
            (_metric_artifact("base", 1.0, 10),),
            ("base",),
            ("one_step", "5", "20", "full"),
            "aggregate_horizon_set_mismatch",
        ),
    ],
)
def test_aggregate_rejects_missing_configurations_or_horizons(
    artifacts, configurations, horizons, reason
) -> None:
    with pytest.raises(ValueError, match=reason):
        aggregate_configuration_metrics_v2(
            artifacts,
            expected_configurations=configurations,
            expected_horizons=horizons,
        )


def test_policy_thresholds_are_required_and_aggregate_has_no_supplied_summary_route() -> None:
    with pytest.raises(TypeError):
        RolloutAnalysisPolicyV2(horizons=(5, 20, 60, "full"))
    parameters = inspect.signature(aggregate_configuration_metrics_v2).parameters
    assert "summary" not in parameters
    assert "macro" not in parameters
    assert "worst" not in parameters
