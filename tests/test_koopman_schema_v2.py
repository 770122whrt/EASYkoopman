"""Contract tests for the pure-Python Koopman transition schema v2."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS, qualification_record
from koopman.schema_v2 import (
    KOOPMAN_EPISODE_MANIFEST_V1,
    KOOPMAN_TRANSITION_SCHEMA_V2,
    KoopmanEpisodeLoggerV2,
    build_local_transition_v2,
    load_episode_jsonl_v2,
    validate_episode_artifact_v2,
    validate_episode_v2,
    validate_transition_v2,
)
from workflows.validate_koopman_v2 import main as validate_main


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


def _oracle_context(thruster_count: int) -> dict:
    values = {
        "fluid_velocity_world_3": [0.1, -0.2, 0.05],
        "water_density_kg_m3": 1028.0,
        "dynamic_viscosity_pa_s": 0.00108,
        "drag_multiplier": 1.0,
        "thruster_efficiency_n": [1.0] * thruster_count,
    }
    return {
        "available": True,
        "method": "runtime_cache",
        "method_version": "1",
        "source_kind": "simulator_ground_truth",
        "source_signals": [
            "fluid_velocity_world_3",
            "water_density_kg_m3",
            "dynamic_viscosity_pa_s",
            "drag_multiplier",
            "thruster_efficiency_n",
        ],
        "values": values,
        "units": {
            "fluid_velocity_world_3": "m/s",
            "water_density_kg_m3": "kg/m^3",
            "dynamic_viscosity_pa_s": "Pa*s",
            "drag_multiplier": "dimensionless",
            "thruster_efficiency_n": "dimensionless",
        },
        "frames": {
            "fluid_velocity_world_3": "world",
            "water_density_kg_m3": "scalar",
            "dynamic_viscosity_pa_s": "scalar",
            "drag_multiplier": "scalar",
            "thruster_efficiency_n": "per_thruster",
        },
        "value_provenance": {
            key: "same_step_runtime_cache" for key in values
        },
    }


def _unavailable_estimated_context() -> dict:
    return {
        "available": False,
        "method": "",
        "method_version": "",
        "source_kind": "unavailable",
        "source_signals": [],
        "values": {},
        "units": {},
        "frames": {},
        "value_provenance": {},
    }


def valid_transition(configuration: str = "base", **overrides) -> dict:
    topology = qualification_record(configuration)
    thruster_count = topology["thruster_count"]
    pwm = [0.1 * ((index % 3) - 1) for index in range(thruster_count)]
    pwm.extend([0.0] * (8 - thruster_count))
    virtual_control = [0.2, -0.1, 0.0 if configuration.startswith("uuv4") else 0.3, -0.4]
    payload = {
        "schema_version": "easyuuv-koopman-transition-v2",
        "state_11": [0.0, 0.1, 0.2, 0.0, 0.0, 0.0, 1.0, 0.01, 0.02, 0.03, 0.04],
        "reference_5": [1.5, 1.0, 0.0, 0.0, 0.0],
        "raw_action_4": [0.2, -0.1, 0.75, -0.4],
        "virtual_control_4": virtual_control,
        "motor_pwm_padded_8": pwm,
        "thruster_mask_8": [1] * thruster_count + [0] * (8 - thruster_count),
        "applied_wrench_6": [0.5, -0.25, 1.5, 0.1, -0.2, 0.05],
        "platform_context": {
            "configuration": configuration,
            "thruster_count": thruster_count,
            "control_channels": list(topology["control_channels"]),
            "control_mask": list(topology["control_mask"]),
            "allocation_mode": topology["allocation_mode"],
            "declared_control_rank": topology["declared_control_rank"],
            "mass_kg": 22.701,
            "inertia_diagonal_kg_m2": [0.37, 0.97, 1.19],
            "com_to_cob_offset_m": [0.0, 0.0, 0.01],
            "volume_m3": 0.023,
            "drag_multiplier": 1.0,
            "thruster_dynamics_time_constant_s": 0.05,
        },
        "environment_context_oracle": _oracle_context(thruster_count),
        "environment_context_estimated": _unavailable_estimated_context(),
        "next_state_11": [0.01, 0.11, 0.21, 0.0, 0.0, 0.0, 1.0, 0.02, 0.03, 0.04, 0.05],
        "episode_provenance": {
            "configuration": configuration,
            "scenario": "phase7-contract",
            "episode_id": f"contract-{configuration}-001",
            "step_index": 0,
            "seed": 7,
            "simulation_time_s": 0.0,
            "control_dt_s": 0.02,
            "task_id": "EasyUUV-Direct-v1",
            "controller_mode": "legacy/Ssurface",
            "source_commit": "a" * 40,
            "evidence_level": "local_contract",
        },
    }
    payload.update(overrides)
    return payload


def assert_reason(payload: dict, reason: str) -> None:
    with pytest.raises(ValueError, match=rf"^{reason}(?::|$)"):
        validate_transition_v2(payload)


@pytest.fixture
def local_tmp_path() -> Path:
    scratch_root = Path(__file__).resolve().parents[1] / ".pytest-tmp"
    scratch_root.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="koopman-schema-v2-", dir=scratch_root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def valid_episode(configuration: str = "base", count: int = 3) -> list[dict]:
    rows: list[dict] = []
    state = valid_transition(configuration)["state_11"]
    for step in range(count):
        next_state = list(state)
        next_state[0] = float(state[0]) + 0.01
        next_state[1] = float(state[1]) + 0.005
        row = valid_transition(configuration)
        row["state_11"] = list(state)
        row["next_state_11"] = next_state
        row["episode_provenance"]["step_index"] = step
        row["episode_provenance"]["simulation_time_s"] = step * 0.02
        rows.append(row)
        state = next_state
    return rows


@pytest.mark.parametrize("configuration", PUBLIC_CONFIGURATIONS)
def test_exact_schema_v2_transition_is_valid(configuration: str):
    assert tuple(SUPPORTED_EMBODIMENTS) == PUBLIC_CONFIGURATIONS
    payload = valid_transition(configuration)
    before = deepcopy(payload)

    validate_transition_v2(payload)

    assert payload == before
    assert payload["schema_version"] == KOOPMAN_TRANSITION_SCHEMA_V2


def test_builder_returns_fresh_local_only_transition():
    source = valid_transition()

    built = build_local_transition_v2(**source)
    built["state_11"][0] = 99.0

    assert source["state_11"][0] == 0.0
    assert built["episode_provenance"]["evidence_level"] == "local_contract"


@pytest.mark.parametrize("bad_version", [2, "2", "v2", "easyuuv-koopman-transition-v2.1"])
def test_transition_rejects_ambiguous_or_future_version(bad_version):
    payload = valid_transition()
    payload["schema_version"] = bad_version
    assert_reason(payload, "schema_version_mismatch")


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_transition_rejects_missing_and_extra_top_level_fields(change: str):
    payload = valid_transition()
    if change == "missing":
        del payload["reference_5"]
    else:
        payload["pwm_8d"] = [0.0] * 8
    assert_reason(payload, "field_set_mismatch")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("state_11", [0.0] * 10, "shape_invalid"),
        ("reference_5", [0.0] * 4, "shape_invalid"),
        ("raw_action_4", [0.0] * 3, "shape_invalid"),
        ("virtual_control_4", [0.0] * 5, "shape_invalid"),
        ("motor_pwm_padded_8", [0.0] * 7, "shape_invalid"),
        ("thruster_mask_8", [1] * 7, "shape_invalid"),
        ("applied_wrench_6", [0.0] * 5, "shape_invalid"),
        ("next_state_11", [0.0] * 12, "shape_invalid"),
        ("state_11", [0.0] * 10 + [float("nan")], "nonfinite_value"),
        ("applied_wrench_6", [0.0] * 5 + [float("inf")], "nonfinite_value"),
        ("raw_action_4", [0.0, 0.0, 0.0, 1.01], "control_out_of_bounds"),
        ("virtual_control_4", [-1.01, 0.0, 0.0, 0.0], "control_out_of_bounds"),
        ("motor_pwm_padded_8", [0.0] * 7 + [1.01], "pwm_out_of_bounds"),
        ("thruster_mask_8", [True] + [1] * 7, "type_invalid"),
        ("thruster_mask_8", [1, 1, 2, 1, 1, 1, 1, 1], "mask_mismatch"),
    ],
)
def test_transition_rejects_vector_shape_type_finite_and_range_mutations(
    field: str, value, reason: str
):
    payload = valid_transition()
    payload[field] = value
    assert_reason(payload, reason)


def test_transition_rejects_unknown_or_internal_configuration():
    for configuration in ("unknown", "heavy_duty"):
        payload = valid_transition()
        payload["platform_context"]["configuration"] = configuration
        payload["episode_provenance"]["configuration"] = configuration
        assert_reason(payload, "configuration_unknown")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("thruster_count", 6),
        ("control_channels", ["roll", "pitch", "depth", "yaw"]),
        ("control_mask", [1, 1, 0, 1]),
        ("allocation_mode", "pinv"),
        ("declared_control_rank", 3),
    ],
)
def test_platform_topology_must_match_canonical_catalog(field: str, value):
    payload = valid_transition("base")
    payload["platform_context"][field] = value
    assert_reason(payload, "topology_mismatch")


def test_mask_padding_and_underactuated_yaw_are_explicit():
    payload = valid_transition("uuv6")
    payload["motor_pwm_padded_8"][7] = 0.25
    assert_reason(payload, "padding_nonzero")

    payload = valid_transition("uuv6")
    payload["thruster_mask_8"] = [1] * 8
    assert_reason(payload, "mask_mismatch")

    payload = valid_transition("uuv4")
    assert payload["raw_action_4"][2] != 0.0
    payload["virtual_control_4"][2] = payload["raw_action_4"][2]
    assert_reason(payload, "underactuated_yaw_nonzero")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("mass_kg", 0.0, "context_value_invalid"),
        ("inertia_diagonal_kg_m2", [0.37, 0.97], "shape_invalid"),
        ("com_to_cob_offset_m", [0.0, float("nan"), 0.01], "nonfinite_value"),
        ("volume_m3", -0.01, "context_value_invalid"),
        ("drag_multiplier", 0.0, "context_value_invalid"),
        ("thruster_dynamics_time_constant_s", True, "type_invalid"),
    ],
)
def test_platform_context_rejects_invalid_dynamics(field: str, value, reason: str):
    payload = valid_transition()
    payload["platform_context"][field] = value
    assert_reason(payload, reason)


def test_nested_objects_use_exact_field_sets():
    for object_name in (
        "platform_context",
        "environment_context_oracle",
        "environment_context_estimated",
        "episode_provenance",
    ):
        payload = valid_transition()
        payload[object_name]["unexpected"] = "drift"
        assert_reason(payload, "field_set_mismatch")


def test_oracle_requires_units_frames_and_value_provenance():
    for namespace in ("units", "frames", "value_provenance"):
        payload = valid_transition()
        del payload["environment_context_oracle"][namespace]["fluid_velocity_world_3"]
        assert_reason(payload, "context_provenance_invalid")

    payload = valid_transition()
    payload["environment_context_oracle"]["frames"]["fluid_velocity_world_3"] = "body"
    assert_reason(payload, "context_provenance_invalid")


def test_estimated_unavailable_is_valid_and_must_be_empty():
    validate_transition_v2(valid_transition())

    payload = valid_transition()
    payload["environment_context_estimated"]["values"] = {"current_speed": 0.1}
    assert_reason(payload, "context_unavailable_invalid")


def test_available_estimate_requires_deployable_method_version_and_signals():
    payload = valid_transition()
    payload["environment_context_estimated"] = {
        "available": True,
        "method": "observer",
        "method_version": "1",
        "source_kind": "deployable_observation",
        "source_signals": ["imu", "depth"],
        "values": {"current_speed_m_s": 0.1},
        "units": {"current_speed_m_s": "m/s"},
        "frames": {"current_speed_m_s": "body"},
        "value_provenance": {"current_speed_m_s": "observer_output"},
    }
    validate_transition_v2(payload)

    for field, value in (
        ("method", ""),
        ("method_version", ""),
        ("source_signals", []),
    ):
        mutated = deepcopy(payload)
        mutated["environment_context_estimated"][field] = value
        assert_reason(mutated, "context_provenance_invalid")


def test_oracle_cannot_alias_or_masquerade_as_estimated_context():
    payload = valid_transition()
    payload["environment_context_estimated"] = payload["environment_context_oracle"]
    assert_reason(payload, "oracle_as_estimate")

    payload = valid_transition()
    payload["environment_context_estimated"] = deepcopy(
        payload["environment_context_oracle"]
    )
    payload["environment_context_estimated"]["source_kind"] = "deployable_observation"
    assert_reason(payload, "oracle_as_estimate")

    payload = valid_transition()
    payload["environment_context_estimated"] = deepcopy(
        payload["environment_context_oracle"]
    )
    assert_reason(payload, "oracle_as_estimate")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("configuration", "uuv6", "topology_mismatch"),
        ("step_index", True, "type_invalid"),
        ("seed", False, "type_invalid"),
        ("simulation_time_s", float("nan"), "nonfinite_value"),
        ("control_dt_s", 0.0, "context_value_invalid"),
        ("source_commit", "ABC", "source_commit_invalid"),
        ("evidence_level", "server_pass", "evidence_level_invalid"),
        ("task_id", "", "type_invalid"),
    ],
)
def test_episode_provenance_is_unambiguous(field: str, value, reason: str):
    payload = valid_transition()
    payload["episode_provenance"][field] = value
    assert_reason(payload, reason)


def test_local_builder_rejects_server_evidence_self_assertion():
    payload = valid_transition()
    payload["episode_provenance"]["evidence_level"] = "server_isaac_smoke"

    with pytest.raises(ValueError, match=r"^local_evidence_required(?::|$)"):
        build_local_transition_v2(**payload)


def test_import_contract_does_not_load_runtime_frameworks(monkeypatch):
    for module_name in (
        "koopman.schema_v2",
        "easyuuv_nc.embodiments",
        "easyuuv_nc",
    ):
        sys.modules.pop(module_name, None)
    before = set(sys.modules)

    imported = importlib.import_module("koopman.schema_v2")
    loaded = set(sys.modules) - before

    assert imported.KOOPMAN_TRANSITION_SCHEMA_V2 == "easyuuv-koopman-transition-v2"
    assert not any(
        name == blocked or name.startswith(f"{blocked}.")
        for name in loaded
        for blocked in ("torch", "gymnasium", "omni", "easyuuv_nc.env")
    )


def test_contiguous_episode_is_valid_without_mutation():
    rows = valid_episode()
    before = deepcopy(rows)

    summary = validate_episode_v2(rows)

    assert rows == before
    assert summary["record_count"] == 3
    assert summary["first_step_index"] == 0
    assert summary["last_step_index"] == 2


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda rows: rows.__setitem__(1, deepcopy(rows[0])), "step_duplicate"),
        (
            lambda rows: rows[1]["episode_provenance"].__setitem__("step_index", -1),
            "step_reordered",
        ),
        (
            lambda rows: rows[1]["episode_provenance"].__setitem__("step_index", 2),
            "step_discontinuity",
        ),
        (
            lambda rows: rows[1]["episode_provenance"].__setitem__(
                "simulation_time_s", 0.021
            ),
            "time_discontinuity",
        ),
        (
            lambda rows: rows[1]["episode_provenance"].__setitem__(
                "controller_mode", "different-controller"
            ),
            "episode_invariant_drift",
        ),
        (
            lambda rows: rows[1]["state_11"].__setitem__(0, 99.0),
            "state_transition_discontinuity",
        ),
        (
            lambda rows: rows[1]["platform_context"].__setitem__("mass_kg", 25.0),
            "platform_context_drift",
        ),
    ],
)
def test_episode_rejects_discontinuity_and_invariant_drift(mutate, reason: str):
    rows = valid_episode()
    mutate(rows)

    with pytest.raises(ValueError, match=rf"^{reason}(?::|$)"):
        validate_episode_v2(rows)


def test_numeric_tolerance_cannot_hide_a_missing_step():
    rows = valid_episode()
    rows[1]["episode_provenance"]["step_index"] = 2

    with pytest.raises(ValueError, match=r"^step_discontinuity(?::|$)"):
        validate_episode_v2(rows, numeric_tolerance=100.0)


def test_episode_requires_two_or_more_rows():
    with pytest.raises(ValueError, match=r"^episode_too_short(?::|$)"):
        validate_episode_v2(valid_episode(count=1))


def test_bounded_loader_rejects_duplicate_keys_constants_utf8_and_partials(
    local_tmp_path: Path,
):
    duplicate = local_tmp_path / "duplicate.jsonl"
    duplicate.write_text('{"x":1,"x":2}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"^duplicate_json_key(?::|$)"):
        load_episode_jsonl_v2(duplicate)

    nonfinite = local_tmp_path / "nonfinite.jsonl"
    nonfinite.write_text('{"x":NaN}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"^nonfinite_json_constant(?::|$)"):
        load_episode_jsonl_v2(nonfinite)

    invalid_utf8 = local_tmp_path / "invalid.jsonl"
    invalid_utf8.write_bytes(b"\xff\xfe\n")
    with pytest.raises(ValueError, match=r"^artifact_not_utf8(?::|$)"):
        load_episode_jsonl_v2(invalid_utf8)

    partial = local_tmp_path / "episode.jsonl.part"
    partial.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"^partial_artifact_refused(?::|$)"):
        load_episode_jsonl_v2(partial)


def test_bounded_loader_rejects_oversize_file_line_and_line_count(
    local_tmp_path: Path,
):
    path = local_tmp_path / "oversize.jsonl"
    path.write_bytes(b"x" * 101)
    with pytest.raises(ValueError, match=r"^artifact_too_large(?::|$)"):
        load_episode_jsonl_v2(path, max_bytes=100)

    path.write_text("{}" * 30 + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"^line_too_large(?::|$)"):
        load_episode_jsonl_v2(path, max_bytes=1000, max_line_bytes=50)

    path.write_text("{}\n{}\n{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"^line_count_exceeded(?::|$)"):
        load_episode_jsonl_v2(path, max_lines=2)


def test_logger_validates_before_write_and_failed_finalize_keeps_part(
    local_tmp_path: Path,
):
    jsonl_path = local_tmp_path / "episode.jsonl"
    logger = KoopmanEpisodeLoggerV2(jsonl_path)
    first = valid_episode(count=1)[0]
    logger.write(first)
    part_bytes = logger.part_path.read_bytes()

    invalid = deepcopy(first)
    invalid["schema_version"] = "v2"
    with pytest.raises(ValueError, match=r"^schema_version_mismatch(?::|$)"):
        logger.write(invalid)
    assert logger.part_path.read_bytes() == part_bytes

    with pytest.raises(ValueError, match=r"^episode_too_short(?::|$)"):
        logger.finalize()
    assert logger.part_path.is_file()
    assert not jsonl_path.exists()
    assert not logger.manifest_path.exists()
    logger.close()


def test_logger_round_trip_is_deterministic_and_manifest_hashes_exact_bytes(
    local_tmp_path: Path,
):
    rows = valid_episode()
    outputs: list[tuple[bytes, dict]] = []
    for directory_name in ("first", "second"):
        path = local_tmp_path / directory_name / "episode.jsonl"
        path.parent.mkdir()
        logger = KoopmanEpisodeLoggerV2(path)
        for row in rows:
            logger.write(dict(reversed(list(row.items()))))
        manifest = logger.finalize()
        outputs.append((path.read_bytes(), manifest))

        assert not logger.part_path.exists()
        assert logger.manifest_path.is_file()
        assert manifest["manifest_version"] == KOOPMAN_EPISODE_MANIFEST_V1
        assert manifest["transition_schema_version"] == KOOPMAN_TRANSITION_SCHEMA_V2
        assert manifest["transition_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert manifest["record_count"] == len(rows)
        assert manifest["evidence_level"] == "local_contract"
        assert load_episode_jsonl_v2(path) == rows
        result = validate_episode_artifact_v2(path, logger.manifest_path)
        assert result["validation_gate"] == "schema_v2_episode_valid"

    assert outputs[0][0] == outputs[1][0]
    comparable_first = dict(outputs[0][1])
    comparable_second = dict(outputs[1][1])
    assert comparable_first == comparable_second


def test_manifest_hash_mismatch_is_distinct(local_tmp_path: Path):
    path = local_tmp_path / "episode.jsonl"
    logger = KoopmanEpisodeLoggerV2(path)
    for row in valid_episode():
        logger.write(row)
    manifest = logger.finalize()
    manifest["transition_sha256"] = "0" * 64
    logger.manifest_path.write_text(
        json.dumps(manifest, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"^manifest_hash_mismatch(?::|$)"):
        validate_episode_artifact_v2(path, logger.manifest_path)


def test_existing_canonical_pair_is_never_reused_or_replaced(local_tmp_path: Path):
    path = local_tmp_path / "episode.jsonl"
    logger = KoopmanEpisodeLoggerV2(path)
    for row in valid_episode():
        logger.write(row)
    logger.finalize()
    original_jsonl = path.read_bytes()
    original_manifest = logger.manifest_path.read_bytes()

    with pytest.raises(ValueError, match=r"^artifact_exists(?::|$)"):
        KoopmanEpisodeLoggerV2(path)

    assert path.read_bytes() == original_jsonl
    assert logger.manifest_path.read_bytes() == original_manifest


def test_validator_cli_accepts_only_exact_pair_and_reports_no_server_pass(
    local_tmp_path: Path, capsys
):
    path = local_tmp_path / "episode.jsonl"
    logger = KoopmanEpisodeLoggerV2(path)
    for row in valid_episode():
        logger.write(row)
    logger.finalize()

    exit_code = validate_main(
        ["--jsonl", str(path), "--manifest", str(logger.manifest_path), "--json"]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["validation_gate"] == "schema_v2_episode_valid"
    assert output["evidence_level"] == "local_contract"
    assert "server_pass" not in json.dumps(output)

    logger.manifest_path.write_text("{}\n", encoding="utf-8")
    assert validate_main(
        ["--jsonl", str(path), "--manifest", str(logger.manifest_path), "--json"]
    ) == 1
    assert "ERROR:" in capsys.readouterr().err


def test_validator_cli_has_no_evidence_upgrade_flag(capsys):
    with pytest.raises(SystemExit) as caught:
        validate_main(["--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    assert "--server" not in help_text
    assert "--evidence-level" not in help_text
