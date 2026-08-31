from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.loco_v21 import (
    CandidateEvaluationV21,
    CandidateSpecV21,
    NumericalDiagnosticsV21,
    PRIMARY_METRICS_V21,
    SourceMetricRecordV21,
)
from koopman.model_v21 import CONDITIONING_STRUCTURED_PCA2_V21
from workflows import run_koopman_v21_loco, select_koopman_v21


EXPERIMENT_ID = "phase8.1-main-identification-v1"


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _write_protocol_inputs(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    source_root = Path(__file__).resolve().parents[1] / "protocols" / "phase8_1"
    role_path = tmp_path / "role.json"
    policy_path = tmp_path / "policy.json"
    role_path.write_bytes((source_root / "main_role_assignment_protocol.json").read_bytes())
    policy_path.write_bytes((source_root / "analysis_policy.json").read_bytes())
    role = json.loads(role_path.read_text(encoding="utf-8"))
    role_sha = hashlib.sha256(role_path.read_bytes()).hexdigest()
    policy_sha = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    inventory = {
        "experiment_id": EXPERIMENT_ID,
        "inventory_version": "phase8.1-protocol-episode-inventory-v1",
        "role_protocol_sha256": role_sha,
        "episodes": [
            {
                "configuration": entry["configuration"],
                "episode_id": entry["episode_id"],
                "family_repetition": (
                    f'{entry["excitation_family"]}-r{entry["repetition"]}'
                ),
                "manifest_path": entry["manifest_path"],
                "role": entry["role"],
                "role_protocol_sha256": role_sha,
                "transition_count": 512,
                "transition_path": entry["transition_path"],
                "transition_sha256": f"{index + 1:064x}",
            }
            for index, entry in enumerate(role["entries"])
        ],
    }
    inventory["inventory_sha256"] = hashlib.sha256(
        _canonical_bytes(inventory)
    ).hexdigest()
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_bytes(_canonical_bytes(inventory))
    return role_path, policy_path, inventory_path, role_sha, policy_sha


def _candidate(label: str, family: str) -> CandidateSpecV21:
    return CandidateSpecV21(
        family=family,
        observable_schema="so3_identity_v1",
        data_prefix=2,
        ridge=1e-6,
        normalization="standard_v1",
        conditioning=(
            "none" if family == "pooled" else CONDITIONING_STRUCTURED_PCA2_V21
        ),
        label=label,
    )


class _Transform:
    def diagnose_heldout_descriptor(self, descriptor):
        return {
            "inside_convex_hull": False,
            "outside_source_range_indices": [0],
            "pca_residual_l2": float(sum(descriptor)),
        }


class _SyntheticFormalLocoBackend:
    def __init__(self) -> None:
        self.opened_roles: list[str] = []
        self.freeze_events: list[tuple[str, str]] = []
        self._primary_bound: set[str] = set()

    def prepare_source_fold(self, *, heldout_configuration, source_configurations, source_bindings):
        from koopman.evaluation_v21 import FormalFoldSourceInputsV21

        assert {binding.role for binding in source_bindings} == {"fit", "validation"}
        assert all(binding.configuration in source_configurations for binding in source_bindings)
        pooled = _candidate(f"{heldout_configuration}-pooled", "pooled")
        conditional = _candidate(f"{heldout_configuration}-conditional", "conditional")

        def evaluation(candidate, value, width):
            records = tuple(
                SourceMetricRecordV21(
                    configuration,
                    dict.fromkeys(PRIMARY_METRICS_V21, value),
                    dict.fromkeys(PRIMARY_METRICS_V21, 1.0),
                    dict.fromkeys(PRIMARY_METRICS_V21, 0.9),
                )
                for configuration in source_configurations
            )
            return CandidateEvaluationV21(
                candidate,
                records,
                NumericalDiagnosticsV21(width, float(width), width, 2.0),
                True,
                None,
                f"model:{candidate.candidate_id}",
                f"normalizer:{candidate.candidate_id}",
                (
                    f"pca:{heldout_configuration}"
                    if candidate.family == "conditional"
                    else None
                ),
            )

        return FormalFoldSourceInputsV21(
            expected_candidates=(pooled, conditional),
            candidate_evaluations=(
                evaluation(pooled, 0.55, 22),
                evaluation(conditional, 0.45, 66),
            ),
            source_transform=_Transform(),
        )

    def bind_primary(self, *, heldout_configuration, primary):
        assert primary is not None
        self._primary_bound.add(heldout_configuration)
        self.freeze_events.append((heldout_configuration, "primary_bound"))

    def build_heldout_descriptor(self, *, heldout_configuration):
        assert heldout_configuration in self._primary_bound
        self.freeze_events.append((heldout_configuration, "descriptor_built"))
        return (1.0, 2.0)

    def open_episode(self, binding):
        self.opened_roles.append(binding.role)
        return f"payload:{binding.episode_id}"

    def expert_candidates(self, *, heldout_configuration):
        from koopman.evaluation_v21 import ExpertCandidateSpecV21

        return (
            ExpertCandidateSpecV21(
                f"expert:{heldout_configuration}", "so3_identity_v1", 1e-6, "none"
            ),
        )

    def fit_expert(self, candidate, payloads):
        return {
            "candidate": candidate.candidate_id,
            "model_identity": f"expert-model:{candidate.candidate_id}",
            "normalizer_identity": f"expert-normalizer:{candidate.candidate_id}",
        }

    def evaluate_expert(self, model, payloads):
        return (
            dict.fromkeys(PRIMARY_METRICS_V21, 0.2),
            dict.fromkeys(PRIMARY_METRICS_V21, 1.0),
            dict.fromkeys(PRIMARY_METRICS_V21, 0.8),
        )

    @staticmethod
    def serialize_expert(model):
        return _canonical_bytes(model)

    @staticmethod
    def load_expert(data):
        return json.loads(data)

    @staticmethod
    def expert_identities(model):
        return model["model_identity"], model["normalizer_identity"]

    def evaluate_test_horizons(
        self, *, heldout_configuration, role, model_identity, opened_episodes
    ):
        from koopman.selection_v21 import HorizonOuterEvidenceV21

        assert len(opened_episodes) == 3
        value = {
            "persistence": 1.0,
            "simple_linear": 0.9,
            "pooled": 0.7,
            "conditional": 0.6,
        }[role]
        horizon = HorizonOuterEvidenceV21(
            metrics=dict.fromkeys(PRIMARY_METRICS_V21, value),
            status="success",
            reason_code=None,
            transition_count=512,
            window_count=1,
            nonfinite_count=0,
            invalid_quaternion_count=0,
            quaternion_unit_norm_drift_count=0,
            quaternion_projection_count=0,
            divergence_count=0,
        )
        return tuple(
            {name: horizon for name in ("5", "20", "60", "full")}
            for _ in opened_episodes
        )


@dataclass
class _SyntheticFinalBackend:
    opened_roles: list[str]

    def open_episode(self, binding):
        self.opened_roles.append(binding.role)
        assert binding.role != "test"
        return f"payload:{binding.episode_id}"

    def candidates(self, selected_family):
        return (
            _candidate("all8-conditional-a", selected_family),
            _candidate("all8-conditional-b", selected_family),
        )

    def inner_select(self, selected_family, fit, validation, candidates):
        assert len(fit) == 48 and len(validation) == 24
        return candidates[-1]

    def final_fit(self, candidate, episodes):
        assert len(episodes) == 72
        return {"candidate_id": candidate.candidate_id, "count": len(episodes)}

    @staticmethod
    def serialize(model):
        return _canonical_bytes(model)

    @staticmethod
    def load(data):
        return json.loads(data)

    @staticmethod
    def model_identity(model):
        return model["candidate_id"], model["count"]


def test_authorized_synthetic_full_chain_uses_real_state_machine_and_exact_protocol_sets(
    tmp_path: Path,
) -> None:
    role, policy, inventory, role_sha, policy_sha = _write_protocol_inputs(tmp_path)
    split = tmp_path / "split.json"
    from koopman.evaluation_v21 import load_protocol_episode_registry_v21

    registry = load_protocol_episode_registry_v21(
        role_protocol_path=role,
        inventory_path=inventory,
    )
    split.write_bytes(_canonical_bytes(registry.expected_split_payload()))
    approval = {
        "decision": "approved",
        "experiment_id": EXPERIMENT_ID,
        "role_protocol_sha256": role_sha,
        "analysis_policy_sha256": policy_sha,
    }
    evaluation_root = tmp_path / "evaluation"
    loco_backend = _SyntheticFormalLocoBackend()
    status = run_koopman_v21_loco._run_authorized_loco(
        args=SimpleNamespace(
            role_protocol=role,
            analysis_policy=policy,
            inventory=inventory,
            split=split,
            dataset_root=tmp_path / "synthetic-dataset",
            output_root=evaluation_root,
            source_commit="1" * 40,
        ),
        approval=approval,
        backend=loco_backend,
    )
    assert status == 0
    assert (evaluation_root / "evaluation_envelope.json").is_file()
    summary = json.loads(
        (evaluation_root / "evaluation_summary.json").read_text(encoding="utf-8")
    )
    assert len(summary["folds"]) == 8
    assert all(fold["state"] == "TEST_OPENED" for fold in summary["folds"])
    assert loco_backend.opened_roles.count("test") == 24
    assert loco_backend.opened_roles.count("fit") == 48
    assert loco_backend.opened_roles.count("validation") == 24
    assert loco_backend.freeze_events == [
        event
        for configuration in SUPPORTED_EMBODIMENTS
        for event in (
            (configuration, "primary_bound"),
            (configuration, "descriptor_built"),
        )
    ]
    for configuration in SUPPORTED_EMBODIMENTS:
        fold_root = evaluation_root / "folds" / configuration
        ledger = json.loads(
            (fold_root / "source_candidate_ledger.json").read_text(encoding="utf-8")
        )
        freeze = json.loads(
            (fold_root / "pre_test_freeze.json").read_text(encoding="utf-8")
        )
        diagnostic = json.loads(
            (fold_root / "heldout_descriptor_diagnostic.json").read_text(
                encoding="utf-8"
            )
        )
        expert = json.loads(
            (fold_root / "expert" / "expert_freeze.json").read_text(
                encoding="utf-8"
            )
        )
        assert diagnostic["selection_eligible"] is False
        assert diagnostic["source_ledger_sha256"] == ledger["ledger_sha256"]
        assert freeze["selected_candidates"] == ledger["selected_candidates"]
        assert "heldout_descriptor" not in ledger
        expert_artifact = fold_root / "expert" / "selected_model.json"
        assert expert_artifact.is_file()
        assert expert["model_artifact_sha256"] == hashlib.sha256(
            expert_artifact.read_bytes()
        ).hexdigest()
        assert expert["selection_eligible"] is False
        assert expert["nonpromoting"] is True

    final_backend = _SyntheticFinalBackend([])
    selection_root = tmp_path / "selection"
    status = select_koopman_v21._run_authorized_selection(
        args=SimpleNamespace(
            role_protocol=role,
            analysis_policy=policy,
            inventory=inventory,
            evaluation_root=evaluation_root,
            dataset_root=tmp_path / "synthetic-dataset",
            output_root=selection_root,
            source_commit="1" * 40,
        ),
        approval=approval,
        backend=final_backend,
    )
    assert status == 0
    result = json.loads(
        (selection_root / "selection_result.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "SELECTION"
    assert result["selected_family"] == "conditional"
    assert (selection_root / "selected_model" / "selected_model.bin").is_file()
    assert final_backend.opened_roles == ["fit"] * 48 + ["validation"] * 24

    from koopman.evaluation_v21 import validate_expert_artifact_v21

    first_expert_root = evaluation_root / "folds" / SUPPORTED_EMBODIMENTS[0] / "expert"
    first_freeze = json.loads(
        (first_expert_root / "expert_freeze.json").read_text(encoding="utf-8")
    )
    first_artifact = first_expert_root / "selected_model.json"
    first_artifact.write_bytes(first_artifact.read_bytes() + b" ")
    with pytest.raises(ValueError, match="expert_artifact_hash_mismatch"):
        validate_expert_artifact_v21(
            first_freeze,
            artifact_path=first_artifact,
            loader=loco_backend.load_expert,
            identity_reader=loco_backend.expert_identities,
        )


def test_segmented_fold_outputs_survive_later_failure_and_assemble_exact_eight(
    tmp_path: Path,
) -> None:
    role, policy, inventory, role_sha, policy_sha = _write_protocol_inputs(tmp_path)
    from koopman.evaluation_v21 import load_protocol_episode_registry_v21

    registry = load_protocol_episode_registry_v21(
        role_protocol_path=role,
        inventory_path=inventory,
    )
    split = tmp_path / "split.json"
    split.write_bytes(_canonical_bytes(registry.expected_split_payload()))
    approval = {
        "decision": "approved",
        "experiment_id": EXPERIMENT_ID,
        "role_protocol_sha256": role_sha,
        "analysis_policy_sha256": policy_sha,
    }
    fold_work_root = tmp_path / "fold-work"

    def fold_args(configuration: str) -> SimpleNamespace:
        return SimpleNamespace(
            role_protocol=role,
            analysis_policy=policy,
            inventory=inventory,
            split=split,
            dataset_root=tmp_path / "synthetic-dataset",
            output_root=fold_work_root / configuration,
            source_commit="1" * 40,
            evaluator_commit="2" * 40,
            fold=configuration,
        )

    first = SUPPORTED_EMBODIMENTS[0]
    assert (
        run_koopman_v21_loco._run_authorized_loco_fold(
            args=fold_args(first),
            approval=approval,
            backend=_SyntheticFormalLocoBackend(),
        )
        == 0
    )
    first_envelope = fold_work_root / first / "fold_envelope.json"
    assert first_envelope.is_file()

    class _FailingBackend(_SyntheticFormalLocoBackend):
        def prepare_source_fold(self, **kwargs):
            raise RuntimeError("synthetic_native_process_failure")

    second = SUPPORTED_EMBODIMENTS[1]
    with pytest.raises(RuntimeError, match="synthetic_native_process_failure"):
        run_koopman_v21_loco._run_authorized_loco_fold(
            args=fold_args(second),
            approval=approval,
            backend=_FailingBackend(),
        )
    assert first_envelope.is_file()
    assert not (fold_work_root / second).exists()

    for configuration in SUPPORTED_EMBODIMENTS[1:]:
        assert (
            run_koopman_v21_loco._run_authorized_loco_fold(
                args=fold_args(configuration),
                approval=approval,
                backend=_SyntheticFormalLocoBackend(),
            )
            == 0
        )

    evaluation_root = tmp_path / "evaluation"
    assert (
        run_koopman_v21_loco._assemble_authorized_loco_folds(
            args=SimpleNamespace(
                role_protocol=role,
                analysis_policy=policy,
                inventory=inventory,
                split=split,
                fold_root=fold_work_root,
                output_root=evaluation_root,
                source_commit="1" * 40,
                evaluator_commit="2" * 40,
            ),
            approval=approval,
        )
        == 0
    )
    summary = json.loads(
        (evaluation_root / "evaluation_summary.json").read_text(encoding="utf-8")
    )
    assert tuple(
        fold["heldout_configuration"] for fold in summary["folds"]
    ) == tuple(SUPPORTED_EMBODIMENTS)
    assert all(fold["state"] == "TEST_OPENED" for fold in summary["folds"])
    assert summary["source_commit"] == "1" * 40
    assert summary["evaluator_commit"] == "2" * 40


def test_segmented_assembly_rejects_rehashed_post_test_freeze_mutation(
    tmp_path: Path,
) -> None:
    role, policy, inventory, role_sha, policy_sha = _write_protocol_inputs(tmp_path)
    from koopman.evaluation_v21 import load_protocol_episode_registry_v21

    registry = load_protocol_episode_registry_v21(
        role_protocol_path=role,
        inventory_path=inventory,
    )
    split = tmp_path / "split.json"
    split.write_bytes(_canonical_bytes(registry.expected_split_payload()))
    approval = {
        "decision": "approved",
        "experiment_id": EXPERIMENT_ID,
        "role_protocol_sha256": role_sha,
        "analysis_policy_sha256": policy_sha,
    }
    heldout = SUPPORTED_EMBODIMENTS[0]
    fold_work_root = tmp_path / "fold-work"
    fold_output = fold_work_root / heldout
    assert (
        run_koopman_v21_loco._run_authorized_loco_fold(
            args=SimpleNamespace(
                role_protocol=role,
                analysis_policy=policy,
                inventory=inventory,
                split=split,
                dataset_root=tmp_path / "synthetic-dataset",
                output_root=fold_output,
                source_commit="1" * 40,
                fold=heldout,
            ),
            approval=approval,
            backend=_SyntheticFormalLocoBackend(),
        )
        == 0
    )
    freeze_path = fold_output / "fold" / "pre_test_freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze["test_open_count_at_freeze"] = 1
    freeze_path.write_bytes(_canonical_bytes(freeze))
    envelope_path = fold_output / "fold_envelope.json"
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["artifact_sha256"]["pre_test_freeze.json"] = hashlib.sha256(
        freeze_path.read_bytes()
    ).hexdigest()
    envelope_path.write_bytes(_canonical_bytes(envelope))

    with pytest.raises(ValueError, match="formal_fold_freeze_invalid"):
        run_koopman_v21_loco._assemble_authorized_loco_folds(
            args=SimpleNamespace(
                role_protocol=role,
                analysis_policy=policy,
                inventory=inventory,
                split=split,
                fold_root=fold_work_root,
                output_root=tmp_path / "evaluation",
                source_commit="1" * 40,
            ),
            approval=approval,
        )


def test_segmented_fold_keeps_failed_expert_nonpromoting_and_nonblocking(
    tmp_path: Path,
) -> None:
    role, policy, inventory, role_sha, policy_sha = _write_protocol_inputs(tmp_path)
    from koopman.evaluation_v21 import load_protocol_episode_registry_v21

    registry = load_protocol_episode_registry_v21(
        role_protocol_path=role,
        inventory_path=inventory,
    )
    split = tmp_path / "split.json"
    split.write_bytes(_canonical_bytes(registry.expected_split_payload()))

    class _FailedExpertBackend(_SyntheticFormalLocoBackend):
        def evaluate_expert(self, model, payloads):
            raise ValueError("synthetic_expert_failure")

    heldout = SUPPORTED_EMBODIMENTS[0]
    output = tmp_path / "fold"
    assert (
        run_koopman_v21_loco._run_authorized_loco_fold(
            args=SimpleNamespace(
                role_protocol=role,
                analysis_policy=policy,
                inventory=inventory,
                split=split,
                dataset_root=tmp_path / "synthetic-dataset",
                output_root=output,
                source_commit="1" * 40,
                evaluator_commit="2" * 40,
                fold=heldout,
            ),
            approval={
                "decision": "approved",
                "experiment_id": EXPERIMENT_ID,
                "role_protocol_sha256": role_sha,
                "analysis_policy_sha256": policy_sha,
            },
            backend=_FailedExpertBackend(),
        )
        == 0
    )
    expert = json.loads(
        (output / "fold" / "expert" / "expert_freeze.json").read_text(
            encoding="utf-8"
        )
    )
    envelope = json.loads(
        (output / "fold_envelope.json").read_text(encoding="utf-8")
    )
    assert expert["status"] == "failed"
    assert expert["selection_eligible"] is False
    assert expert["nonpromoting"] is True
    assert not (output / "fold" / "expert" / "selected_model.json").exists()
    assert "expert/selected_model.json" not in envelope["artifact_sha256"]


def test_formal_loco_rejects_incomplete_inventory_before_backend_or_data_open(
    tmp_path: Path,
) -> None:
    role, policy, inventory, role_sha, policy_sha = _write_protocol_inputs(tmp_path)
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    payload["episodes"].pop()
    payload.pop("inventory_sha256")
    payload["inventory_sha256"] = hashlib.sha256(
        _canonical_bytes(payload)
    ).hexdigest()
    inventory.write_bytes(_canonical_bytes(payload))
    backend = _SyntheticFormalLocoBackend()
    try:
        run_koopman_v21_loco._run_authorized_loco(
            args=SimpleNamespace(
                role_protocol=role,
                analysis_policy=policy,
                inventory=inventory,
                split=tmp_path / "missing-split.json",
                dataset_root=tmp_path / "dataset",
                output_root=tmp_path / "output",
                source_commit="1" * 40,
            ),
            approval={
                "decision": "approved",
                "experiment_id": EXPERIMENT_ID,
                "role_protocol_sha256": role_sha,
                "analysis_policy_sha256": policy_sha,
            },
            backend=backend,
        )
    except ValueError as exc:
        assert "protocol_inventory_episode_set_mismatch" in str(exc)
    else:
        raise AssertionError("incomplete inventory accepted")
    assert backend.opened_roles == []
    assert not (tmp_path / "output").exists()


def _synthetic_model_dataset(configuration: str, seed: int) -> object:
    from koopman.platform_features_v21 import declared_platform_context_v21

    rng = np.random.default_rng(seed)
    count = 96
    states = np.empty((count, 11), dtype=np.float64)
    states[:, 0] = rng.normal(size=count)
    quaternions = rng.normal(size=(count, 4))
    quaternions /= np.linalg.norm(quaternions, axis=1, keepdims=True)
    states[:, 1:5] = quaternions
    states[:, 5:] = rng.normal(size=(count, 6))
    memory = rng.normal(size=(count, 4))
    controls = rng.normal(size=(count, 4))
    targets = states.copy()
    targets[:, 0] += 0.01 * controls[:, 3]
    targets[:, 5:8] += 0.01 * controls[:, :3]
    return SimpleNamespace(
        state_11=states,
        actuator_memory_4=memory,
        virtual_control_4=controls,
        Y=targets,
        sample_count=count,
        platform_contexts=(declared_platform_context_v21(configuration),) * count,
    )


def test_default_backends_bind_official_rollout_and_distinct_exact7_exact8_conditional_scopes(
    tmp_path: Path,
) -> None:
    from koopman.evaluation_v21 import DatasetFormalLocoBackendV21
    from koopman.evaluation_v21 import ProtocolEpisodeBindingV21
    from koopman.metrics_v21 import OFFICIAL_ROLLOUT_POLICY_V21
    from koopman.model_v21 import (
        CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21,
        CONDITIONAL_POPULATION_LOCO_SOURCE7_V21,
    )
    from koopman.platform_features_v21 import (
        FINAL_REFIT_ALL8_SCOPE_V21,
        LOCO_SOURCE7_SCOPE_V21,
        build_physical_core_descriptor_v21,
        declared_platform_context_v21,
        fit_source_pca_v21,
    )
    from koopman.selection_v21 import (
        DatasetFinalRefitBackendV21,
        FinalRefitEpisodeV21,
    )

    assert DatasetFormalLocoBackendV21._rollout_policy() is OFFICIAL_ROLLOUT_POLICY_V21
    sources = tuple(SUPPORTED_EMBODIMENTS[:-1])
    projector = fit_source_pca_v21(
        {
            configuration: build_physical_core_descriptor_v21(
                [declared_platform_context_v21(configuration)]
            )
            for configuration in sources
        },
        source_configurations=sources,
    )
    fold_candidate = CandidateSpecV21(
        family="conditional",
        observable_schema="so3_identity_v1",
        data_prefix=1,
        ridge=1e-6,
        normalization="standard_v1",
        conditioning=CONDITIONING_STRUCTURED_PCA2_V21,
        label="default-fold-conditional",
    )
    loaded = tuple(
        (
            ProtocolEpisodeBindingV21(
                episode_id=f"{configuration}-fit",
                configuration=configuration,
                role="fit",
                family_repetition="synthetic-r1",
                transition_sha256=f"{index + 1:064x}",
                transition_path=f"episodes/{configuration}.jsonl",
                manifest_path=f"manifests/{configuration}.json",
                transition_count=512,
                role_protocol_sha256="a" * 64,
            ),
            _synthetic_model_dataset(configuration, 100 + index),
        )
        for index, configuration in enumerate(sources)
    )
    fold_model = DatasetFormalLocoBackendV21._fit_model(
        fold_candidate, loaded, sources, projector
    )
    assert projector.population_scope == LOCO_SOURCE7_SCOPE_V21
    assert fold_model.population_scope == CONDITIONAL_POPULATION_LOCO_SOURCE7_V21
    assert fold_model.source_configurations == sources

    final_candidate = CandidateSpecV21(
        family="conditional",
        observable_schema="so3_identity_v1",
        data_prefix=1,
        ridge=1e-6,
        normalization="standard_v1",
        conditioning=CONDITIONING_STRUCTURED_PCA2_V21,
        label="default-final-conditional",
    )
    final_episodes = tuple(
        FinalRefitEpisodeV21(
            ProtocolEpisodeBindingV21(
                episode_id=f"{configuration}-fit",
                configuration=configuration,
                role="fit",
                family_repetition="synthetic-r1",
                transition_sha256=f"{index + 101:064x}",
                transition_path=f"episodes/final-{configuration}.jsonl",
                manifest_path=f"manifests/final-{configuration}.json",
                transition_count=512,
                role_protocol_sha256="a" * 64,
            ),
            _synthetic_model_dataset(configuration, 200 + index),
        )
        for index, configuration in enumerate(SUPPORTED_EMBODIMENTS)
    )
    bundle = DatasetFinalRefitBackendV21._fit_candidate(
        final_candidate, final_episodes, use_all_rows=True
    )
    assert bundle["projector"].population_scope == FINAL_REFIT_ALL8_SCOPE_V21
    assert bundle["model"].population_scope == (
        CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21
    )
    assert bundle["model"].source_configurations == tuple(SUPPORTED_EMBODIMENTS)


def test_default_dataset_backend_rejects_source_commit_mismatch_before_model_fit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from koopman.evaluation_v21 import (
        DatasetFormalLocoBackendV21,
        ProtocolEpisodeBindingV21,
    )
    from koopman import dataset_v21, schema_v21
    from workflows import run_koopman_v21_loco, select_koopman_v21

    expected = "1" * 40
    policy_path = (
        Path(__file__).resolve().parents[1]
        / "protocols"
        / "phase8_1"
        / "analysis_policy.json"
    )
    args = SimpleNamespace(
        dataset_root=tmp_path,
        analysis_policy=policy_path,
        expected_source_commit=expected,
        source_commit=expected,
    )
    backend = run_koopman_v21_loco._default_formal_backend(
        args, expected_evidence_level="server_isaac_smoke"
    )
    final_backend = select_koopman_v21._default_final_backend(
        args, expected_evidence_level="server_isaac_smoke"
    )
    assert isinstance(backend, DatasetFormalLocoBackendV21)
    assert backend.expected_source_commit == expected
    assert backend.expected_evidence_level == "server_isaac_smoke"
    assert final_backend._loader.expected_source_commit == expected
    assert final_backend._loader.expected_evidence_level == "server_isaac_smoke"
    binding = ProtocolEpisodeBindingV21(
        episode_id="base-fit",
        configuration="base",
        role="fit",
        family_repetition="synthetic-r1",
        transition_sha256="2" * 64,
        transition_path="episodes/base.jsonl",
        manifest_path="manifests/base.json",
        transition_count=512,
        role_protocol_sha256="a" * 64,
    )
    monkeypatch.setattr(
        schema_v21,
        "validate_episode_artifact_v21",
        lambda transition, manifest: {
            "episode_id": binding.episode_id,
            "configuration": binding.configuration,
            "record_count": 512,
            "transition_sha256": binding.transition_sha256,
            "evidence_level": "server_isaac_smoke",
        },
    )
    monkeypatch.setattr(
        dataset_v21,
        "load_koopman_episode_v21",
        lambda transition, manifest: SimpleNamespace(
            episode_provenance=({"source_commit": "f" * 40},)
        ),
    )
    with pytest.raises(ValueError, match="dataset_source_commit_mismatch"):
        backend.open_episode(binding)
    assert backend._fold_contexts == {}


def test_default_backend_rejects_self_consistent_local_contract_artifact_before_fit(
    tmp_path: Path,
) -> None:
    from koopman.evaluation_v21 import ProtocolEpisodeBindingV21
    from koopman.schema_v21 import (
        KOOPMAN_TRANSITION_SCHEMA_V21,
        KoopmanEpisodeLoggerV21,
    )

    expected_commit = "1" * 40
    dataset_root = tmp_path / "dataset"
    transition_path = dataset_root / "episodes" / "base.jsonl"
    manifest_path = dataset_root / "manifests" / "base.json"
    source_path = (
        Path(__file__).parent
        / "fixtures"
        / "koopman_v2_three_topologies"
        / "base.jsonl"
    )
    templates = [
        json.loads(line)
        for line in source_path.read_text(encoding="utf-8").splitlines()
    ]
    tau_s = float(
        templates[0]["platform_context"]["thruster_dynamics_time_constant_s"]
    )
    control_dt_s = float(templates[0]["episode_provenance"]["control_dt_s"])
    alpha = math.exp(-control_dt_s / tau_s)
    memory = np.zeros(4, dtype=np.float64)
    episode_id = "base-fit-local-substitution"
    rows = []
    for step in range(512):
        row = json.loads(json.dumps(templates[0]))
        if rows:
            row["state_11"] = list(rows[-1]["next_state_11"])
            row["next_state_11"] = list(row["state_11"])
        row["schema_version"] = KOOPMAN_TRANSITION_SCHEMA_V21
        row["actuator_memory_4"] = memory.tolist()
        provenance = row["episode_provenance"]
        provenance.update(
            {
                "configuration": "base",
                "episode_id": episode_id,
                "source_commit": expected_commit,
                "evidence_level": "local_contract",
                "physics_dt_s": control_dt_s / 2,
                "decimation": 2,
                "step_index": step,
                "simulation_time_s": step * control_dt_s,
            }
        )
        memory = alpha * memory + (1.0 - alpha) * np.asarray(
            row["virtual_control_4"], dtype=np.float64
        )
        rows.append(row)
    with KoopmanEpisodeLoggerV21(
        transition_path,
        manifest_path=manifest_path,
        runtime_provenance={
            "artifact_origin": "local_contract",
            "generator": "synthetic-evidence-level-mutation",
        },
    ) as logger:
        for row in rows:
            logger.write(row)
        manifest = logger.finalize()
    binding = ProtocolEpisodeBindingV21(
        episode_id=episode_id,
        configuration="base",
        role="fit",
        family_repetition="synthetic-r1",
        transition_sha256=manifest["transition_sha256"],
        transition_path="episodes/base.jsonl",
        manifest_path="manifests/base.json",
        transition_count=len(rows),
        role_protocol_sha256="a" * 64,
    )
    policy_path = (
        Path(__file__).resolve().parents[1]
        / "protocols"
        / "phase8_1"
        / "analysis_policy.json"
    )
    backend = run_koopman_v21_loco._default_formal_backend(
        SimpleNamespace(
            dataset_root=dataset_root,
            analysis_policy=policy_path,
            source_commit=expected_commit,
        ),
        expected_evidence_level="server_isaac_smoke",
    )
    with pytest.raises(ValueError, match="dataset_evidence_level_mismatch"):
        backend.open_episode(binding)
    assert backend._cache == {}
    assert backend._fold_contexts == {}
