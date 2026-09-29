"""Causal SO(3) rollout and inherited six-metric contracts for Phase 8.1."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from koopman.actuator_memory_v21 import ActuatorMemoryProxyV21
from koopman.metrics_v21 import (
    OFFICIAL_ERROR_METRICS_V21,
    OFFICIAL_ROLLOUT_POLICY_V21,
    REQUIRED_HORIZON_LABELS_V21,
    RolloutAnalysisPolicyV21,
    RolloutEpisodeV21,
    aggregate_configuration_metrics_v21,
    evaluate_episode_metrics_v21,
    rollout_episode_v21,
)


class ZeroIncrementModel:
    def __init__(self) -> None:
        self.memory_inputs: list[np.ndarray] = []

    def predict_increment(self, state, actuator_memory, control, *, platform_score=None):
        self.memory_inputs.append(np.array(actuator_memory, copy=True))
        return np.zeros(10, dtype=np.float64)


class NonfiniteModel:
    def predict_increment(self, state, actuator_memory, control, *, platform_score=None):
        return np.full(10, np.nan)


class DivergingModel:
    def predict_increment(self, state, actuator_memory, control, *, platform_score=None):
        result = np.zeros(10, dtype=np.float64)
        result[0] = 1.0e6
        return result


def _policy() -> RolloutAnalysisPolicyV21:
    return OFFICIAL_ROLLOUT_POLICY_V21


def _episode(
    *,
    configuration: str = "base",
    count: int = 64,
    future_memory_fill: float = 0.0,
) -> RolloutEpisodeV21:
    states = np.zeros((count, 11), dtype=np.float64)
    states[:, 1] = 1.0
    targets = states.copy()
    controls = np.tile(np.asarray([0.5, -0.25, 0.125, -0.5]), (count, 1))
    memory = np.full((count, 4), future_memory_fill, dtype=np.float64)
    memory[0] = 0.0
    return RolloutEpisodeV21(
        episode_id=f"episode-{configuration}",
        configuration=configuration,
        states_11=states,
        actuator_memory_4=memory,
        virtual_control_4=controls,
        targets_11=targets,
        tau_s=0.2,
        control_dt_s=0.1,
        control_mask_4=(1, 1, 1, 1),
    )


def test_rollout_reads_only_window_start_memory_then_uses_production_proxy() -> None:
    episode = _episode(future_memory_fill=999.0)
    model = ZeroIncrementModel()

    trace = rollout_episode_v21(
        model, episode, start=0, steps=5, policy=_policy()
    )

    independent = ActuatorMemoryProxyV21(0.2, 0.1, (1, 1, 1, 1))
    expected_inputs = []
    for control in episode.virtual_control_4[:5]:
        expected_inputs.append(independent.current())
        independent.advance(control)
    assert trace.status == "success"
    assert np.array_equal(trace.memory_inputs_4, np.asarray(expected_inputs))
    assert np.array_equal(np.asarray(model.memory_inputs), trace.memory_inputs_4)
    assert not np.any(trace.memory_inputs_4 == 999.0)


def test_mutating_future_memory_truth_does_not_change_same_window_trace_or_metrics() -> None:
    clean = _episode(future_memory_fill=0.0)
    poisoned = _episode(future_memory_fill=-777.0)

    first = rollout_episode_v21(
        ZeroIncrementModel(), clean, start=0, steps=20, policy=_policy()
    )
    second = rollout_episode_v21(
        ZeroIncrementModel(), poisoned, start=0, steps=20, policy=_policy()
    )

    assert first.to_dict() == second.to_dict()


def test_multi_step_rollout_preserves_quaternion_unit_norm_without_projection() -> None:
    episode = _episode(count=100)
    trace = rollout_episode_v21(
        ZeroIncrementModel(), episode, start=0, steps=100, policy=_policy()
    )

    assert trace.status == "success"
    assert trace.completed_transition_count == 100
    assert np.max(np.abs(np.linalg.norm(trace.predictions[:, 1:5], axis=1) - 1.0)) <= 1e-15
    assert trace.quaternion_projection_count == 0


@pytest.mark.parametrize(
    ("model", "reason"),
    ((NonfiniteModel(), "prediction_nonfinite"), (DivergingModel(), "rollout_diverged")),
)
def test_rollout_failures_are_reason_coded(model, reason: str) -> None:
    trace = rollout_episode_v21(model, _episode(), start=0, steps=5, policy=_policy())
    assert trace.status == "failed"
    assert trace.reason_code == reason
    assert trace.completed_transition_count == 0


def test_official_horizons_and_six_sign_invariant_metrics_are_preserved() -> None:
    episode = _episode()
    # Equivalent quaternion signs must remain a zero-orientation-error truth.
    targets = np.array(episode.targets_11, copy=True)
    targets[::2, 1:5] *= -1.0
    episode = RolloutEpisodeV21(
        episode_id=episode.episode_id,
        configuration=episode.configuration,
        states_11=episode.states_11,
        actuator_memory_4=episode.actuator_memory_4,
        virtual_control_4=episode.virtual_control_4,
        targets_11=targets,
        tau_s=episode.tau_s,
        control_dt_s=episode.control_dt_s,
        control_mask_4=episode.control_mask_4,
    )

    artifact = evaluate_episode_metrics_v21(
        ZeroIncrementModel(), episode, policy=_policy()
    )

    assert tuple(artifact.horizons) == REQUIRED_HORIZON_LABELS_V21
    for entry in artifact.horizons.values():
        assert tuple(entry.values) == OFFICIAL_ERROR_METRICS_V21
        assert entry.status == "success"
        assert all(value == pytest.approx(0.0) for value in entry.values.values())


def test_equal_configuration_aggregation_does_not_row_weight_macro() -> None:
    first = evaluate_episode_metrics_v21(
        ZeroIncrementModel(), _episode(configuration="base"), policy=_policy()
    )
    second_episode = _episode(configuration="uuv6")
    shifted_targets = np.array(second_episode.targets_11, copy=True)
    shifted_targets[:, 0] = 2.0
    second_episode = RolloutEpisodeV21(
        episode_id=second_episode.episode_id,
        configuration=second_episode.configuration,
        states_11=second_episode.states_11,
        actuator_memory_4=second_episode.actuator_memory_4,
        virtual_control_4=second_episode.virtual_control_4,
        targets_11=shifted_targets,
        tau_s=second_episode.tau_s,
        control_dt_s=second_episode.control_dt_s,
        control_mask_4=second_episode.control_mask_4,
    )
    second = evaluate_episode_metrics_v21(
        ZeroIncrementModel(), second_episode, policy=_policy()
    )

    aggregate = aggregate_configuration_metrics_v21(
        (first, second),
        expected_configurations=("base", "uuv6"),
        expected_horizons=REQUIRED_HORIZON_LABELS_V21,
    )

    assert aggregate["equal_configuration_macro"]["60"]["depth_rmse"] == pytest.approx(1.0)
    assert aggregate["per_configuration"]["base"]["60"]["depth_rmse"] == pytest.approx(0.0)
    assert aggregate["per_configuration"]["uuv6"]["60"]["depth_rmse"] == pytest.approx(2.0)


def test_row_weighted_aggregation_is_diagnostic_and_does_not_replace_macro() -> None:
    short = evaluate_episode_metrics_v21(
        ZeroIncrementModel(), _episode(configuration="base", count=64), policy=_policy()
    )
    long_episode = _episode(configuration="uuv6", count=128)
    shifted_targets = np.array(long_episode.targets_11, copy=True)
    shifted_targets[:, 0] = 2.0
    long_episode = RolloutEpisodeV21(
        episode_id=long_episode.episode_id,
        configuration=long_episode.configuration,
        states_11=long_episode.states_11,
        actuator_memory_4=long_episode.actuator_memory_4,
        virtual_control_4=long_episode.virtual_control_4,
        targets_11=shifted_targets,
        tau_s=long_episode.tau_s,
        control_dt_s=long_episode.control_dt_s,
        control_mask_4=long_episode.control_mask_4,
    )
    long = evaluate_episode_metrics_v21(
        ZeroIncrementModel(), long_episode, policy=_policy()
    )

    aggregate = aggregate_configuration_metrics_v21(
        (short, long),
        expected_configurations=("base", "uuv6"),
        expected_horizons=REQUIRED_HORIZON_LABELS_V21,
    )

    # Horizon 60 contains 5 short-episode windows and 69 long-episode windows.
    assert aggregate["equal_configuration_macro"]["60"]["depth_rmse"] == pytest.approx(1.0)
    assert aggregate["row_weighted_diagnostic"]["60"]["depth_rmse"] == pytest.approx(
        (0.0 * 5 + 2.0 * 69) / 74
    )


def test_aggregation_rejects_duplicate_expected_configurations() -> None:
    artifact = evaluate_episode_metrics_v21(
        ZeroIncrementModel(), _episode(configuration="base"), policy=_policy()
    )

    with pytest.raises(ValueError, match="aggregate_configuration_set_mismatch"):
        aggregate_configuration_metrics_v21(
            (artifact,),
            expected_configurations=("base", "base"),
            expected_horizons=REQUIRED_HORIZON_LABELS_V21,
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "transition_count",
        "window_count",
        "nonfinite_count",
        "invalid_quaternion_count",
        "quaternion_unit_norm_drift_count",
        "divergence_count",
        "quaternion_projection_count",
    ),
)
def test_horizon_metric_rejects_negative_or_boolean_counts(field_name: str) -> None:
    artifact = evaluate_episode_metrics_v21(
        ZeroIncrementModel(), _episode(), policy=_policy()
    )
    entry = artifact.horizons["5"]

    for invalid in (-1, True):
        with pytest.raises(ValueError, match=f"metric_count_invalid:{field_name}"):
            replace(entry, **{field_name: invalid})


def test_episode_metric_artifact_rejects_hash_and_horizon_label_substitution() -> None:
    artifact = evaluate_episode_metrics_v21(
        ZeroIncrementModel(), _episode(), policy=_policy()
    )

    with pytest.raises(ValueError, match="metric_policy_hash_invalid"):
        replace(artifact, policy_sha256="not-a-sha256")

    horizons = dict(artifact.horizons)
    horizons["5"] = replace(horizons["5"], label="20")
    with pytest.raises(ValueError, match="metric_horizon_invalid"):
        replace(artifact, horizons=horizons)


def test_rollout_accepts_only_the_frozen_inherited_divergence_policy() -> None:
    assert OFFICIAL_ROLLOUT_POLICY_V21.payload() == {
        "angular_velocity_abs_max": 100.0,
        "depth_abs_max": 100.0,
        "horizons": [5, 20, 60, "full"],
        "linear_velocity_abs_max": 100.0,
        "version": "phase8.1-rollout-analysis-policy-v1",
    }
    mutated = RolloutAnalysisPolicyV21(
        horizons=(5, 20, 60, "full"),
        depth_abs_max=100.0,
        linear_velocity_abs_max=99.0,
        angular_velocity_abs_max=100.0,
    )

    with pytest.raises(ValueError, match="rollout_policy_not_official"):
        rollout_episode_v21(
            ZeroIncrementModel(),
            _episode(),
            start=0,
            steps=5,
            policy=mutated,
        )
