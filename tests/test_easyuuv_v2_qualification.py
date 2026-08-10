"""Strict mutation tests for the EasyUUV v2 qualification artifact gate."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile

import pytest

from workflows.easyuuv_v2_qualification_artifact import (
    MAX_ARTIFACT_BYTES,
    load_qualification_payload,
    validate_qualification_file,
    validate_qualification_payload,
)
from workflows.validate_easyuuv_v2_qualification import main


PUBLIC_CONFIGURATIONS = (
    "base",
    "long_body",
    "heavy_moderate",
    "asymmetric",
    "uuv6",
    "uuv6_angled",
    "uuv4",
    "uuv4_angled",
)

EXPECTED_TOPOLOGY = {
    "base": {"thruster_count": 8, "control_mask": (1, 1, 1, 1), "declared_control_rank": 4},
    "long_body": {"thruster_count": 8, "control_mask": (1, 1, 1, 1), "declared_control_rank": 4},
    "heavy_moderate": {"thruster_count": 8, "control_mask": (1, 1, 1, 1), "declared_control_rank": 4},
    "asymmetric": {"thruster_count": 8, "control_mask": (1, 1, 1, 1), "declared_control_rank": 4},
    "uuv6": {"thruster_count": 6, "control_mask": (1, 1, 1, 1), "declared_control_rank": 4},
    "uuv6_angled": {"thruster_count": 6, "control_mask": (1, 1, 1, 1), "declared_control_rank": 4},
    "uuv4": {"thruster_count": 4, "control_mask": (1, 1, 0, 1), "declared_control_rank": 3},
    "uuv4_angled": {"thruster_count": 4, "control_mask": (1, 1, 0, 1), "declared_control_rank": 3},
}


@pytest.fixture
def local_tmp_path() -> Path:
    """Keep scratch files inside the repository on restricted Windows runners."""
    scratch_root = Path(__file__).resolve().parents[1] / ".pytest-tmp"
    scratch_root.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="qualification-", dir=scratch_root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _valid_row(name: str, *, server: bool = True) -> dict:
    topology = EXPECTED_TOPOLOGY[name]
    return {
        "configuration": name,
        "thruster_count": topology["thruster_count"],
        "control_channels": ["roll", "pitch", "yaw", "depth"],
        "control_mask": list(topology["control_mask"]),
        "declared_control_rank": topology["declared_control_rank"],
        "environment_created": server,
        "reset_passed": server,
        "steps_completed": (64 if name == "base" else 8) if server else 0,
        "action_min": -1.0 if server else 0.0,
        "action_max": 1.0 if server else 0.0,
        "motor_min": -1.0 if server else 0.0,
        "motor_max": 1.0 if server else 0.0,
        "motor_vector_length": topology["thruster_count"],
        "nonfinite_count": 0,
        "dimension_mismatch_count": 0,
        "seed": 0,
        "status": "pass",
        "reason_codes": [],
    }


def valid_server_payload() -> dict:
    return {
        "schema_version": "easyuuv-v2-qualification-v1",
        "evidence_level": "server_isaac_smoke",
        "expected_isaac_sim": "5.0",
        "expected_isaac_lab": "2.2.1",
        "actual_isaac_sim": "5.0",
        "actual_isaac_lab": "2.2.1",
        "runtime_provenance": {
            "isaac_sim_distribution": "5.0.0.0",
            "isaac_lab_distribution": "0.45.9",
            "isaac_lab_repo_commit": "c" * 40,
            "isaac_lab_repo_tag": "v2.2.1",
        },
        "task_id": "EasyUUV-Direct-v1",
        "source_commit": "a" * 40,
        "results": [_valid_row(name) for name in PUBLIC_CONFIGURATIONS],
    }


def valid_catalog_payload() -> dict:
    payload = valid_server_payload()
    payload["evidence_level"] = "local_contract"
    payload["actual_isaac_sim"] = ""
    payload["actual_isaac_lab"] = ""
    payload["results"] = [_valid_row(name, server=False) for name in PUBLIC_CONFIGURATIONS]
    return payload


def _row(payload: dict, name: str) -> dict:
    return next(row for row in payload["results"] if row["configuration"] == name)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    return path


def test_valid_server_artifact_passes():
    result = validate_qualification_payload(valid_server_payload(), expected_topology=EXPECTED_TOPOLOGY)

    assert result == {
        "qualification_gate": "server_pass",
        "evidence_level": "server_isaac_smoke",
        "configuration_count": 8,
        "passed_configurations": list(PUBLIC_CONFIGURATIONS),
        "actual_versions": {"isaac_sim": "5.0", "isaac_lab": "2.2.1"},
        "warnings": [],
    }


def test_valid_catalog_only_artifact_has_distinct_local_gate():
    result = validate_qualification_payload(
        valid_catalog_payload(), catalog_only=True, expected_topology=EXPECTED_TOPOLOGY
    )

    assert result["qualification_gate"] == "local_contract_pass"
    assert result["evidence_level"] == "local_contract"
    assert result["actual_versions"] == {"isaac_sim": "", "isaac_lab": ""}


def test_catalog_only_artifact_does_not_require_runtime_provenance():
    payload = valid_catalog_payload()
    del payload["runtime_provenance"]

    result = validate_qualification_payload(
        payload, catalog_only=True, expected_topology=EXPECTED_TOPOLOGY
    )

    assert result["qualification_gate"] == "local_contract_pass"


def test_server_artifact_requires_runtime_provenance():
    payload = valid_server_payload()
    del payload["runtime_provenance"]

    with pytest.raises(ValueError, match="runtime_provenance_missing"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("isaac_sim_distribution", "6.0.0.0"),
        ("isaac_lab_distribution", ""),
        ("isaac_lab_repo_commit", "ABC"),
        ("isaac_lab_repo_tag", "v2.3.0"),
    ),
)
def test_server_artifact_rejects_invalid_runtime_provenance(
    field: str, value: object
):
    payload = valid_server_payload()
    payload["runtime_provenance"][field] = value

    with pytest.raises(ValueError, match="runtime_provenance_invalid"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


def test_server_artifact_can_be_bound_to_external_source_and_isaaclab_commits():
    payload = valid_server_payload()

    result = validate_qualification_payload(
        payload,
        expected_topology=EXPECTED_TOPOLOGY,
        expected_source_commit="a" * 40,
        expected_isaaclab_repo_commit="c" * 40,
        expected_isaaclab_repo_tag="v2.2.1",
    )

    assert result["qualification_gate"] == "server_pass"


@pytest.mark.parametrize(
    ("argument", "value", "reason"),
    (
        ("expected_source_commit", "b" * 40, "source_commit_mismatch"),
        (
            "expected_isaaclab_repo_commit",
            "d" * 40,
            "isaaclab_repo_commit_mismatch",
        ),
        (
            "expected_isaaclab_repo_tag",
            "v2.3.0",
            "isaaclab_repo_tag_mismatch",
        ),
    ),
)
def test_server_artifact_rejects_external_commit_binding_mismatch(
    argument: str, value: str, reason: str
):
    payload = valid_server_payload()

    with pytest.raises(ValueError, match=reason):
        validate_qualification_payload(
            payload,
            expected_topology=EXPECTED_TOPOLOGY,
            **{argument: value},
        )


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_configuration_set_mismatch_is_rejected(mutation: str):
    payload = valid_server_payload()
    if mutation == "missing":
        payload["results"].pop()
    else:
        extra = deepcopy(payload["results"][-1])
        extra["configuration"] = "heavy_duty"
        payload["results"].append(extra)

    with pytest.raises(ValueError, match="configuration_set_mismatch"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


def test_duplicate_configuration_is_rejected_before_set_or_count_checks():
    payload = valid_server_payload()
    payload["results"].append(deepcopy(payload["results"][0]))

    with pytest.raises(ValueError, match="duplicate_configuration"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("thruster_count", 5, "thruster_count_mismatch"),
        ("control_channels", ["depth", "roll", "pitch", "yaw"], "control_channels_mismatch"),
        ("control_mask", [1, 1, 0, 1], "control_mask_mismatch"),
        ("declared_control_rank", 3, "declared_control_rank_mismatch"),
    ),
)
def test_wrong_topology_field_is_rejected(field: str, value: object, reason: str):
    payload = valid_server_payload()
    _row(payload, "base")[field] = value

    with pytest.raises(ValueError, match=reason):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


def test_boolean_control_mask_cannot_impersonate_integer_topology():
    payload = valid_server_payload()
    _row(payload, "base")["control_mask"] = [True, True, True, True]

    with pytest.raises(ValueError, match="control_mask_mismatch"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("control_mask", [1, 1, 1, 1], "control_mask_mismatch"),
        ("declared_control_rank", 4, "declared_control_rank_mismatch"),
    ),
)
def test_uuv4_yaw_underactuation_cannot_be_promoted(field: str, value: object, reason: str):
    payload = valid_server_payload()
    _row(payload, "uuv4")[field] = value

    with pytest.raises(ValueError, match=reason):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(("name", "steps"), (("base", 63), ("uuv6", 7)))
def test_insufficient_steps_are_rejected(name: str, steps: int):
    payload = valid_server_payload()
    _row(payload, name)["steps_completed"] = steps

    with pytest.raises(ValueError, match="insufficient_steps"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("field", "reason"),
    (("environment_created", "environment_not_created"), ("reset_passed", "reset_failed")),
)
def test_server_runtime_failure_is_rejected(field: str, reason: str):
    payload = valid_server_payload()
    _row(payload, "asymmetric")[field] = False

    with pytest.raises(ValueError, match=reason):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_control_is_rejected(bad_value: float):
    payload = valid_server_payload()
    _row(payload, "base")["motor_max"] = bad_value

    with pytest.raises(ValueError, match="nonfinite_control"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize("field", ["action_min", "action_max", "motor_min", "motor_max"])
def test_control_beyond_tolerance_is_rejected(field: str):
    payload = valid_server_payload()
    _row(payload, "base")[field] = -1.000002 if field.endswith("min") else 1.000002

    with pytest.raises(ValueError, match="control_out_of_bounds"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize("prefix", ["action", "motor"])
def test_inverted_control_extrema_are_rejected(prefix: str):
    payload = valid_server_payload()
    _row(payload, "base")[f"{prefix}_min"] = 0.75
    _row(payload, "base")[f"{prefix}_max"] = -0.75

    with pytest.raises(ValueError, match="control_range_inverted"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


def test_motor_dimension_mismatch_is_rejected():
    payload = valid_server_payload()
    _row(payload, "uuv6")["motor_vector_length"] = 8

    with pytest.raises(ValueError, match="motor_dimension_mismatch"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("nonfinite_count", "nonfinite_count_nonzero"),
        ("dimension_mismatch_count", "dimension_mismatch_count_nonzero"),
    ),
)
def test_nonzero_failure_count_is_rejected(field: str, reason: str):
    payload = valid_server_payload()
    _row(payload, "uuv6_angled")[field] = 1

    with pytest.raises(ValueError, match=reason):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("status", "fail", "row_status_failed"),
        ("reason_codes", ["step_exception"], "row_reason_codes_present"),
    ),
)
def test_row_failure_status_or_reason_codes_are_rejected(field: str, value: object, reason: str):
    payload = valid_server_payload()
    _row(payload, "long_body")[field] = value

    with pytest.raises(ValueError, match=reason):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


def test_local_evidence_cannot_substitute_for_server_evidence():
    with pytest.raises(ValueError, match="server_evidence_required"):
        validate_qualification_payload(valid_catalog_payload(), expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize("field", ["actual_isaac_sim", "actual_isaac_lab"])
def test_server_artifact_requires_actual_versions(field: str):
    payload = valid_server_payload()
    payload[field] = ""

    with pytest.raises(ValueError, match="actual_version_missing"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize("field", ["expected_isaac_sim", "expected_isaac_lab"])
def test_artifact_requires_expected_versions(field: str):
    payload = valid_server_payload()
    payload[field] = ""

    with pytest.raises(ValueError, match="expected_version_missing"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("expected_field", "bad_version"),
    (("expected_isaac_sim", "6.0"), ("expected_isaac_lab", "3.0")),
)
def test_artifact_expected_versions_are_pinned_to_server_baseline(
    expected_field: str, bad_version: str
):
    payload = valid_server_payload()
    payload[expected_field] = bad_version
    if expected_field == "expected_isaac_sim":
        payload["actual_isaac_sim"] = bad_version
    else:
        payload["actual_isaac_lab"] = bad_version

    with pytest.raises(ValueError, match="expected_version_mismatch"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("actual_field", "bad_version"),
    (("actual_isaac_sim", "6.0"), ("actual_isaac_lab", "3.0")),
)
def test_server_actual_versions_must_match_expected(actual_field: str, bad_version: str):
    payload = valid_server_payload()
    payload[actual_field] = bad_version

    with pytest.raises(ValueError, match="actual_version_mismatch"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("schema_version", "v0", "schema_version_mismatch"),
        ("evidence_level", "unknown", "evidence_level_invalid"),
        ("task_id", "OtherTask-v0", "task_id_mismatch"),
        ("source_commit", "ABC", "source_commit_invalid"),
    ),
)
def test_top_level_contract_mismatch_is_rejected(field: str, value: object, reason: str):
    payload = valid_server_payload()
    payload[field] = value

    with pytest.raises(ValueError, match=reason):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


def test_missing_required_field_is_rejected():
    payload = valid_server_payload()
    del payload["task_id"]

    with pytest.raises(ValueError, match="missing_top_level_fields"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


def test_missing_row_required_field_is_rejected():
    payload = valid_server_payload()
    del _row(payload, "base")["motor_max"]

    with pytest.raises(ValueError, match="missing_row_fields"):
        validate_qualification_payload(payload, expected_topology=EXPECTED_TOPOLOGY)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_strict_json_loader_rejects_nonfinite_constants(local_tmp_path: Path, token: str):
    path = local_tmp_path / "qualification.json"
    path.write_text('{"bad": ' + token + "}", encoding="utf-8")

    with pytest.raises(ValueError, match=f"nonfinite_json_constant:{token}"):
        load_qualification_payload(path)


def test_loader_rejects_malformed_json(local_tmp_path: Path):
    path = local_tmp_path / "qualification.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid_json"):
        load_qualification_payload(path)


def test_loader_rejects_oversize_artifact(local_tmp_path: Path):
    path = local_tmp_path / "qualification.json"
    with path.open("wb") as handle:
        handle.truncate(MAX_ARTIFACT_BYTES + 1)

    with pytest.raises(ValueError, match="artifact_too_large"):
        load_qualification_payload(path)


def test_loader_rejects_non_file_and_missing_paths(local_tmp_path: Path):
    with pytest.raises(ValueError, match="artifact_not_regular_file"):
        load_qualification_payload(local_tmp_path)
    with pytest.raises(ValueError, match="artifact_not_found"):
        load_qualification_payload(local_tmp_path / "missing.json")


def test_file_validator_and_cli_return_pass_for_valid_server_artifact(local_tmp_path: Path, capsys):
    path = _write_json(local_tmp_path / "qualification.json", valid_server_payload())

    result = validate_qualification_file(path, expected_topology=EXPECTED_TOPOLOGY)
    assert result["qualification_gate"] == "server_pass"
    assert main([str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["qualification_gate"] == "server_pass"


def test_cli_binds_artifact_to_external_commit_sidecars(local_tmp_path: Path, capsys):
    artifact = _write_json(
        local_tmp_path / "qualification.json", valid_server_payload()
    )
    source_commit = local_tmp_path / "expected-source-commit.txt"
    isaaclab_commit = local_tmp_path / "isaaclab_repo_commit.txt"
    isaaclab_tag = local_tmp_path / "isaaclab_repo_tag.txt"
    source_commit.write_text("a" * 40 + "\n", encoding="utf-8")
    isaaclab_commit.write_text("c" * 40 + "\n", encoding="utf-8")
    isaaclab_tag.write_text("v2.2.1\n", encoding="utf-8")

    assert main(
        [
            str(artifact),
            "--json",
            "--expected-source-commit-file",
            str(source_commit),
            "--expected-isaaclab-commit-file",
            str(isaaclab_commit),
            "--expected-isaaclab-tag-file",
            str(isaaclab_tag),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["qualification_gate"] == "server_pass"


def test_cli_returns_one_and_stderr_reason_for_local_as_server(local_tmp_path: Path, capsys):
    path = _write_json(local_tmp_path / "qualification.json", valid_catalog_payload())

    assert main([str(path)]) == 1
    assert "ERROR: server_evidence_required" in capsys.readouterr().err


def test_cli_returns_one_for_textual_nan(local_tmp_path: Path, capsys):
    path = local_tmp_path / "qualification.json"
    path.write_text('{"bad": NaN}', encoding="utf-8")

    assert main([str(path)]) == 1
    assert "nonfinite_json_constant:NaN" in capsys.readouterr().err


def test_cli_json_output_is_byte_identical_for_same_artifact(local_tmp_path: Path, capsys):
    path = _write_json(local_tmp_path / "qualification.json", valid_server_payload())

    assert main([str(path), "--json"]) == 0
    first = capsys.readouterr()
    assert main([str(path), "--json"]) == 0
    second = capsys.readouterr()

    assert first.out.encode("utf-8") == second.out.encode("utf-8")
    assert first.err == second.err == ""
