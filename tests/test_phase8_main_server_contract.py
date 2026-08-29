from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from workflows import collect_koopman_v2_identification as collection_workflow
from koopman.protocol_v2 import (
    MAIN_EXCITATION_FAMILIES,
    MAIN_RAW_ACTION_ABS_MAX,
    PUBLIC_CONFIGURATIONS,
    load_analysis_policy_v1,
    validate_analysis_policy_v1,
    validate_main_role_protocol_v1,
)
from workflows.collect_koopman_v2_identification import (
    collect_policy_entries,
    deterministic_policy_action,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLE_PROTOCOL_PATH = PROJECT_ROOT / "protocols" / "phase8" / "main_role_assignment_protocol.json"
ANALYSIS_POLICY_PATH = PROJECT_ROOT / "protocols" / "phase8" / "analysis_policy.json"
PILOT_POLICY_PATH = PROJECT_ROOT / "protocols" / "phase8" / "pilot_collection_policy.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_exact_main_role_protocol_is_the_pending_d23_proposal() -> None:
    protocol = _json(ROLE_PROTOCOL_PATH)
    validate_main_role_protocol_v1(protocol)

    assert protocol["protocol_version"] == "phase8-main-role-protocol-v2"
    assert protocol["experiment_id"] == "phase8-main-identification-v2-proposal"
    assert protocol["approval_status"] == "pending_d23"
    assert protocol["proposal_only"] is True
    assert protocol["transition_count"] == 512
    assert protocol["raw_action_abs_max"] == 0.25
    assert len(protocol["entries"]) == 96

    by_configuration: dict[str, list[dict]] = defaultdict(list)
    for entry in protocol["entries"]:
        by_configuration[entry["configuration"]].append(entry)
    assert tuple(by_configuration) == tuple(PUBLIC_CONFIGURATIONS)

    expected_excitation_seeds = {
        "fit": [8201, 8202],
        "validation": [8301],
        "test": [8401],
    }
    expected_environment_seeds = {
        "fit": {
            "independent_prbs": [9211, 9212],
            "bounded_multisine": [9221, 9222],
            "coupled_chirp": [9231, 9232],
        },
        "validation": {
            "independent_prbs": [9311],
            "bounded_multisine": [9321],
            "coupled_chirp": [9331],
        },
        "test": {
            "independent_prbs": [9411],
            "bounded_multisine": [9421],
            "coupled_chirp": [9431],
        },
    }
    assert protocol["seed_semantics"] == {
        "environment_seed_field": "seed",
        "environment_seed_scope": "matched_across_configurations_by_role_family_repetition",
        "environment_seed_controls": [
            "environment_reset",
            "goal_reference",
        ],
        "excitation_seed_field": "excitation_seed",
        "excitation_seed_scope": "matched_across_configurations_by_role_repetition",
    }
    assert protocol["environment_contract"] == {
        "domain_randomization_enabled": False,
        "eval_mode": True,
        "reference_mode": "step",
        "sensor_noise_enabled": False,
        "disturbance_mode": "none",
    }
    for configuration in PUBLIC_CONFIGURATIONS:
        entries = by_configuration[configuration]
        assert len(entries) == 12
        assert Counter(entry["role"] for entry in entries) == {
            "fit": 6,
            "validation": 3,
            "test": 3,
        }
        for role, excitation_seeds in expected_excitation_seeds.items():
            role_entries = [entry for entry in entries if entry["role"] == role]
            for family in MAIN_EXCITATION_FAMILIES:
                assert [
                    entry["excitation_seed"]
                    for entry in role_entries
                    if entry["excitation_family"] == family
                ] == excitation_seeds
                assert [
                    entry["seed"]
                    for entry in role_entries
                    if entry["excitation_family"] == family
                ] == expected_environment_seeds[role][family]

    episode_ids = [entry["episode_id"] for entry in protocol["entries"]]
    assert len(set(episode_ids)) == 96
    assert not any(episode_id.startswith("phase8-pilot-") for episode_id in episode_ids)
    assert {entry["seed"] for entry in protocol["entries"]}.isdisjoint({8101, 8102})


def test_exact_main_analysis_policy_is_pending_d23_and_immutable() -> None:
    payload = _json(ANALYSIS_POLICY_PATH)
    policy = load_analysis_policy_v1(ANALYSIS_POLICY_PATH)

    assert payload["analysis_policy_version"] == "phase8-analysis-policy-v2"
    assert policy.approval_status == "pending_d23"
    assert policy.qualification_level == "local_contract"
    assert policy.data_prefixes == (2, 4, 6)
    assert policy.observable_candidates == ("identity_v1", "auv_kinematic_v1")
    assert policy.ridge_grid == (1e-8, 1e-6, 1e-4, 1e-2)
    assert policy.normalization_candidates == ("none", "standard_v1")
    assert policy.platform_schema_candidates == (
        "none",
        "platform_physical_compact_v1",
        "platform_physical_core_v1",
    )
    assert policy.horizons == (5, 20, 60, "full")
    assert policy.bootstrap == {
        "alpha": 0.05,
        "aggregate": "equal_configuration_macro",
        "configuration_sampling": "fixed_exact_eight",
        "pairing": "paired_by_configuration_role_family_repetition",
        "population_scope": "supported_exact_eight_only",
        "resamples": 2000,
        "seed": 80304,
        "stratify_by": "configuration",
        "unit": "episode_block",
    }
    assert payload["outer_fold_execution"] == {
        "candidate_selection": "seven_source_fit_validation_only",
        "holdout_unit": "configuration",
        "normalization": "seven_source_only",
        "primary_heldout_access": "final_test_only",
        "primary_model_freeze": "before_heldout_test_open",
    }
    assert payload["metric_schema"] == {
        "aggregation": [
            "per_configuration",
            "equal_configuration_macro",
            "worst_configuration",
        ],
        "official_orientation": "so3_geodesic_radians",
        "row_weighted": "diagnostic_only",
        "version": "phase8-episode-metrics-v1",
    }
    assert payload["gate_template"] == {
        "conditional_margin_fraction": 0.05,
        "divergence_max": 0,
        "invalid_quaternion_max": 0,
        "minimum_improvement_fraction": 0.01,
        "nonfinite_max": 0,
        "noninferiority_fraction": 0.1,
    }
    assert payload["forbidden_inputs"] == [
        "reference_5",
        "motor_pwm_padded_8",
        "thruster_mask_8",
        "applied_wrench_6",
        "environment_context_oracle",
        "environment_context_estimated",
        "configuration_identity",
        "heldout_statistics",
    ]
    assert payload["forbidden_roles"] == [
        "heldout_expert_upper_bound_v2",
        "reference_conditioned_diagnostic_v2",
    ]

    for mutation in (
        lambda value: value.update(post_test_mutable=True),
        lambda value: value.update(ridge_grid=[]),
        lambda value: value.update(ridge_grid=[float("nan")]),
        lambda value: value.update(observable_candidates=["identity"]),
    ):
        changed = deepcopy(payload)
        mutation(changed)
        with pytest.raises(ValueError):
            validate_analysis_policy_v1(changed)


def test_main_actions_are_deterministic_bounded_signed_and_family_specific() -> None:
    entries = _json(ROLE_PROTOCOL_PATH)["entries"]
    representatives = {
        family: next(entry for entry in entries if entry["excitation_family"] == family)
        for family in MAIN_EXCITATION_FAMILIES
    }
    trajectories = {}
    for family, entry in representatives.items():
        first = [deterministic_policy_action(entry, step) for step in range(512)]
        second = [deterministic_policy_action(deepcopy(entry), step) for step in range(512)]
        assert first == second
        assert all(len(action) == 4 for action in first)
        assert all(
            abs(value) <= MAIN_RAW_ACTION_ABS_MAX
            for action in first
            for value in action
        )
        for channel in range(4):
            assert any(action[channel] > 0.0 for action in first)
            assert any(action[channel] < 0.0 for action in first)
        trajectories[family] = first

        changed_environment = deepcopy(entry)
        changed_environment["seed"] += 100
        assert [
            deterministic_policy_action(changed_environment, step) for step in range(512)
        ] == first

        changed_excitation = deepcopy(entry)
        changed_excitation["excitation_seed"] += 1
        assert [
            deterministic_policy_action(changed_excitation, step) for step in range(512)
        ] != first
    assert len({repr(value) for value in trajectories.values()}) == 3


def test_main_environment_contract_disables_non_nominal_randomization() -> None:
    protocol = _json(ROLE_PROTOCOL_PATH)
    cfg = SimpleNamespace(
        eval_mode=False,
        reference_mode="sine_sweep",
        disturbance_cfg=SimpleNamespace(mode="jonswap"),
        noise_cfg=SimpleNamespace(enable_noise=True),
        domain_randomization=SimpleNamespace(use_custom_randomization=True),
    )

    collection_workflow.apply_main_environment_contract(cfg, protocol)

    assert cfg.eval_mode is True
    assert cfg.reference_mode == "step"
    assert cfg.disturbance_cfg.mode == "none"
    assert cfg.noise_cfg.enable_noise is False
    assert cfg.domain_randomization.use_custom_randomization is False


def test_main_environment_contract_prevents_native_timeout_inside_512_step_block() -> None:
    protocol = _json(ROLE_PROTOCOL_PATH)
    cfg = SimpleNamespace(
        cap_episode_length=True,
        eval_mode=False,
        reference_mode="sine_sweep",
        disturbance_cfg=SimpleNamespace(mode="jonswap"),
        noise_cfg=SimpleNamespace(enable_noise=True),
        domain_randomization=SimpleNamespace(use_custom_randomization=True),
    )

    collection_workflow.apply_main_environment_contract(cfg, protocol)

    assert cfg.cap_episode_length is False


class _Bridge:
    def __init__(self, entry: dict, fail_at: int | None = None) -> None:
        self.entry = entry
        self.fail_at = fail_at
        self.steps = 0

    def step_and_record(self, action: tuple[float, ...]) -> dict:
        if self.steps == self.fail_at:
            raise RuntimeError("bridge_failure")
        row = {
            "raw_action_4": list(action),
            "virtual_control_4": list(action),
            "episode_provenance": {
                "episode_id": self.entry["episode_id"],
                "step_index": self.steps,
            },
        }
        self.steps += 1
        return row


class _Logger:
    def __init__(self, entry: dict) -> None:
        self.entry = entry
        self.rows = []
        self.finalized = False

    def write(self, row: dict) -> None:
        self.rows.append(row)

    def finalize(self) -> dict:
        self.finalized = True
        return {"episode_id": self.entry["episode_id"], "record_count": len(self.rows)}


def test_main_collection_resets_and_finalizes_12_independent_episodes() -> None:
    entries = [
        entry
        for entry in _json(ROLE_PROTOCOL_PATH)["entries"]
        if entry["configuration"] == "base"
    ]
    resets = []
    loggers: list[_Logger] = []

    def logger_factory(entry: dict) -> _Logger:
        logger = _Logger(entry)
        loggers.append(logger)
        return logger

    results = collect_policy_entries(
        entries,
        reset=lambda seed, episode_id: resets.append((seed, episode_id)),
        bridge_factory=lambda entry: _Bridge(entry),
        logger_factory=logger_factory,
    )
    assert resets == [(entry["seed"], entry["episode_id"]) for entry in entries]
    assert len(results) == len(loggers) == 12
    assert all(logger.finalized and len(logger.rows) == 512 for logger in loggers)


def test_main_collection_failure_does_not_finalize_or_continue() -> None:
    entries = [
        entry
        for entry in _json(ROLE_PROTOCOL_PATH)["entries"]
        if entry["configuration"] == "base"
    ]
    loggers: list[_Logger] = []

    def logger_factory(entry: dict) -> _Logger:
        logger = _Logger(entry)
        loggers.append(logger)
        return logger

    with pytest.raises(RuntimeError, match="bridge_failure"):
        collect_policy_entries(
            entries,
            reset=lambda seed, episode_id: None,
            bridge_factory=lambda entry: _Bridge(entry, fail_at=7),
            logger_factory=logger_factory,
        )
    assert len(loggers) == 1
    assert loggers[0].finalized is False


def test_main_scripts_freeze_exact_set_provenance_and_no_partial_promotion() -> None:
    expected_tokens = {
        "scripts/phase8_main_local_preflight.ps1": (
            "test_phase8_main_server_contract.py",
            "canonical_main_absent",
            "pilot_evidence_preserved",
            "worktree_clean",
        ),
        "scripts/phase8_main_prepare_bundle.ps1": (
            "phase8_main_local_preflight.ps1",
            "main_role_assignment_protocol.json",
            "analysis_policy.json",
            "expected-source-commit.txt",
        ),
        "scripts/phase8_main_server_bootstrap.sh": (
            "/root/EASYkoopman-phase8-main-v2",
            "expected-source-commit.txt",
            "phase8_main_server_run.sh",
        ),
        "scripts/phase8_main_server_run.sh": (
            "koopman_phase8_dataset",
            "phase8-main-identification-v2-proposal",
            "main_role_assignment_protocol.json",
            "analysis_policy.json",
            "dataset_inventory.json",
            "loco_split_manifest.json",
            "dataset_envelope.json",
            "all_files.sha256",
            "native_status",
            "tee_status",
            "semantic_status",
            "exact_96",
        ),
        "scripts/phase8_main_pullback.ps1": (
            "canonical_evidence_already_exists",
            "source_commit_mismatch",
            "runtime_version_mismatch",
            "sha256_mismatch",
            "inventory_file_set_mismatch",
            "role_protocol_sha256",
            "analysis_policy_sha256",
        ),
    }
    for relative, tokens in expected_tokens.items():
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        for token in tokens:
            assert token in text, f"{relative} is missing fail-closed token {token!r}"

    assert not (PROJECT_ROOT / "source" / "results" / "koopman_phase8_dataset").exists()


def test_main_server_runner_reuses_locked_server_environment_and_snapshots_pipeline_status() -> None:
    text = (PROJECT_ROOT / "scripts" / "phase8_main_server_run.sh").read_text(
        encoding="utf-8"
    )

    for token in (
        "set -Eeuo pipefail",
        "phase6_server_preflight.sh",
        "phase6_offline_install.sh",
        "/opt/conda/etc/profile.d/conda.sh",
        "/opt/conda/envs/isaaclab/bin/python",
        "phase6_activate_conda_env",
        "phase6_capture_locked_isaaclab_state",
        "phase6_prepare_offline_python_env",
        'pipeline_status=("${PIPESTATUS[@]}")',
        'native_status="${pipeline_status[0]:-125}"',
        'tee_status="${pipeline_status[1]:-125}"',
        "configuration_exact_12_failed",
        'part_count="$(find',
        'semantic_status="pass"',
        'runtime_sha="$("$CONDA_PYTHON" -c',
        '"$CONDA_PYTHON" workflows/build_koopman_v2_inventory.py',
        '"$CONDA_PYTHON" workflows/build_koopman_v2_splits.py',
        '"$CONDA_PYTHON" workflows/build_phase8_main_envelope.py',
        '"$CONDA_PYTHON" workflows/validate_phase8_evidence.py',
    ):
        assert token in text, f"main server runner is missing {token!r}"

    for unsafe_postprocess in (
        '"$ISAACLAB_PY" -p workflows/build_koopman_v2_inventory.py',
        '"$ISAACLAB_PY" -p workflows/build_koopman_v2_splits.py',
        '"$ISAACLAB_PY" -p workflows/build_phase8_main_envelope.py',
        '"$ISAACLAB_PY" -p workflows/validate_phase8_evidence.py',
    ):
        assert unsafe_postprocess not in text

    assert "native_status=${PIPESTATUS[0]}" not in text
    assert "tee_status=${PIPESTATUS[1]}" not in text


def test_runbook_marks_d23_values_as_unapproved_engineering_design() -> None:
    text = (PROJECT_ROOT / "docs" / "phase8_koopman_identification_runbook.md").read_text(
        encoding="utf-8"
    )
    for token in (
        "D-23",
        "pending_d23",
        "pre-registered engineering design",
        "not a statistical optimality claim",
        "8 × 12 × 512",
        "dataset-not-model",
        "fresh experiment",
    ):
        assert token in text
