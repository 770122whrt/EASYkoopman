"""Phase 8 pilot policy, external evidence and model-free health contracts."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

from easyuuv_nc.embodiments import qualification_record
from koopman.evidence_v2 import (
    LOCAL_QUALIFICATION_LEVEL,
    PHASE8_EVIDENCE_ENVELOPE_V1,
    PILOT_QUALIFICATION_LEVEL,
    build_local_phase8_envelope,
    validate_phase8_evidence,
)
from koopman.protocol_v2 import (
    PILOT_POLICY_VERSION,
    PUBLIC_CONFIGURATIONS,
    load_pilot_collection_policy,
    validate_pilot_collection_policy,
)
from workflows.audit_koopman_v2_pilot import audit_pilot_collection
from workflows.validate_phase8_evidence import main as validate_phase8_main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "protocols" / "phase8" / "pilot_collection_policy.json"
PHASE8_QUALIFICATIONS = (
    "server_isaac_identification_pilot",
    "server_isaac_identification_dataset",
    "offline_koopman_ood_evaluation",
    "koopman_selection",
    "no_selection",
)
EXPECTED_CONFIGURATIONS = (
    "base",
    "long_body",
    "heavy_moderate",
    "asymmetric",
    "uuv6",
    "uuv6_angled",
    "uuv4",
    "uuv4_angled",
)
EXPECTED_POLICY_FIELDS = {
    "policy_version",
    "experiment_id",
    "transition_schema_version",
    "artifact_origin_level",
    "task_id",
    "controller_mode",
    "runtime_contract",
    "raw_action_abs_max",
    "entries",
}
EXPECTED_ENTRY_FIELDS = {
    "configuration",
    "episode_id",
    "scenario",
    "policy_kind",
    "seed",
    "transition_count",
}
SOURCE_COMMIT = "a" * 40


def _canonical_bytes(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime() -> dict:
    return {
        "actual_isaac_lab": "2.2.1",
        "actual_isaac_sim": "5.0",
        "artifact_origin": "server_isaac_smoke",
        "context_source": "same_step_oracle_snapshot",
        "isaac_lab_release_commit": "0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20",
        "isaac_lab_release_tag": "v2.2.1",
        "isaac_lab_repo_commit": "c91a125c73c8b574878419a9583afc0b63b99f0a",
        "isaac_lab_repo_dirty_files": [
            "source/isaaclab_mimic/setup.py",
            "source/isaaclab_rl/setup.py",
        ],
        "isaac_lab_repo_parent_commit": "0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20",
        "isaac_lab_repo_patch_sha256": "d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079",
        "native_status": 0,
        "semantic_status": "pass",
        "tee_status": 0,
        "wrench_source": "post_actuator_thruster_only",
    }


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
        "source_signals": list(values),
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
        "value_provenance": {key: "same_step_runtime_cache" for key in values},
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


def _action(step: int, policy_kind: str) -> list[float]:
    if policy_kind == "axis_pulse":
        channel = (step // 16) % 4
        sign = 1.0 if (step // 64) % 2 == 0 else -1.0
        return [sign * 0.25 if index == channel else 0.0 for index in range(4)]
    return [
        0.2 * math.sin((step + 1) * (index + 1) * 0.19 + index * 0.7)
        for index in range(4)
    ]


def _row(entry: dict, step: int, state: list[float]) -> dict:
    configuration = entry["configuration"]
    topology = qualification_record(configuration)
    thruster_count = topology["thruster_count"]
    raw = _action(step, entry["policy_kind"])
    virtual = list(raw)
    if configuration.startswith("uuv4"):
        virtual[2] = 0.0
    next_state = list(state)
    next_state[0] += 0.0001 * (step + 1)
    next_state[5] += 0.0002 * virtual[0]
    pwm = [0.05 * ((step + index) % 3 - 1) for index in range(thruster_count)]
    pwm.extend([0.0] * (8 - thruster_count))
    return {
        "schema_version": "easyuuv-koopman-transition-v2",
        "state_11": list(state),
        "reference_5": [1.5, 1.0, 0.0, 0.0, 0.0],
        "raw_action_4": raw,
        "virtual_control_4": virtual,
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
        "next_state_11": next_state,
        "episode_provenance": {
            "configuration": configuration,
            "scenario": entry["scenario"],
            "episode_id": entry["episode_id"],
            "step_index": step,
            "seed": entry["seed"],
            "simulation_time_s": step * 0.02,
            "control_dt_s": 0.02,
            "task_id": "EasyUUV-Direct-v1",
            "controller_mode": "legacy/Ssurface",
            "source_commit": SOURCE_COMMIT,
            "evidence_level": "server_isaac_smoke",
        },
    }


def _write_fixture(root: Path) -> dict:
    root.mkdir()
    (root / "episodes").mkdir()
    (root / "manifests").mkdir()
    (root / "logs").mkdir()
    policy = load_pilot_collection_policy(POLICY_PATH)
    (root / "pilot_collection_policy.json").write_bytes(_canonical_bytes(policy))
    runtime = _runtime()
    for entry in policy["entries"]:
        episode_path = root / "episodes" / f"{entry['episode_id']}.jsonl"
        manifest_path = root / "manifests" / f"{entry['episode_id']}.manifest.json"
        log_path = root / "logs" / f"{entry['episode_id']}.log"
        state = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        rows = []
        for step in range(entry["transition_count"]):
            row = _row(entry, step, state)
            rows.append(row)
            state = list(row["next_state_11"])
        episode_path.write_bytes(b"".join(_canonical_bytes(row) for row in rows))
        platform_hash = hashlib.sha256(
            _canonical_bytes(rows[0]["platform_context"])
        ).hexdigest()
        manifest = {
            "manifest_version": "easyuuv-koopman-episode-manifest-v1",
            "transition_schema_version": "easyuuv-koopman-transition-v2",
            "transition_file": episode_path.name,
            "transition_sha256": _sha256(episode_path),
            "record_count": entry["transition_count"],
            "first_step_index": 0,
            "last_step_index": entry["transition_count"] - 1,
            "first_simulation_time_s": 0.0,
            "last_simulation_time_s": (entry["transition_count"] - 1) * 0.02,
            "episode_invariants": {
                key: rows[0]["episode_provenance"][key]
                for key in sorted(
                    {
                        "configuration",
                        "scenario",
                        "episode_id",
                        "seed",
                        "control_dt_s",
                        "task_id",
                        "controller_mode",
                        "source_commit",
                        "evidence_level",
                    }
                )
            },
            "platform_context_sha256": platform_hash,
            "runtime_provenance": runtime,
            "evidence_level": "server_isaac_smoke",
        }
        manifest_path.write_bytes(_canonical_bytes(manifest))
        log_path.write_text(
            f"episode={entry['episode_id']}\nsemantic_status=pass\n",
            encoding="utf-8",
        )
    return policy


def _rewrite_manifest(root: Path, episode_id: str, mutate) -> None:
    path = root / "manifests" / f"{episode_id}.manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_bytes(_canonical_bytes(payload))


def test_committed_policy_is_exact_precollection_intent_without_model_results():
    policy = load_pilot_collection_policy(POLICY_PATH)
    before = deepcopy(policy)

    validate_pilot_collection_policy(policy)

    assert policy == before
    assert policy["policy_version"] == PILOT_POLICY_VERSION
    assert set(policy) == EXPECTED_POLICY_FIELDS
    assert tuple(PUBLIC_CONFIGURATIONS) == EXPECTED_CONFIGURATIONS
    assert len(policy["entries"]) == 16
    assert all(set(entry) == EXPECTED_ENTRY_FIELDS for entry in policy["entries"])
    assert len({entry["episode_id"] for entry in policy["entries"]}) == 16
    assert {
        (entry["configuration"], entry["policy_kind"], entry["seed"], entry["transition_count"])
        for entry in policy["entries"]
    } == {
        (configuration, policy_kind, seed, 128)
        for configuration in EXPECTED_CONFIGURATIONS
        for policy_kind, seed in (("axis_pulse", 8101), ("bounded_multisine", 8102))
    }
    assert policy["raw_action_abs_max"] == 0.25
    forbidden = ("model", "fit", "feature", "horizon", "rank", "condition", "prediction", "rollout", "error", "sha256")
    assert not any(token in json.dumps(policy).lower() for token in forbidden)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.pop("task_id"),
        lambda value: value.__setitem__("unexpected", True),
        lambda value: value["entries"].append(deepcopy(value["entries"][0])),
        lambda value: value["entries"].pop(),
        lambda value: value["entries"][0].__setitem__("transition_count", 127),
        lambda value: value["entries"][0].__setitem__("seed", 9999),
        lambda value: value["entries"][0].__setitem__("model_hash", "0" * 64),
        lambda value: value.__setitem__("raw_action_abs_max", float("nan")),
    ],
)
def test_policy_rejects_missing_extra_duplicate_nonfinite_and_postcollection_fields(mutate):
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    with pytest.raises(ValueError, match=r"^pilot_policy_invalid(?::|$)"):
        validate_pilot_collection_policy(payload)


def test_phase7_transition_evidence_enum_remains_frozen():
    from koopman.schema_v2 import validate_transition_v2

    policy = load_pilot_collection_policy(POLICY_PATH)
    row = _row(policy["entries"][0], 0, [0.0, 1.0] + [0.0] * 9)
    for qualification in PHASE8_QUALIFICATIONS:
        mutated = deepcopy(row)
        mutated["episode_provenance"]["evidence_level"] = qualification
        with pytest.raises(ValueError, match=r"^evidence_level_invalid(?::|$)"):
            validate_transition_v2(mutated)


def test_local_builder_cannot_self_promote_and_external_qualification_is_exact(tmp_path: Path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("local contract\n", encoding="utf-8")
    envelope_path = tmp_path / "local_envelope.json"
    envelope = build_local_phase8_envelope(
        envelope_path,
        experiment_id="phase8-local-contract-test",
        source_commit=SOURCE_COMMIT,
        protocol_sha256="1" * 64,
        runtime_provenance={"artifact_origin": "local_contract"},
        referenced_paths=[artifact],
    )

    assert envelope["envelope_version"] == PHASE8_EVIDENCE_ENVELOPE_V1
    assert envelope["artifact_origin_level"] == "local_contract"
    assert envelope["qualification_level"] == LOCAL_QUALIFICATION_LEVEL
    assert validate_phase8_evidence(envelope_path)["qualification_level"] == LOCAL_QUALIFICATION_LEVEL

    with pytest.raises(ValueError, match=r"^local_self_promotion(?::|$)"):
        build_local_phase8_envelope(
            tmp_path / "illegal.json",
            experiment_id="phase8-illegal-promotion",
            source_commit=SOURCE_COMMIT,
            protocol_sha256="1" * 64,
            runtime_provenance={"artifact_origin": "local_contract"},
            referenced_paths=[artifact],
            qualification_level=PILOT_QUALIFICATION_LEVEL,
        )

    mutated = deepcopy(envelope)
    mutated["qualification_level"] = PILOT_QUALIFICATION_LEVEL
    envelope_path.write_bytes(_canonical_bytes(mutated))
    with pytest.raises(ValueError, match=r"^local_self_promotion(?::|$)"):
        validate_phase8_evidence(envelope_path)


def test_exact_sixteen_health_audit_earns_only_collection_chain_qualification(tmp_path: Path):
    root = tmp_path / "pilot"
    policy = _write_fixture(root)

    result = audit_pilot_collection(root, require_server=True)

    assert result["validation_gate"] == "pilot_health_gate"
    assert result["decision"] == "collection_chain_ready"
    assert result["qualification_level"] == PILOT_QUALIFICATION_LEVEL
    assert result["configuration_count"] == 8
    assert result["episode_count"] == 16
    assert result["transition_count"] == 16 * 128
    assert result["warnings"] == []
    assert (root / "pilot_inventory.json").is_file()
    assert (root / "pilot_health_decision.json").is_file()
    envelope_path = root / "pilot_envelope.json"
    validated = validate_phase8_evidence(
        envelope_path, required_qualification=PILOT_QUALIFICATION_LEVEL
    )
    assert validated["qualification_level"] == PILOT_QUALIFICATION_LEVEL
    assert validated["referenced_file_count"] == 51
    for entry in policy["entries"]:
        assert (root / "episodes" / f"{entry['episode_id']}.jsonl").is_file()

    decision = json.loads((root / "pilot_health_decision.json").read_text(encoding="utf-8"))
    assert decision["pilot_health_gate"] == "pass"
    assert set(decision["channel_health"]) == set(EXPECTED_CONFIGURATIONS)
    for configuration in ("uuv4", "uuv4_angled"):
        assert decision["channel_health"][configuration]["raw_yaw_nonzero_count"] > 0
        assert decision["channel_health"][configuration]["virtual_yaw_nonzero_count"] == 0
    forbidden = ("model", "feature", "horizon", "rank", "condition", "prediction_error", "rollout")
    assert not any(token in json.dumps(decision).lower() for token in forbidden)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing_episode", "inventory_set_mismatch"),
        ("unexpected_file", "inventory_set_mismatch"),
        ("manifest_hash", "manifest_hash_mismatch"),
        ("source_drift", "source_commit_mismatch"),
        ("runtime_drift", "runtime_provenance_disagreement"),
        ("modeling_file", "pilot_modeling_forbidden"),
        ("modeling_field", "pilot_modeling_forbidden"),
    ],
)
def test_health_audit_fails_closed_for_inventory_hash_provenance_and_modeling_mutations(
    tmp_path: Path, mutation: str, reason: str
):
    root = tmp_path / "pilot"
    policy = _write_fixture(root)
    episode_id = policy["entries"][0]["episode_id"]
    if mutation == "missing_episode":
        (root / "episodes" / f"{episode_id}.jsonl").unlink()
    elif mutation == "unexpected_file":
        (root / "logs" / "stale.log").write_text("stale\n", encoding="utf-8")
    elif mutation == "manifest_hash":
        _rewrite_manifest(root, episode_id, lambda value: value.__setitem__("transition_sha256", "0" * 64))
    elif mutation == "source_drift":
        _rewrite_manifest(
            root,
            episode_id,
            lambda value: value["episode_invariants"].__setitem__("source_commit", "b" * 40),
        )
    elif mutation == "runtime_drift":
        _rewrite_manifest(
            root,
            episode_id,
            lambda value: value["runtime_provenance"].__setitem__("actual_isaac_lab", "9.9.9"),
        )
    elif mutation == "modeling_file":
        (root / "fit_model.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "modeling_field":
        path = root / "episodes" / f"{episode_id}.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["prediction_error"] = 0.0
        lines[0] = json.dumps(first, allow_nan=False, sort_keys=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=rf"^{reason}(?::|$)"):
        audit_pilot_collection(root, require_server=True)
    assert not (root / "pilot_envelope.json").exists()
    assert not list(root.rglob("*.tmp"))


def test_health_audit_rejects_yaw_mask_failure_with_no_pass_envelope(tmp_path: Path):
    root = tmp_path / "pilot"
    policy = _write_fixture(root)
    entry = next(item for item in policy["entries"] if item["configuration"] == "uuv4")
    path = root / "episodes" / f"{entry['episode_id']}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    for row in rows:
        row["raw_action_4"][2] = 0.0
    path.write_bytes(b"".join(_canonical_bytes(row) for row in rows))
    _rewrite_manifest(root, entry["episode_id"], lambda value: value.__setitem__("transition_sha256", _sha256(path)))

    with pytest.raises(ValueError, match=r"^pilot_health_failed:uuv4_raw_yaw_probe_missing(?::|$)"):
        audit_pilot_collection(root, require_server=True)
    assert not (root / "pilot_envelope.json").exists()


def test_external_validator_rereads_every_referenced_byte_and_rejects_stale_outputs(tmp_path: Path):
    root = tmp_path / "pilot"
    policy = _write_fixture(root)
    audit_pilot_collection(root, require_server=True)
    episode_id = policy["entries"][0]["episode_id"]
    log_path = root / "logs" / f"{episode_id}.log"
    log_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"^artifact_hash_mismatch(?::|$)"):
        validate_phase8_evidence(
            root / "pilot_envelope.json",
            required_qualification=PILOT_QUALIFICATION_LEVEL,
        )


def test_existing_audit_output_is_refused_without_overwrite(tmp_path: Path):
    root = tmp_path / "pilot"
    _write_fixture(root)
    first = audit_pilot_collection(root, require_server=True)
    before = {
        path.name: path.read_bytes()
        for path in (
            root / "pilot_inventory.json",
            root / "pilot_health_decision.json",
            root / "pilot_envelope.json",
        )
    }

    with pytest.raises(ValueError, match=r"^artifact_exists(?::|$)"):
        audit_pilot_collection(root, require_server=True)

    assert first["decision"] == "collection_chain_ready"
    assert before == {
        path.name: path.read_bytes()
        for path in (
            root / "pilot_inventory.json",
            root / "pilot_health_decision.json",
            root / "pilot_envelope.json",
        )
    }


def test_auditor_imports_no_modeling_or_evaluation_modules():
    source_path = PROJECT_ROOT / "workflows" / "audit_koopman_v2_pilot.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    forbidden = ("koopman.model", "koopman.edmd", "koopman.evaluation", "koopman.loco_v2")
    assert not any(name == prefix or name.startswith(prefix + ".") for name in imports for prefix in forbidden)


def test_phase8_validator_cli_reports_deterministic_server_qualification(tmp_path: Path, capsys):
    root = tmp_path / "pilot"
    _write_fixture(root)
    audit_pilot_collection(root, require_server=True)

    exit_code = validate_phase8_main(
        [
            "--envelope",
            str(root / "pilot_envelope.json"),
            "--qualification",
            PILOT_QUALIFICATION_LEVEL,
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["validation_gate"] == "phase8_external_evidence_valid"
    assert output["qualification_level"] == PILOT_QUALIFICATION_LEVEL
    assert output["artifact_origin_level"] == "server_isaac_smoke"

