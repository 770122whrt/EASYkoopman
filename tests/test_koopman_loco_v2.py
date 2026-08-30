"""Contracts for seven-source decisions, six roles and held-out sealing."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

import koopman.loco_v2 as loco_v2
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.collection_v2 import DatasetInventoryV2, EpisodeInventoryEntryV2
from koopman.loco_v2 import (
    CandidateValidationResultV2,
    DiagnosticRoleResultV2,
    FoldExecutionV2,
    FrozenPrimaryStateV2,
    ModelRoleV2,
    ReferenceDiagnosticResultV2,
    RoleOutcomeV2,
    SelectionEligibleRoleResultV2,
    authorize_primary_test_access_v2,
    candidate_grid_v2,
    validate_fold_model_binding_v2,
)
from koopman.protocol_v2 import (
    ANALYSIS_POLICY_VERSION_V1,
    AnalysisPolicyV2,
    analysis_policy_from_mapping_v1,
    load_analysis_policy_v1,
    validate_analysis_policy_v1,
)
from koopman.splits_v2 import (
    ExpertLOCOViewV2,
    LOCOFoldManifestV2,
    PrimaryLOCOViewV2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "koopman_phase8_synthetic_system"
    / "analysis_policy_v1.json"
)
CANONICAL_POLICY_PATH = PROJECT_ROOT / "protocols" / "phase8" / "analysis_policy.json"
PRIMARY_SOURCE_SCORE_METRICS = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)


def _inventory() -> DatasetInventoryV2:
    entries: list[EpisodeInventoryEntryV2] = []
    for configuration in SUPPORTED_EMBODIMENTS:
        for role in ("fit", "validation", "test"):
            episode_id = f"synthetic-{configuration}-{role}"
            entries.append(
                EpisodeInventoryEntryV2(
                    configuration=configuration,
                    episode_id=episode_id,
                    role=role,
                    scenario=f"synthetic-{role}",
                    seed=len(entries) + 1,
                    transition_count=64,
                    transition_path=f"episodes/{episode_id}.jsonl",
                    manifest_path=f"manifests/{episode_id}.manifest.json",
                    transition_sha256=hashlib.sha256(
                        f"transition-{episode_id}".encode("utf-8")
                    ).hexdigest(),
                    manifest_sha256=hashlib.sha256(
                        f"manifest-{episode_id}".encode("utf-8")
                    ).hexdigest(),
                    transition_size_bytes=64,
                    manifest_size_bytes=64,
                    record_count=64,
                    platform_context_sha256=hashlib.sha256(
                        f"platform-{configuration}".encode("utf-8")
                    ).hexdigest(),
                    evidence_level="local_contract",
                )
            )
    return DatasetInventoryV2(
        entries=tuple(entries),
        role_protocol_sha256="8" * 64,
        source_commit="7" * 40,
        runtime_sha256="6" * 64,
        envelope_sha256=None,
        qualification_level="local_contract",
        inventory_sha256="9" * 64,
    )


def _fold(inventory: DatasetInventoryV2, holdout: str) -> LOCOFoldManifestV2:
    sources = tuple(item for item in SUPPORTED_EMBODIMENTS if item != holdout)
    source_entries = tuple(
        entry
        for entry in inventory.entries
        if entry.configuration in sources and entry.role in {"fit", "validation"}
    )
    heldout_test = tuple(
        entry
        for entry in inventory.entries
        if entry.configuration == holdout and entry.role == "test"
    )
    expert = tuple(
        entry
        for entry in inventory.entries
        if entry.configuration == holdout and entry.role in {"fit", "validation"}
    )
    return LOCOFoldManifestV2(
        fold_id=f"loco-holdout-{holdout}",
        holdout_configuration=holdout,
        source_configurations=sources,
        primary_source_episode_ids=tuple(entry.episode_id for entry in source_entries),
        primary_heldout_test_episode_ids=tuple(entry.episode_id for entry in heldout_test),
        expert_fit_validation_episode_ids=tuple(entry.episode_id for entry in expert),
        expert_test_episode_ids=tuple(entry.episode_id for entry in heldout_test),
        source_episode_sha256s=tuple(entry.transition_sha256 for entry in source_entries),
        sealed_heldout_digest=hashlib.sha256(
            f"sealed-{holdout}".encode("utf-8")
        ).hexdigest(),
        inventory_sha256=inventory.inventory_sha256,
        role_protocol_sha256=inventory.role_protocol_sha256,
    )


def _views(fold: LOCOFoldManifestV2):
    primary = PrimaryLOCOViewV2(
        fold_id=fold.fold_id,
        holdout_configuration=fold.holdout_configuration,
        source_configurations=fold.source_configurations,
        decision_episode_ids=fold.primary_source_episode_ids,
        outer_test_episode_ids=fold.primary_heldout_test_episode_ids,
        inventory_sha256=fold.inventory_sha256,
    )
    expert = ExpertLOCOViewV2(
        fold_id=fold.fold_id,
        holdout_configuration=fold.holdout_configuration,
        decision_episode_ids=fold.expert_fit_validation_episode_ids,
        test_episode_ids=fold.expert_test_episode_ids,
        inventory_sha256=fold.inventory_sha256,
    )
    return primary, expert


def _policy() -> AnalysisPolicyV2:
    return load_analysis_policy_v1(POLICY_PATH)


def _candidate_result(candidate, opened, fold):
    preferred = (
        candidate.data_prefix == 4
        and candidate.observable_schema == "identity_v1"
        and candidate.ridge == pytest.approx(1.0e-8)
        and candidate.normalization == "none"
        and candidate.platform_schema
        in {"none", "platform_physical_compact_v1"}
    )
    penalty = 0.0 if preferred else 1.0
    scores = {
        configuration: penalty + 0.01 * index
        for index, configuration in enumerate(fold.source_configurations)
    }
    base_width = 16 if candidate.observable_schema == "identity_v1" else 44
    platform_dimension = {
        "none": 0,
        "platform_physical_compact_v1": 11,
        "platform_physical_core_v1": 19,
    }[candidate.platform_schema]
    design_width = (
        base_width
        if platform_dimension == 0
        else base_width + platform_dimension + platform_dimension * base_width
    )
    return CandidateValidationResultV2(
        candidate=candidate,
        budget_data_prefix=candidate.data_prefix,
        source_scores=scores,
        source_episode_sha256s=fold.source_episode_sha256s,
        design_rank=design_width,
        design_width=design_width,
        condition_number=10.0 + penalty,
        converged=True,
        platform_normalizer_sha256=(
            None
            if candidate.platform_schema == "none"
            else hashlib.sha256(candidate.candidate_id.encode("utf-8")).hexdigest()
        ),
    )


def _session(holdout: str = "base"):
    inventory = _inventory()
    fold = _fold(inventory, holdout)
    primary, expert = _views(fold)
    return (
        FoldExecutionV2(
            fold=fold,
            primary_view=primary,
            inventory=inventory,
            policy=_policy(),
        ),
        expert,
    )


def _seal(session: FoldExecutionV2, *, path: Path | None = None):
    return session.seal_decision(
        source_opener=lambda entry: entry,
        candidate_evaluator=_candidate_result,
        sealed_at="2026-08-24T00:00:00Z",
        output_path=path,
    )


def _test_token(session: FoldExecutionV2):
    assert session.decision is not None
    frozen = FrozenPrimaryStateV2(
        fold_id=session.fold.fold_id,
        holdout_configuration=session.fold.holdout_configuration,
        source_configurations=session.fold.source_configurations,
        source_episode_sha256s=session.fold.source_episode_sha256s,
        candidate_id=session.decision.candidate_id,
        decision_sha256=session.decision.decision_sha256,
        analysis_policy_sha256=session.decision.analysis_policy_sha256,
        primary_model_sha256s={
            ModelRoleV2.POOLED.value: "1" * 64,
            ModelRoleV2.CONDITIONAL.value: "2" * 64,
        },
        frozen_at="2026-08-29T00:00:00Z",
    )
    return authorize_primary_test_access_v2(
        frozen,
        analysis_policy=_policy(),
        fold_id=session.fold.fold_id,
        holdout_configuration=session.fold.holdout_configuration,
        test_episode_ids=session.fold.primary_heldout_test_episode_ids,
    )


def test_analysis_policy_is_exact_local_fixture_not_canonical_approval() -> None:
    policy = _policy()
    assert policy.version == ANALYSIS_POLICY_VERSION_V1
    assert policy.qualification_level == "local_contract"
    assert policy.approval_status == "local_fixture_only_not_d23"
    assert policy.data_prefixes == (2, 4, 6)
    assert policy.observable_candidates == ("identity_v1", "auv_kinematic_v1")
    assert policy.horizons == (5, 20, 60, "full")
    assert policy.reference_diagnostic["selection_eligible"] is False
    assert policy.policy_sha256 == _policy().policy_sha256
    assert len(candidate_grid_v2(policy)) == 108


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda value: value.update(extra=True), "analysis_policy_field_set_mismatch"),
        (
            lambda value: value["forbidden_inputs"].remove("reference_5"),
            "analysis_policy_forbidden_input_mismatch",
        ),
        (
            lambda value: value.update(ridge_grid=[0.0, float("nan")]),
            "analysis_policy_ridge_invalid",
        ),
        (
            lambda value: value["reference_diagnostic"].update(selection_eligible=True),
            "reference_diagnostic_not_eligible",
        ),
    ],
)
def test_analysis_policy_mutations_fail_closed(mutation, reason) -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    mutation(payload)
    with pytest.raises(ValueError, match=reason):
        validate_analysis_policy_v1(payload)


def test_canonical_policy_freezes_robust_relative_source_score_and_disables_reference() -> None:
    payload = json.loads(CANONICAL_POLICY_PATH.read_text(encoding="utf-8"))
    validate_analysis_policy_v1(payload)

    source_score = payload["inner_decision_algorithm"]["source_score"]
    assert source_score == {
        "aggregation": "equal_configuration_macro",
        "baseline_reference": "minimum_error",
        "denominator_zero": {
            "candidate_positive": "candidate_ineligible",
            "candidate_zero": "ratio_one",
        },
        "direction": "lower_is_better",
        "group_reduction": "maximum",
        "horizon": "full",
        "name": "robust_relative_max_ratio_v1",
        "primary_metric_groups": list(PRIMARY_SOURCE_SCORE_METRICS),
    }
    assert "weights" not in source_score
    assert payload["reference_diagnostic"]["enabled"] is False


def test_robust_relative_source_score_uses_stronger_baseline_and_max_group() -> None:
    candidate = dict.fromkeys(PRIMARY_SOURCE_SCORE_METRICS, 1.0)
    persistence = dict.fromkeys(PRIMARY_SOURCE_SCORE_METRICS, 2.0)
    simple_linear = dict.fromkeys(PRIMARY_SOURCE_SCORE_METRICS, 2.0)
    candidate["depth_rmse"] = 2.0
    persistence["depth_rmse"] = 4.0
    simple_linear["depth_rmse"] = 3.0
    candidate["linear_velocity_rmse"] = 4.0
    persistence["linear_velocity_rmse"] = 8.0
    simple_linear["linear_velocity_rmse"] = 10.0

    score = loco_v2.robust_relative_source_score_v2(
        candidate,
        persistence,
        simple_linear,
        primary_metric_groups=PRIMARY_SOURCE_SCORE_METRICS,
    )

    assert score == pytest.approx(2.0 / 3.0)


def test_robust_relative_source_score_defines_zero_denominator_without_epsilon() -> None:
    zero = dict.fromkeys(PRIMARY_SOURCE_SCORE_METRICS, 0.0)
    assert loco_v2.robust_relative_source_score_v2(
        zero,
        zero,
        zero,
        primary_metric_groups=PRIMARY_SOURCE_SCORE_METRICS,
    ) == pytest.approx(1.0)

    positive = dict(zero)
    positive["depth_rmse"] = 0.1
    with pytest.raises(ValueError, match="source_score_reference_zero_candidate_positive"):
        loco_v2.robust_relative_source_score_v2(
            positive,
            zero,
            zero,
            primary_metric_groups=PRIMARY_SOURCE_SCORE_METRICS,
        )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda value: value["inner_decision_algorithm"].pop("source_score"),
            "analysis_policy_field_set_mismatch",
        ),
        (
            lambda value: value["inner_decision_algorithm"]["source_score"].update(
                weights=[1.0] * len(PRIMARY_SOURCE_SCORE_METRICS)
            ),
            "analysis_policy_field_set_mismatch",
        ),
        (
            lambda value: value["reference_diagnostic"].update(enabled=True),
            "reference_diagnostic_not_disabled",
        ),
    ],
)
def test_canonical_source_score_semantic_mutations_fail_closed(mutation, reason) -> None:
    payload = json.loads(CANONICAL_POLICY_PATH.read_text(encoding="utf-8"))
    mutation(payload)
    with pytest.raises(ValueError, match=reason):
        validate_analysis_policy_v1(payload)


def test_fold_decision_opens_exactly_seven_sources_and_seals_before_test(tmp_path) -> None:
    session, _ = _session("base")
    path = tmp_path / "folds" / "base" / "fold_protocol_decision.json"
    decision = _seal(session, path=path)

    assert path.exists()
    assert decision.source_configurations == session.fold.source_configurations
    assert len(decision.source_configurations) == 7
    assert decision.source_episode_sha256s == session.fold.source_episode_sha256s
    assert set(decision.selected_candidates) == {
        ModelRoleV2.POOLED.value,
        ModelRoleV2.CONDITIONAL.value,
    }
    pooled = decision.selected_candidates[ModelRoleV2.POOLED.value]
    conditional = decision.selected_candidates[ModelRoleV2.CONDITIONAL.value]
    assert pooled.data_prefix == conditional.data_prefix == 4
    assert pooled.observable_schema == conditional.observable_schema == "identity_v1"
    assert pooled.ridge == conditional.ridge == pytest.approx(1.0e-8)
    assert pooled.normalization == conditional.normalization == "none"
    assert pooled.platform_schema == "none"
    assert conditional.platform_schema == "platform_physical_compact_v1"
    assert decision.diagnostics[ModelRoleV2.POOLED.value]["design_rank"] == 16
    assert decision.diagnostics[ModelRoleV2.CONDITIONAL.value]["design_rank"] == 203
    assert decision.test_open_count_at_seal == 0
    assert session.test_accesses == ()
    assert {record.configuration for record in session.dataset_accesses} == set(
        session.fold.source_configurations
    )
    assert session.fold.holdout_configuration not in {
        record.configuration for record in session.dataset_accesses
    }
    assert {record.configuration for record in session.statistic_accesses} == set(
        session.fold.source_configurations
    )


def test_all_eight_synthetic_folds_decide_before_any_heldout_test_open(tmp_path) -> None:
    decisions = []
    for holdout in SUPPORTED_EMBODIMENTS:
        session, _ = _session(holdout)
        decisions.append(
            _seal(session, path=tmp_path / holdout / "fold_protocol_decision.json")
        )
        assert session.test_accesses == ()
        assert len({record.configuration for record in session.dataset_accesses}) == 7
        assert holdout not in {record.configuration for record in session.dataset_accesses}
    assert tuple(decision.holdout_configuration for decision in decisions) == tuple(
        SUPPORTED_EMBODIMENTS
    )
    assert len({decision.decision_sha256 for decision in decisions}) == 8


def test_one_unavailable_family_is_reason_coded_without_fallback_candidate() -> None:
    session, _ = _session("base")

    def conditional_unavailable(candidate, opened, fold):
        result = _candidate_result(candidate, opened, fold)
        return replace(
            result,
            converged=candidate.platform_schema == "none" and result.converged,
        )

    decision = session.seal_decision(
        source_opener=lambda entry: entry,
        candidate_evaluator=conditional_unavailable,
        sealed_at="2026-08-30T00:00:00Z",
    )

    assert decision.selected_candidates[ModelRoleV2.POOLED.value] is not None
    assert decision.selected_candidates[ModelRoleV2.CONDITIONAL.value] is None
    assert decision.diagnostics[ModelRoleV2.CONDITIONAL.value] == {
        "reason_code": "source_candidate_unavailable",
        "status": "failed",
    }
    with pytest.raises(ValueError, match="source_candidate_unavailable"):
        validate_fold_model_binding_v2(
            decision,
            SimpleNamespace(),
            family=ModelRoleV2.CONDITIONAL,
        )


def test_test_open_before_decision_and_post_test_retune_fail_closed() -> None:
    session, _ = _session()
    with pytest.raises(ValueError, match="fold_decision_missing"):
        session.open_primary_test(test_opener=lambda entry: entry, policy=_policy())
    _seal(session)
    with pytest.raises(ValueError, match="primary_freeze_missing"):
        session.open_primary_test(test_opener=lambda entry: entry, policy=_policy())
    opened = session.open_primary_test(
        test_opener=lambda entry: entry,
        policy=_policy(),
        access_token=_test_token(session),
    )
    assert len(opened) == 1
    assert opened[0].configuration == session.fold.holdout_configuration
    with pytest.raises(ValueError, match="post_test_retune"):
        _seal(session)


def test_heldout_statistic_different_budget_and_policy_drift_fail_closed() -> None:
    session, _ = _session()

    def heldout_result(candidate, opened, fold):
        result = _candidate_result(candidate, opened, fold)
        return replace(
            result,
            source_scores={
                **dict(result.source_scores),
                fold.holdout_configuration: 0.0,
            },
        )

    with pytest.raises(ValueError, match="heldout_statistic_access"):
        session.seal_decision(
            source_opener=lambda entry: entry,
            candidate_evaluator=heldout_result,
            sealed_at="2026-08-24T00:00:00Z",
        )

    session, _ = _session()

    def wrong_budget(candidate, opened, fold):
        return replace(
            _candidate_result(candidate, opened, fold),
            budget_data_prefix=6 if candidate.data_prefix != 6 else 4,
        )

    with pytest.raises(ValueError, match="different_budget"):
        session.seal_decision(
            source_opener=lambda entry: entry,
            candidate_evaluator=wrong_budget,
            sealed_at="2026-08-24T00:00:00Z",
        )

    session, _ = _session()
    _seal(session)
    mutated = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    mutated["ridge_grid"].append(0.01)
    changed_policy = analysis_policy_from_mapping_v1(mutated)
    with pytest.raises(ValueError, match="analysis_policy_drift"):
        session.open_primary_test(
            test_opener=lambda entry: entry,
            policy=changed_policy,
            access_token=_test_token(session),
        )


def test_stale_normalizer_or_model_binding_is_rejected() -> None:
    session, _ = _session()
    decision = _seal(session)
    selected = decision.selected_candidates[ModelRoleV2.CONDITIONAL.value]
    valid_model = SimpleNamespace(
        fold_id=decision.fold_id,
        observable_schema=selected.observable_schema,
        ridge=selected.ridge,
        normalization=selected.normalization,
        conditioning="platform_affine",
        platform_normalizer_sha256=decision.platform_normalizer_sha256s[
            ModelRoleV2.CONDITIONAL.value
        ],
    )
    validate_fold_model_binding_v2(
        decision, valid_model, family=ModelRoleV2.CONDITIONAL
    )
    with pytest.raises(ValueError, match="stale_normalizer"):
        validate_fold_model_binding_v2(
            decision,
            SimpleNamespace(
                **{
                    **vars(valid_model),
                    "platform_normalizer_sha256": "0" * 64,
                }
            ),
            family=ModelRoleV2.CONDITIONAL,
        )
    with pytest.raises(ValueError, match="fold_model_binding_mismatch"):
        validate_fold_model_binding_v2(
            decision,
            SimpleNamespace(**{**vars(valid_model), "ridge": 0.5}),
            family=ModelRoleV2.CONDITIONAL,
        )

    pooled = decision.selected_candidates[ModelRoleV2.POOLED.value]
    validate_fold_model_binding_v2(
        decision,
        SimpleNamespace(
            fold_id=decision.fold_id,
            observable_schema=pooled.observable_schema,
            ridge=pooled.ridge,
            normalization=pooled.normalization,
            conditioning="none",
            platform_normalizer_sha256=None,
        ),
        family=ModelRoleV2.POOLED,
    )


def test_six_roles_have_exact_eligibility_and_reference_is_non_promoting() -> None:
    session, expert_view = _session()
    decision = _seal(session)
    session.open_expert_decision(
        expert_view=expert_view,
        expert_opener=lambda entry: entry,
    )
    session.open_primary_test(
        test_opener=lambda entry: entry,
        policy=_policy(),
        access_token=_test_token(session),
    )

    def runner(role, fit_payloads, test_payloads, fold_decision):
        assert fold_decision.decision_sha256 == decision.decision_sha256
        assert test_payloads
        if role == ModelRoleV2.PERSISTENCE:
            assert fit_payloads == ()
        if role == ModelRoleV2.HELDOUT_EXPERT:
            assert all(entry.configuration == session.fold.holdout_configuration for entry in fit_payloads)
        return RoleOutcomeV2(
            status="success",
            reason_code=None,
            artifact_sha256=hashlib.sha256(role.value.encode("utf-8")).hexdigest(),
        )

    matrix = session.run_roles(
        role_runner=runner,
        reference_runner=lambda fit_payloads, test_payloads, fold_decision: RoleOutcomeV2(
            status="success",
            reason_code=None,
            artifact_sha256="5" * 64,
        ),
    )
    assert tuple(result.role for result in matrix.results) == tuple(ModelRoleV2)
    assert tuple(result.role for result in matrix.eligible_results) == (
        ModelRoleV2.POOLED,
        ModelRoleV2.CONDITIONAL,
    )
    assert all(
        isinstance(result, SelectionEligibleRoleResultV2)
        for result in matrix.eligible_results
    )
    assert all(
        isinstance(result, DiagnosticRoleResultV2)
        for result in matrix.results
        if result.role not in {ModelRoleV2.POOLED, ModelRoleV2.CONDITIONAL}
    )
    assert isinstance(matrix.reference_diagnostic, ReferenceDiagnosticResultV2)
    assert matrix.reference_diagnostic.selection_eligible is False
    assert matrix.reference_diagnostic.namespace == "diagnostic/reference_conditioned_v2"
    assert matrix.reference_diagnostic not in matrix.eligible_results


def test_every_role_is_success_or_reason_coded_failure_under_one_contract() -> None:
    session, expert_view = _session()
    decision = _seal(session)
    session.open_expert_decision(expert_view=expert_view, expert_opener=lambda entry: entry)
    session.open_primary_test(
        test_opener=lambda entry: entry,
        policy=_policy(),
        access_token=_test_token(session),
    )

    def runner(role, fit_payloads, test_payloads, fold_decision):
        if role == ModelRoleV2.SOURCE_PER_CONFIGURATION:
            return RoleOutcomeV2(
                status="failed",
                reason_code="regressor_rank_insufficient",
                artifact_sha256="4" * 64,
            )
        return RoleOutcomeV2(
            status="success",
            reason_code=None,
            artifact_sha256=hashlib.sha256(role.value.encode("utf-8")).hexdigest(),
        )

    matrix = session.run_roles(role_runner=runner)
    assert len(matrix.results) == 6
    assert all(
        (result.status == "success" and result.reason_code is None)
        or (result.status == "failed" and result.reason_code)
        for result in matrix.results
    )
    assert {result.analysis_policy_sha256 for result in matrix.results} == {
        decision.analysis_policy_sha256
    }
    assert {result.metric_policy_sha256 for result in matrix.results} == {
        decision.metric_policy_sha256
    }
    assert {result.budget_sha256 for result in matrix.results} == {
        decision.budget_sha256
    }


def test_expert_or_reference_cannot_be_constructed_as_selection_eligible() -> None:
    session, _ = _session()
    decision = _seal(session)
    common = {
        "fold_id": decision.fold_id,
        "analysis_policy_sha256": decision.analysis_policy_sha256,
        "metric_policy_sha256": decision.metric_policy_sha256,
        "budget_sha256": decision.budget_sha256,
        "decision_sha256": decision.decision_sha256,
        "status": "success",
        "reason_code": None,
        "artifact_sha256": "1" * 64,
    }
    with pytest.raises(ValueError, match="expert_promotion_forbidden"):
        SelectionEligibleRoleResultV2(
            role=ModelRoleV2.HELDOUT_EXPERT,
            selection_eligible=True,
            **common,
        )
    with pytest.raises(ValueError, match="reference_diagnostic_not_eligible"):
        ReferenceDiagnosticResultV2(
            namespace="diagnostic/reference_conditioned_v2",
            selection_eligible=True,
            **common,
        )


def test_cli_exposes_strict_inventory_split_policy_output_and_fold_arguments() -> None:
    completed = subprocess.run(
        [sys.executable, "workflows/run_koopman_v2_loco.py", "--help"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    for flag in (
        "--inventory",
        "--split",
        "--analysis-policy",
        "--output-root",
        "--fold",
    ):
        assert flag in completed.stdout
    source = (PROJECT_ROOT / "workflows" / "run_koopman_v2_loco.py").read_text(
        encoding="utf-8"
    )
    assert "selection" not in source.lower()
