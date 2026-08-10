"""Isaac-free contracts for the Phase 6 qualification runner and merger."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile

import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS, qualification_record
from workflows.easyuuv_v2_qualification_artifact import (
    EXPECTED_ISAAC_LAB_VERSION,
    EXPECTED_ISAAC_SIM_VERSION,
    EXPECTED_TASK_ID,
    QUALIFICATION_SCHEMA_VERSION,
    SERVER_EVIDENCE_LEVEL,
    validate_qualification_payload,
)
from workflows.merge_easyuuv_v2_qualification import merge_qualification_results
from workflows.qualify_easyuuv_v2 import (
    DEFAULT_RESULT_ROOT,
    build_runtime_provenance,
    build_argument_parser,
    deterministic_excitation,
    normalize_isaac_sim_version,
    resolve_output_path,
    summarize_actual_telemetry,
)


@pytest.fixture
def local_tmp_path() -> Path:
    """Keep scratch files under the repository on restricted Windows runners."""
    scratch_root = Path(__file__).resolve().parents[1] / ".pytest-tmp"
    scratch_root.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="qualification-runner-", dir=scratch_root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _row(configuration: str) -> dict:
    topology = qualification_record(configuration)
    steps = 64 if configuration == "base" else 8
    return {
        "configuration": configuration,
        "thruster_count": topology["thruster_count"],
        "control_channels": list(topology["control_channels"]),
        "control_mask": list(topology["control_mask"]),
        "declared_control_rank": topology["declared_control_rank"],
        "environment_created": True,
        "reset_passed": True,
        "steps_completed": steps,
        "action_min": -0.1,
        "action_max": 0.1,
        "motor_min": -0.25,
        "motor_max": 0.25,
        "motor_vector_length": topology["thruster_count"],
        "nonfinite_count": 0,
        "dimension_mismatch_count": 0,
        "seed": 0,
        "status": "pass",
        "reason_codes": [],
    }


def _single_row_payload(
    configuration: str,
    *,
    actual_isaac_sim: str = EXPECTED_ISAAC_SIM_VERSION,
    actual_isaac_lab: str = EXPECTED_ISAAC_LAB_VERSION,
    source_commit: str = "a" * 40,
) -> dict:
    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "evidence_level": SERVER_EVIDENCE_LEVEL,
        "expected_isaac_sim": EXPECTED_ISAAC_SIM_VERSION,
        "expected_isaac_lab": EXPECTED_ISAAC_LAB_VERSION,
        "actual_isaac_sim": actual_isaac_sim,
        "actual_isaac_lab": actual_isaac_lab,
        "task_id": EXPECTED_TASK_ID,
        "source_commit": source_commit,
        "results": [_row(configuration)],
    }


def _write_row(path: Path, configuration: str, **overrides: object) -> Path:
    payload = _single_row_payload(configuration)
    payload.update(overrides)
    path.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_all_rows(directory: Path) -> list[Path]:
    return [
        _write_row(directory / f"{configuration}.json", configuration)
        for configuration in SUPPORTED_EMBODIMENTS
    ]


def test_runner_help_contract_is_available_without_isaac_imports():
    parser = build_argument_parser()
    help_text = parser.format_help()

    for option in (
        "--task",
        "--configuration",
        "--steps",
        "--seed",
        "--num-envs",
        "--headless",
        "--output-json",
        "--result-root",
    ):
        assert option in help_text
    assert tuple(parser._option_string_actions["--configuration"].choices) == SUPPORTED_EMBODIMENTS


def test_deterministic_excitation_cycles_signed_channels_and_is_bounded():
    values = [deterministic_excitation(step, (1, 1, 1, 1)) for step in range(8)]

    assert values == [
        (0.1, 0.0, 0.0, 0.0),
        (-0.1, 0.0, 0.0, 0.0),
        (0.0, 0.1, 0.0, 0.0),
        (0.0, -0.1, 0.0, 0.0),
        (0.0, 0.0, 0.1, 0.0),
        (0.0, 0.0, -0.1, 0.0),
        (0.0, 0.0, 0.0, 0.1),
        (0.0, 0.0, 0.0, -0.1),
    ]
    assert max(abs(value) for action in values for value in action) <= 0.1


@pytest.mark.parametrize("configuration", ("uuv4", "uuv4_angled"))
def test_underactuated_excitation_never_sets_yaw(configuration: str):
    mask = qualification_record(configuration)["control_mask"]

    values = [deterministic_excitation(step, mask) for step in range(24)]

    assert all(action[2] == 0.0 for action in values)


def test_output_path_defaults_to_repository_result_root():
    resolved = resolve_output_path(DEFAULT_RESULT_ROOT / "rows" / "base.json", DEFAULT_RESULT_ROOT)

    assert resolved == (DEFAULT_RESULT_ROOT / "rows" / "base.json").resolve()


def test_output_path_rejects_escape_from_explicit_result_root(local_tmp_path: Path):
    result_root = local_tmp_path / "allowed"

    with pytest.raises(ValueError, match="output_outside_result_root"):
        resolve_output_path(local_tmp_path / "outside.json", result_root)


def test_output_path_creates_confined_parent(local_tmp_path: Path):
    result_root = local_tmp_path / "allowed"
    output = result_root / "rows" / "base.json"

    resolved = resolve_output_path(output, result_root)

    assert resolved.parent.is_dir()
    assert resolved.is_relative_to(result_root.resolve())


def test_actual_telemetry_is_required():
    with pytest.raises(RuntimeError, match="missing_actual_telemetry"):
        summarize_actual_telemetry(
            pid_value=None,
            motor_values=None,
            expected_motor_length=8,
        )


def test_actual_telemetry_summary_uses_real_values_and_counts_shape_mismatch():
    summary = summarize_actual_telemetry(
        pid_value=[[0.05, -0.1, 0.0, 0.1]],
        motor_values=[[0.25, -0.2, 0.0, 0.1, -0.1, 0.2]],
        expected_motor_length=8,
    )

    assert summary == {
        "action_min": -0.1,
        "action_max": 0.1,
        "motor_min": -0.2,
        "motor_max": 0.25,
        "motor_vector_length": 6,
        "nonfinite_count": 0,
        "dimension_mismatch_count": 1,
    }


def test_runtime_provenance_uses_installed_sim_and_exact_isaaclab_release_tag():
    provenance = build_runtime_provenance(
        isaac_sim_distribution="5.0.0.0",
        isaac_lab_distribution="0.45.9",
        isaac_lab_repo_commit="c" * 40,
        isaac_lab_repo_tag="v2.2.1",
    )

    assert provenance == {
        "actual_isaac_sim": "5.0",
        "actual_isaac_lab": "2.2.1",
        "runtime_provenance": {
            "isaac_sim_distribution": "5.0.0.0",
            "isaac_lab_distribution": "0.45.9",
            "isaac_lab_repo_commit": "c" * 40,
            "isaac_lab_repo_tag": "v2.2.1",
        },
    }


@pytest.mark.parametrize("raw", ("5.0", "5.0.0.0", "5.0.0.0+linux-x86_64"))
def test_isaac_sim_distribution_is_normalized_to_semantic_baseline(raw: str):
    assert normalize_isaac_sim_version(raw) == "5.0"


@pytest.mark.parametrize(
    "bad_tag",
    ("2.2", "release-2.2.1", "v2.2.1-dirty", "v2.3.0", ""),
)
def test_runtime_provenance_rejects_nonbaseline_or_inexact_isaaclab_tag(bad_tag: str):
    with pytest.raises(RuntimeError, match="isaac_lab_release_provenance_invalid"):
        build_runtime_provenance(
            isaac_sim_distribution="5.0.0.0",
            isaac_lab_distribution="0.45.9",
            isaac_lab_repo_commit="c" * 40,
            isaac_lab_repo_tag=bad_tag,
        )


def test_merge_valid_eight_rows_is_deterministic_and_strict(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    output = local_tmp_path / "merged" / "qualification.json"

    first = merge_qualification_results(inputs, output)
    first_bytes = output.read_bytes()
    second = merge_qualification_results(list(reversed(inputs)), output)

    assert first == second
    assert output.read_bytes() == first_bytes
    assert [row["configuration"] for row in first["results"]] == list(SUPPORTED_EMBODIMENTS)
    assert validate_qualification_payload(first)["qualification_gate"] == "server_pass"


def test_merge_rejects_missing_configuration_without_replacing_output(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)[:-1]
    output = local_tmp_path / "qualification.json"
    output.write_text("preserve-me", encoding="utf-8")

    with pytest.raises(ValueError, match="configuration_set_mismatch"):
        merge_qualification_results(inputs, output)

    assert output.read_text(encoding="utf-8") == "preserve-me"


def test_merge_rejects_duplicate_before_set_check(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    duplicate = local_tmp_path / "duplicate-base.json"
    duplicate.write_text(inputs[0].read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate_configuration"):
        merge_qualification_results([*inputs, duplicate], local_tmp_path / "qualification.json")


def test_merge_rejects_extra_configuration(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    extra_payload = deepcopy(_single_row_payload("base"))
    extra_payload["results"][0]["configuration"] = "heavy_duty"
    extra = local_tmp_path / "heavy_duty.json"
    extra.write_text(json.dumps(extra_payload), encoding="utf-8")

    with pytest.raises(ValueError, match="configuration_set_mismatch"):
        merge_qualification_results([*inputs, extra], local_tmp_path / "qualification.json")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("actual_isaac_sim", "5.1", "actual_version_disagreement"),
        ("actual_isaac_lab", "2.3.0", "actual_version_disagreement"),
        ("task_id", "OtherTask-v0", "metadata_disagreement"),
        ("source_commit", "b" * 40, "metadata_disagreement"),
    ),
)
def test_merge_rejects_metadata_disagreement(
    local_tmp_path: Path, field: str, value: str, reason: str
):
    inputs = _write_all_rows(local_tmp_path)
    changed = json.loads(inputs[-1].read_text(encoding="utf-8"))
    changed[field] = value
    inputs[-1].write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(ValueError, match=reason):
        merge_qualification_results(inputs, local_tmp_path / "qualification.json")


def test_merge_rejects_more_than_one_result_per_input(local_tmp_path: Path):
    inputs = _write_all_rows(local_tmp_path)
    payload = json.loads(inputs[0].read_text(encoding="utf-8"))
    payload["results"].append(deepcopy(payload["results"][0]))
    inputs[0].write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="single_result_required"):
        merge_qualification_results(inputs, local_tmp_path / "qualification.json")
