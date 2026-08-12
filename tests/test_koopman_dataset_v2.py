"""Contracts for immutable model-facing Koopman schema-v2 datasets."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from koopman.dataset_v2 import (
    ActuatorDiagnostics,
    KoopmanDatasetV2,
    dataset_from_records_v2,
    load_koopman_episode_v2,
)
from koopman.schema_v2 import load_episode_jsonl_v2, validate_episode_artifact_v2


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "koopman_v2_three_topologies"
EXPECTED_HASHES = {
    "base": "1167f0e4bb8ffcc31f9260495273798cdb11bc40e068008a9f258899bc198259",
    "uuv6": "b0bafce33b04fdfd300292b218f6e8c93300515f1a23ba91e54a306e793443b5",
    "uuv4": "ac6d161e8d292420fd9773cb28fc2125723d508c5995288662c01405b4faf0a8",
}


def _paths(configuration: str) -> tuple[Path, Path]:
    return (
        FIXTURE_ROOT / f"{configuration}.jsonl",
        FIXTURE_ROOT / f"{configuration}.manifest.json",
    )


@pytest.mark.parametrize("configuration", ("base", "uuv6", "uuv4"))
def test_committed_fixture_pair_is_strict_local_contract_with_locked_hash(
    configuration: str,
) -> None:
    jsonl_path, manifest_path = _paths(configuration)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_hash = hashlib.sha256(jsonl_path.read_bytes()).hexdigest()

    assert actual_hash == EXPECTED_HASHES[configuration]
    assert manifest["transition_sha256"] == actual_hash
    assert manifest["record_count"] == 2
    assert manifest["evidence_level"] == "local_contract"
    assert manifest["episode_invariants"]["configuration"] == configuration
    assert manifest["episode_invariants"]["evidence_level"] == "local_contract"
    assert validate_episode_artifact_v2(jsonl_path, manifest_path)["record_count"] == 2


@pytest.mark.parametrize(
    ("configuration", "thruster_count"),
    (("base", 8), ("uuv6", 6), ("uuv4", 4)),
)
def test_dataset_v2_u_is_virtual_control_4(
    configuration: str, thruster_count: int
) -> None:
    jsonl_path, manifest_path = _paths(configuration)
    records = load_episode_jsonl_v2(jsonl_path)
    dataset = load_koopman_episode_v2(jsonl_path, manifest_path)

    assert isinstance(dataset, KoopmanDatasetV2)
    assert dataset.X.shape == (2, 11)
    assert dataset.U.shape == (2, 4)
    assert dataset.R.shape == (2, 5)
    assert dataset.Y.shape == (2, 11)
    np.testing.assert_allclose(dataset.U, [row["virtual_control_4"] for row in records])
    assert dataset.U is dataset.virtual_control_4
    assert not hasattr(dataset, "action")
    assert not hasattr(dataset, "control")
    with pytest.raises(TypeError):
        tuple(dataset)

    diagnostics = dataset.diagnostics
    assert isinstance(diagnostics, ActuatorDiagnostics)
    assert diagnostics.motor_pwm_padded_8.shape == (2, 8)
    assert diagnostics.thruster_mask_8.shape == (2, 8)
    assert diagnostics.applied_wrench_6.shape == (2, 6)
    assert diagnostics.saturation_ratio.shape == (2,)
    assert diagnostics.energy_proxy.shape == (2,)
    assert np.all(diagnostics.thruster_mask_8[:, :thruster_count] == 1)
    assert np.all(diagnostics.thruster_mask_8[:, thruster_count:] == 0)
    assert np.all(diagnostics.motor_pwm_padded_8[:, thruster_count:] == 0.0)
    np.testing.assert_allclose(
        diagnostics.energy_proxy,
        np.sum(np.square(diagnostics.motor_pwm_padded_8), axis=1),
    )


def test_dataset_v2_preserves_row_addressable_context_and_provenance() -> None:
    dataset = load_koopman_episode_v2(*_paths("uuv6"))

    assert dataset.configurations == ("uuv6", "uuv6")
    assert dataset.episode_ids == ("contract-uuv6-001", "contract-uuv6-001")
    np.testing.assert_array_equal(dataset.step_indices, [0, 1])
    assert dataset.platform_contexts[0]["thruster_count"] == 6
    assert dataset.environment_contexts_oracle[0]["available"] is True
    assert dataset.environment_contexts_estimated[0]["available"] is False
    assert dataset.episode_provenance[1]["step_index"] == 1
    assert dataset.source_paths == tuple(str(path) for path in _paths("uuv6"))


def test_dataset_v2_arrays_and_metadata_are_read_only_copies() -> None:
    records = load_episode_jsonl_v2(_paths("base")[0])
    original_control = list(records[0]["virtual_control_4"])
    dataset = dataset_from_records_v2(records)

    records[0]["virtual_control_4"][0] = 0.99
    assert dataset.U[0].tolist() == original_control
    for array in (
        dataset.X,
        dataset.U,
        dataset.R,
        dataset.Y,
        dataset.step_indices,
        dataset.diagnostics.motor_pwm_padded_8,
        dataset.diagnostics.thruster_mask_8,
        dataset.diagnostics.applied_wrench_6,
        dataset.diagnostics.saturation_ratio,
        dataset.diagnostics.energy_proxy,
    ):
        assert array.flags.writeable is False
        with pytest.raises(ValueError):
            array.flat[0] = 123.0
    with pytest.raises(TypeError):
        dataset.platform_contexts[0]["mass_kg"] = 99.0


def test_dataset_v2_rejects_mixed_configuration_episode() -> None:
    base = load_episode_jsonl_v2(_paths("base")[0])
    uuv6 = load_episode_jsonl_v2(_paths("uuv6")[0])
    rows = [deepcopy(base[0]), deepcopy(uuv6[1])]
    with pytest.raises(ValueError, match="episode_invariant_drift|platform_context_drift"):
        dataset_from_records_v2(rows)


def test_dataset_v2_rejects_empty_and_mismatched_rows() -> None:
    with pytest.raises(ValueError, match="episode_too_short|dataset_empty"):
        dataset_from_records_v2([])

    dataset = load_koopman_episode_v2(*_paths("base"))
    with pytest.raises(ValueError, match="dataset_row_count_mismatch|dataset_shape_invalid"):
        replace(dataset, X=np.zeros((1, 11)))
    with pytest.raises(ValueError, match="dataset_row_count_mismatch"):
        replace(dataset, platform_contexts=())


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (lambda row: row.__setitem__("state_11", [0.0] * 10), "shape_invalid"),
        (
            lambda row: row.__setitem__("virtual_control_4", [0.0, 0.0, 0.0, float("nan")]),
            "nonfinite_value",
        ),
        (
            lambda row: row.__setitem__("virtual_control_4", list(row["motor_pwm_padded_8"])),
            "shape_invalid",
        ),
        (lambda row: row.pop("platform_context"), "field_set_mismatch"),
        (lambda row: row.pop("episode_provenance"), "field_set_mismatch|type_invalid"),
    ),
)
def test_dataset_v2_rejects_invalid_dimensions_pwm_control_and_metadata_loss(
    mutation, reason: str
) -> None:
    rows = load_episode_jsonl_v2(_paths("base")[0])
    mutation(rows[0])
    with pytest.raises(ValueError, match=reason):
        dataset_from_records_v2(rows)
