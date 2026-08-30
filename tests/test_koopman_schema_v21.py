"""Strict additive schema-v2.1 transition, episode and artifact contracts."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from koopman.schema_v2 import validate_transition_v2
from koopman.schema_v21 import (
    KOOPMAN_EPISODE_MANIFEST_V21,
    KOOPMAN_TRANSITION_SCHEMA_V21,
    KoopmanEpisodeLoggerV21,
    build_local_transition_v21,
    load_episode_jsonl_v21,
    validate_episode_artifact_v21,
    validate_episode_v21,
    validate_transition_v21,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "koopman_v2_three_topologies"


def valid_episode_v21(configuration: str = "base") -> list[dict]:
    source_path = FIXTURE_ROOT / f"{configuration}.jsonl"
    rows = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines()]
    tau_s = float(rows[0]["platform_context"]["thruster_dynamics_time_constant_s"])
    control_dt_s = float(rows[0]["episode_provenance"]["control_dt_s"])
    alpha = math.exp(-control_dt_s / tau_s)
    memory = np.zeros(4, dtype=np.float64)
    for row in rows:
        row["schema_version"] = KOOPMAN_TRANSITION_SCHEMA_V21
        row["actuator_memory_4"] = memory.tolist()
        provenance = row["episode_provenance"]
        provenance["physics_dt_s"] = control_dt_s / 2
        provenance["decimation"] = 2
        control = np.asarray(row["virtual_control_4"], dtype=np.float64)
        memory = alpha * memory + (1.0 - alpha) * control
    return rows


def test_exact_v21_transition_and_local_builder_are_version_isolated() -> None:
    row = valid_episode_v21()[0]

    validate_transition_v21(row)
    built = build_local_transition_v21(**row)
    built["state_11"][0] = 99.0

    assert row["state_11"][0] != 99.0
    with pytest.raises(ValueError, match="schema_version_mismatch|field_set_mismatch"):
        validate_transition_v2(row)
    legacy = deepcopy(row)
    legacy["schema_version"] = "easyuuv-koopman-transition-v2"
    legacy.pop("actuator_memory_4")
    legacy["episode_provenance"].pop("physics_dt_s")
    legacy["episode_provenance"].pop("decimation")
    with pytest.raises(ValueError, match="schema_version_mismatch|field_set_mismatch"):
        validate_transition_v21(legacy)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (lambda row: row.pop("actuator_memory_4"), "field_set_mismatch"),
        (lambda row: row.__setitem__("future_memory_truth", [0.0] * 4), "field_set_mismatch"),
        (lambda row: row.__setitem__("actuator_memory_4", [0.0] * 3), "shape_invalid"),
        (
            lambda row: row["episode_provenance"].__setitem__("physics_dt_s", 0.0),
            "timing_provenance_invalid",
        ),
        (
            lambda row: row["episode_provenance"].__setitem__("decimation", 2.0),
            "timing_provenance_invalid",
        ),
        (
            lambda row: row["episode_provenance"].__setitem__("decimation", 3),
            "timing_relation_mismatch",
        ),
    ),
)
def test_v21_transition_rejects_field_and_timing_mutations(mutation, reason: str) -> None:
    row = valid_episode_v21()[0]
    mutation(row)

    with pytest.raises(ValueError, match=reason):
        validate_transition_v21(row)


def test_uuv4_yaw_control_and_memory_are_exact_zero() -> None:
    row = valid_episode_v21("uuv4")[0]
    validate_transition_v21(row)

    row["actuator_memory_4"][2] = np.nextafter(0.0, 1.0)
    with pytest.raises(ValueError, match="underactuated_yaw_memory_nonzero"):
        validate_transition_v21(row)


def test_episode_replays_unique_recurrence_and_starts_at_exact_zero() -> None:
    rows = valid_episode_v21()

    summary = validate_episode_v21(rows)

    assert summary["record_count"] == 2
    assert summary["timing_provenance"] == {
        "physics_dt_s": rows[0]["episode_provenance"]["physics_dt_s"],
        "decimation": 2,
        "control_dt_s": rows[0]["episode_provenance"]["control_dt_s"],
    }

    nonzero_first = deepcopy(rows)
    nonzero_first[0]["actuator_memory_4"][0] = 1e-15
    with pytest.raises(ValueError, match="actuator_memory_initial_state_nonzero"):
        validate_episode_v21(nonzero_first)

    recurrence_drift = deepcopy(rows)
    recurrence_drift[1]["actuator_memory_4"][0] += 1e-9
    with pytest.raises(ValueError, match="actuator_memory_recurrence_mismatch"):
        validate_episode_v21(recurrence_drift)


def test_json_binary64_roundtrip_preserves_memory_bytes() -> None:
    rows = valid_episode_v21()
    before = np.asarray(rows[1]["actuator_memory_4"], dtype=np.float64)

    decoded = json.loads(json.dumps(rows[1], allow_nan=False))
    after = np.asarray(decoded["actuator_memory_4"], dtype=np.float64)

    assert before.tobytes() == after.tobytes()
    validate_transition_v21(decoded)


def test_v21_logger_manifest_and_loader_are_strict_and_atomic(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "episode.jsonl"
    manifest_path = tmp_path / "episode.manifest.json"
    rows = valid_episode_v21()

    with KoopmanEpisodeLoggerV21(jsonl_path, manifest_path=manifest_path) as logger:
        for row in rows:
            logger.write(row)
        manifest = logger.finalize()

    assert manifest["manifest_version"] == KOOPMAN_EPISODE_MANIFEST_V21
    assert manifest["transition_schema_version"] == KOOPMAN_TRANSITION_SCHEMA_V21
    assert manifest["timing_provenance"] == {
        "physics_dt_s": rows[0]["episode_provenance"]["physics_dt_s"],
        "decimation": 2,
        "control_dt_s": rows[0]["episode_provenance"]["control_dt_s"],
    }
    assert not Path(f"{jsonl_path}.part").exists()
    assert len(load_episode_jsonl_v21(jsonl_path)) == 2
    assert validate_episode_artifact_v21(jsonl_path, manifest_path)["record_count"] == 2

    mutated = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutated["transition_schema_version"] = "easyuuv-koopman-transition-v2"
    manifest_path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version_mismatch"):
        validate_episode_artifact_v21(jsonl_path, manifest_path)


def test_v21_logger_preserves_server_evidence_and_runtime_provenance(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "server-episode.jsonl"
    manifest_path = tmp_path / "server-episode.manifest.json"
    rows = valid_episode_v21()
    for row in rows:
        row["episode_provenance"]["evidence_level"] = "server_isaac_smoke"
    runtime = {
        "artifact_origin": "server_isaac_smoke",
        "generator": "collect_koopman_v21_identification",
        "semantic_status": "pass",
    }

    with KoopmanEpisodeLoggerV21(
        jsonl_path,
        manifest_path=manifest_path,
        runtime_provenance=runtime,
    ) as logger:
        for row in rows:
            logger.write(row)
        manifest = logger.finalize()

    assert manifest["evidence_level"] == "server_isaac_smoke"
    assert manifest["runtime_provenance"] == runtime
    assert validate_episode_artifact_v21(jsonl_path, manifest_path)["evidence_level"] == "server_isaac_smoke"
