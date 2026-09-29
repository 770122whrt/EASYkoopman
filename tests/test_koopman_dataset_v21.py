"""Model-facing 19D dataset contracts for additive schema v2.1."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from koopman.dataset_v21 import (
    ActuatorDiagnosticsV21,
    KoopmanDatasetV21,
    dataset_from_records_v21,
    load_koopman_episode_v21,
)
from koopman.schema_v21 import KOOPMAN_TRANSITION_SCHEMA_V21, KoopmanEpisodeLoggerV21


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "koopman_v2_three_topologies"


def _records(configuration: str = "base") -> list[dict]:
    source = FIXTURE_ROOT / f"{configuration}.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    tau_s = float(rows[0]["platform_context"]["thruster_dynamics_time_constant_s"])
    control_dt_s = float(rows[0]["episode_provenance"]["control_dt_s"])
    alpha = math.exp(-control_dt_s / tau_s)
    memory = np.zeros(4, dtype=np.float64)
    for row in rows:
        row["schema_version"] = KOOPMAN_TRANSITION_SCHEMA_V21
        row["actuator_memory_4"] = memory.tolist()
        row["episode_provenance"]["physics_dt_s"] = control_dt_s / 2
        row["episode_provenance"]["decimation"] = 2
        memory = alpha * memory + (1.0 - alpha) * np.asarray(
            row["virtual_control_4"], dtype=np.float64
        )
    return rows


def test_dataset_exposes_only_the_frozen_19d_primary_view() -> None:
    rows = _records()
    dataset = dataset_from_records_v21(rows)

    assert isinstance(dataset, KoopmanDatasetV21)
    assert dataset.X.shape == (2, 19)
    assert dataset.primary_X is dataset.X
    assert dataset.state_11.shape == (2, 11)
    assert dataset.actuator_memory_4.shape == (2, 4)
    assert dataset.virtual_control_4.shape == (2, 4)
    assert dataset.U is dataset.virtual_control_4
    assert dataset.Y.shape == (2, 11)
    np.testing.assert_array_equal(
        dataset.X,
        np.concatenate(
            [dataset.state_11, dataset.actuator_memory_4, dataset.virtual_control_4],
            axis=1,
        ),
    )
    assert not hasattr(dataset, "motor_pwm_padded_8")
    assert not hasattr(dataset, "applied_wrench_6")
    assert not hasattr(dataset, "environment_contexts_oracle")


def test_diagnostics_are_named_read_only_and_cannot_change_primary_bytes() -> None:
    rows = _records()
    mutated = deepcopy(rows)
    mutated[0]["motor_pwm_padded_8"][0] = -0.9
    mutated[0]["applied_wrench_6"] = [9.0] * 6
    mutated[0]["environment_context_oracle"]["values"]["fluid_velocity_world_3"] = [
        9.0,
        8.0,
        7.0,
    ]

    original = dataset_from_records_v21(rows)
    changed_diagnostics = dataset_from_records_v21(mutated)

    assert original.X.tobytes() == changed_diagnostics.X.tobytes()
    assert isinstance(original.diagnostics, ActuatorDiagnosticsV21)
    assert original.diagnostics.motor_pwm_padded_8.flags.writeable is False
    assert original.diagnostics.applied_wrench_6.flags.writeable is False
    assert original.diagnostics.environment_contexts_oracle[0]["available"] is True
    with pytest.raises(ValueError):
        original.diagnostics.applied_wrench_6[0, 0] = 1.0
    with pytest.raises(TypeError):
        original.diagnostics.environment_contexts_oracle[0]["available"] = False


def test_dataset_arrays_and_metadata_are_defensive_and_read_only() -> None:
    rows = _records("uuv4")
    dataset = dataset_from_records_v21(rows, source_paths=("a.jsonl", "a.manifest.json"))
    rows[0]["state_11"][0] = 123.0

    assert dataset.X[0, 0] != 123.0
    assert dataset.actuator_memory_4[:, 2].tobytes() == np.zeros(
        2, dtype=np.float64
    ).tobytes()
    for array in (
        dataset.X,
        dataset.state_11,
        dataset.actuator_memory_4,
        dataset.U,
        dataset.R,
        dataset.Y,
        dataset.step_indices,
    ):
        assert array.flags.writeable is False
    with pytest.raises(TypeError):
        dataset.platform_contexts[0]["mass_kg"] = 99.0
    assert dataset.source_paths == ("a.jsonl", "a.manifest.json")


def test_loader_requires_a_strict_v21_episode_manifest_pair(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "episode.jsonl"
    manifest_path = tmp_path / "episode.manifest.json"
    with KoopmanEpisodeLoggerV21(jsonl_path, manifest_path=manifest_path) as logger:
        for row in _records():
            logger.write(row)
        logger.finalize()

    dataset = load_koopman_episode_v21(jsonl_path, manifest_path)

    assert dataset.sample_count == 2
    assert dataset.source_paths == (str(jsonl_path), str(manifest_path))


def test_dataset_rejects_unvalidated_recurrence_and_empty_input() -> None:
    with pytest.raises(ValueError, match="dataset_empty|episode_too_short"):
        dataset_from_records_v21([])

    rows = _records()
    rows[1]["actuator_memory_4"][0] += 1e-6
    with pytest.raises(ValueError, match="actuator_memory_recurrence_mismatch"):
        dataset_from_records_v21(rows)
