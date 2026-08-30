"""Sealed, source-only LOCO orchestration for the additive v2 backend.

This module owns protocol mechanics only.  It never opens canonical Phase 8
roots and never treats the expert or reference namespaces as promotable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
import math
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from koopman.collection_v2 import DatasetInventoryV2, EpisodeInventoryEntryV2
from koopman.evidence_v2 import canonical_json_bytes, canonical_sha256
from koopman.protocol_v2 import AnalysisPolicyV2, SOURCE_SCORE_PRIMARY_METRICS_V2
from koopman.splits_v2 import (
    ExpertLOCOViewV2,
    LOCOFoldManifestV2,
    OpenedArtifactRecordV2,
    PrimaryLOCOViewV2,
    load_primary_decision_view_v2,
    validate_primary_access_audit_v2,
)


FOLD_PROTOCOL_DECISION_VERSION_V2 = "phase8-fold-protocol-decision-v2"
FOLD_PROTOCOL_DECISION_FILENAME_V1 = "fold_protocol_decision.json"
_REFERENCE_NAMESPACE = "diagnostic/reference_conditioned_v2"
_PRIMARY_KOOPMAN_FAMILIES = (
    "pooled_koopman_v2",
    "conditional_koopman_v2",
)
T = TypeVar("T")


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _sha(value: str, path: str, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or len(value) != 64:
        _fail("artifact_hash_invalid", path)
    try:
        int(value, 16)
    except ValueError:
        _fail("artifact_hash_invalid", path)


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class CandidateSpecV2:
    """One deterministic point in the predeclared inner-decision grid."""

    data_prefix: int
    observable_schema: str
    ridge: float
    normalization: str
    platform_schema: str
    candidate_id: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.data_prefix, bool) or self.data_prefix <= 0:
            _fail("candidate_budget_invalid")
        if not math.isfinite(self.ridge) or self.ridge < 0.0:
            _fail("candidate_ridge_invalid")
        object.__setattr__(self, "ridge", float(self.ridge))
        object.__setattr__(self, "candidate_id", canonical_sha256(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_prefix": self.data_prefix,
            "normalization": self.normalization,
            "observable_schema": self.observable_schema,
            "platform_schema": self.platform_schema,
            "ridge": self.ridge,
        }


def candidate_grid_v2(policy: AnalysisPolicyV2) -> tuple[CandidateSpecV2, ...]:
    """Expand the policy in its declared, deterministic tie-break order."""

    return tuple(
        CandidateSpecV2(prefix, observable, ridge, normalization, platform)
        for prefix in policy.data_prefixes
        for observable in policy.observable_candidates
        for ridge in policy.ridge_grid
        for normalization in policy.normalization_candidates
        for platform in policy.platform_schema_candidates
    )


def robust_relative_source_score_v2(
    candidate_errors: Mapping[str, float],
    persistence_errors: Mapping[str, float],
    simple_linear_errors: Mapping[str, float],
    *,
    primary_metric_groups: tuple[str, ...],
) -> float:
    """Return the frozen unweighted worst relative source-validation error.

    Inputs are the already aggregated full-horizon errors for one source
    configuration.  A zero reference and zero candidate is exact parity and
    therefore has ratio one.  A positive candidate error against a zero
    reference is ineligible instead of being softened with an epsilon.
    """

    groups = tuple(primary_metric_groups)
    if groups != SOURCE_SCORE_PRIMARY_METRICS_V2:
        _fail("source_score_metric_group_mismatch")
    expected = set(groups)
    if any(set(values) != expected for values in (
        candidate_errors,
        persistence_errors,
        simple_linear_errors,
    )):
        _fail("source_score_metric_group_mismatch")
    ratios: list[float] = []
    for group in groups:
        values = tuple(
            float(errors[group])
            for errors in (candidate_errors, persistence_errors, simple_linear_errors)
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            _fail("source_score_error_invalid", group)
        candidate_error, persistence_error, simple_linear_error = values
        reference = min(persistence_error, simple_linear_error)
        if reference == 0.0:
            if candidate_error > 0.0:
                _fail("source_score_reference_zero_candidate_positive", group)
            ratios.append(1.0)
        else:
            ratios.append(candidate_error / reference)
    return max(ratios)


@dataclass(frozen=True)
class CandidateValidationResultV2:
    candidate: CandidateSpecV2
    budget_data_prefix: int
    source_scores: Mapping[str, float]
    source_episode_sha256s: tuple[str, ...]
    design_rank: int
    design_width: int
    condition_number: float
    converged: bool
    platform_normalizer_sha256: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_scores", _frozen_mapping(self.source_scores))
        object.__setattr__(self, "source_episode_sha256s", tuple(self.source_episode_sha256s))
        if (
            isinstance(self.design_rank, bool)
            or isinstance(self.design_width, bool)
            or self.design_rank < 0
            or self.design_width <= 0
            or self.design_rank > self.design_width
        ):
            _fail("candidate_design_invalid")
        if not math.isfinite(self.condition_number) or self.condition_number < 0.0:
            _fail("candidate_condition_invalid")
        for configuration, score in self.source_scores.items():
            if not isinstance(configuration, str) or not math.isfinite(float(score)):
                _fail("candidate_source_score_invalid")
        if self.platform_normalizer_sha256 is not None:
            _sha(self.platform_normalizer_sha256, "platform_normalizer_sha256")


@dataclass(frozen=True)
class StatisticAccessRecordV2:
    candidate_id: str
    configuration: str
    episode_sha256s: tuple[str, ...]
    statistic: str = "full_equal_configuration_validation"


@dataclass(frozen=True)
class FoldProtocolDecisionV2:
    fold_id: str
    holdout_configuration: str
    source_configurations: tuple[str, ...]
    source_episode_sha256s: tuple[str, ...]
    selected_candidates: Mapping[str, CandidateSpecV2]
    diagnostics: Mapping[str, Any]
    source_gates: Mapping[str, Any]
    sealed_at: str
    inventory_sha256: str
    analysis_policy_sha256: str
    metric_policy_sha256: str
    budget_sha256: str
    platform_normalizer_sha256s: Mapping[str, str | None]
    test_open_count_at_seal: int = 0
    version: str = FOLD_PROTOCOL_DECISION_VERSION_V2
    candidate_id: str = field(init=False)
    decision_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_configurations", tuple(self.source_configurations))
        object.__setattr__(self, "source_episode_sha256s", tuple(self.source_episode_sha256s))
        selected = dict(self.selected_candidates)
        normalizers = dict(self.platform_normalizer_sha256s)
        if tuple(selected) != _PRIMARY_KOOPMAN_FAMILIES or set(normalizers) != set(
            _PRIMARY_KOOPMAN_FAMILIES
        ):
            _fail("primary_candidate_family_set_mismatch")
        if (
            not isinstance(selected[_PRIMARY_KOOPMAN_FAMILIES[0]], CandidateSpecV2)
            or selected[_PRIMARY_KOOPMAN_FAMILIES[0]].platform_schema != "none"
            or not isinstance(selected[_PRIMARY_KOOPMAN_FAMILIES[1]], CandidateSpecV2)
            or selected[_PRIMARY_KOOPMAN_FAMILIES[1]].platform_schema == "none"
        ):
            _fail("primary_candidate_family_binding_mismatch")
        if normalizers[_PRIMARY_KOOPMAN_FAMILIES[0]] is not None:
            _fail("pooled_normalizer_forbidden")
        if normalizers[_PRIMARY_KOOPMAN_FAMILIES[1]] is None:
            _fail("conditional_normalizer_missing")
        object.__setattr__(self, "selected_candidates", MappingProxyType(selected))
        object.__setattr__(self, "platform_normalizer_sha256s", MappingProxyType(normalizers))
        object.__setattr__(self, "diagnostics", _frozen_mapping(self.diagnostics))
        object.__setattr__(self, "source_gates", _frozen_mapping(self.source_gates))
        for name in (
            "inventory_sha256",
            "analysis_policy_sha256",
            "metric_policy_sha256",
            "budget_sha256",
        ):
            _sha(getattr(self, name), name)
        for family, normalizer_sha256 in normalizers.items():
            if normalizer_sha256 is not None:
                _sha(normalizer_sha256, f"platform_normalizer_sha256s.{family}")
        if self.test_open_count_at_seal != 0:
            _fail("heldout_test_open_at_seal")
        object.__setattr__(
            self,
            "candidate_id",
            canonical_sha256(
                {
                    family: candidate.candidate_id
                    for family, candidate in selected.items()
                }
            ),
        )
        object.__setattr__(self, "decision_sha256", canonical_sha256(self.to_dict()))

    def to_dict(self, *, include_sha256: bool = False) -> dict[str, Any]:
        value = {
            "analysis_policy_sha256": self.analysis_policy_sha256,
            "budget_sha256": self.budget_sha256,
            "diagnostics": dict(self.diagnostics),
            "fold_id": self.fold_id,
            "holdout_configuration": self.holdout_configuration,
            "inventory_sha256": self.inventory_sha256,
            "metric_policy_sha256": self.metric_policy_sha256,
            "candidate_id": self.candidate_id,
            "platform_normalizer_sha256s": dict(self.platform_normalizer_sha256s),
            "sealed_at": self.sealed_at,
            "selected_candidates": {
                family: candidate.to_dict() | {"candidate_id": candidate.candidate_id}
                for family, candidate in self.selected_candidates.items()
            },
            "source_configurations": list(self.source_configurations),
            "source_episode_sha256s": list(self.source_episode_sha256s),
            "source_gates": dict(self.source_gates),
            "test_open_count_at_seal": self.test_open_count_at_seal,
            "version": self.version,
        }
        if include_sha256:
            value["decision_sha256"] = self.decision_sha256
        return value


def _write_decision(decision: FoldProtocolDecisionV2, path: str | Path) -> None:
    target = Path(path)
    part = target.with_name(f"{target.name}.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or part.exists():
        _fail("artifact_exists", str(target if target.exists() else part))
    try:
        with part.open("xb") as stream:
            stream.write(canonical_json_bytes(decision.to_dict(include_sha256=True)))
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            _fail("artifact_exists", str(target))
        os.replace(part, target)
    finally:
        if part.exists():
            part.unlink()


class ModelRoleV2(Enum):
    PERSISTENCE = "persistence"
    SIMPLE_LINEAR = "simple_linear_v2"
    SOURCE_PER_CONFIGURATION = "source_per_configuration_koopman_v2"
    POOLED = "pooled_koopman_v2"
    CONDITIONAL = "conditional_koopman_v2"
    HELDOUT_EXPERT = "heldout_expert_upper_bound_v2"


@dataclass(frozen=True)
class RoleOutcomeV2:
    status: str
    reason_code: str | None
    artifact_sha256: str

    def __post_init__(self) -> None:
        if self.status not in {"success", "failed"}:
            _fail("role_status_invalid")
        if (self.status == "success") != (self.reason_code is None):
            _fail("role_reason_code_invalid")
        _sha(self.artifact_sha256, "role_artifact_sha256")


@dataclass(frozen=True)
class RoleResultV2:
    role: ModelRoleV2
    selection_eligible: bool
    fold_id: str
    analysis_policy_sha256: str
    metric_policy_sha256: str
    budget_sha256: str
    decision_sha256: str
    status: str
    reason_code: str | None
    artifact_sha256: str

    def __post_init__(self) -> None:
        RoleOutcomeV2(self.status, self.reason_code, self.artifact_sha256)
        for name in (
            "analysis_policy_sha256",
            "metric_policy_sha256",
            "budget_sha256",
            "decision_sha256",
        ):
            _sha(getattr(self, name), name)


@dataclass(frozen=True)
class SelectionEligibleRoleResultV2(RoleResultV2):
    def __post_init__(self) -> None:
        super().__post_init__()
        if self.role == ModelRoleV2.HELDOUT_EXPERT:
            _fail("expert_promotion_forbidden")
        if self.role not in {ModelRoleV2.POOLED, ModelRoleV2.CONDITIONAL}:
            _fail("role_not_eligible")
        if self.selection_eligible is not True:
            _fail("role_eligibility_invalid")


@dataclass(frozen=True)
class DiagnosticRoleResultV2(RoleResultV2):
    def __post_init__(self) -> None:
        super().__post_init__()
        if self.role in {ModelRoleV2.POOLED, ModelRoleV2.CONDITIONAL}:
            _fail("role_diagnostic_invalid")
        if self.selection_eligible is not False:
            _fail("role_eligibility_invalid")


@dataclass(frozen=True)
class ReferenceDiagnosticResultV2:
    namespace: str
    selection_eligible: bool
    fold_id: str
    analysis_policy_sha256: str
    metric_policy_sha256: str
    budget_sha256: str
    decision_sha256: str
    status: str
    reason_code: str | None
    artifact_sha256: str

    def __post_init__(self) -> None:
        if self.namespace != _REFERENCE_NAMESPACE or self.selection_eligible is not False:
            _fail("reference_diagnostic_not_eligible")
        RoleOutcomeV2(self.status, self.reason_code, self.artifact_sha256)
        for name in (
            "analysis_policy_sha256",
            "metric_policy_sha256",
            "budget_sha256",
            "decision_sha256",
        ):
            _sha(getattr(self, name), name)


@dataclass(frozen=True)
class RoleResultMatrixV2:
    results: tuple[RoleResultV2, ...]
    reference_diagnostic: ReferenceDiagnosticResultV2 | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(self.results))
        if tuple(result.role for result in self.results) != tuple(ModelRoleV2):
            _fail("role_matrix_incomplete")

    @property
    def eligible_results(self) -> tuple[SelectionEligibleRoleResultV2, ...]:
        return tuple(
            result
            for result in self.results
            if isinstance(result, SelectionEligibleRoleResultV2)
        )


@dataclass(frozen=True)
class FrozenPrimaryStateV2:
    """Immutable primary decision/model identity captured before outer test access."""

    fold_id: str
    holdout_configuration: str
    source_configurations: tuple[str, ...]
    source_episode_sha256s: tuple[str, ...]
    candidate_id: str
    decision_sha256: str
    analysis_policy_sha256: str
    primary_model_sha256s: Mapping[str, str]
    frozen_at: str
    candidate_revision: int = 0
    model_revision: int = 0
    test_open_count_at_freeze: int = 0
    post_test_mutation_count: int = 0
    state: str = "frozen"
    freeze_state_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        sources = tuple(self.source_configurations)
        hashes = tuple(self.source_episode_sha256s)
        models = dict(self.primary_model_sha256s)
        if (
            self.state != "frozen"
            or len(sources) != 7
            or len(set(sources)) != 7
            or self.holdout_configuration in sources
            or not hashes
        ):
            _fail("primary_freeze_invalid")
        for name, value in (
            ("candidate_id", self.candidate_id),
            ("decision_sha256", self.decision_sha256),
            ("analysis_policy_sha256", self.analysis_policy_sha256),
            *tuple((f"primary_model_sha256s.{key}", value) for key, value in models.items()),
            *tuple(("source_episode_sha256s", value) for value in hashes),
        ):
            _sha(value, name)
        if not models:
            _fail("primary_freeze_model_set_empty")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value != 0
            for value in (
                self.candidate_revision,
                self.model_revision,
                self.test_open_count_at_freeze,
                self.post_test_mutation_count,
            )
        ):
            _fail("post_test_retune")
        object.__setattr__(self, "source_configurations", sources)
        object.__setattr__(self, "source_episode_sha256s", hashes)
        object.__setattr__(self, "primary_model_sha256s", MappingProxyType(models))
        object.__setattr__(
            self,
            "freeze_state_sha256",
            canonical_sha256(self.to_dict(include_sha256=False)),
        )

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, Any]:
        value = {
            "analysis_policy_sha256": self.analysis_policy_sha256,
            "candidate_id": self.candidate_id,
            "candidate_revision": self.candidate_revision,
            "decision_sha256": self.decision_sha256,
            "fold_id": self.fold_id,
            "frozen_at": self.frozen_at,
            "holdout_configuration": self.holdout_configuration,
            "model_revision": self.model_revision,
            "post_test_mutation_count": self.post_test_mutation_count,
            "primary_model_sha256s": dict(self.primary_model_sha256s),
            "source_configurations": list(self.source_configurations),
            "source_episode_sha256s": list(self.source_episode_sha256s),
            "state": self.state,
            "test_open_count_at_freeze": self.test_open_count_at_freeze,
        }
        if include_sha256:
            value["freeze_state_sha256"] = self.freeze_state_sha256
        return value


@dataclass(frozen=True)
class PrimaryTestAccessTokenV2:
    fold_id: str
    holdout_configuration: str
    test_episode_ids: tuple[str, ...]
    freeze_state_sha256: str
    freeze_candidate_id: str
    analysis_policy_sha256: str


def authorize_primary_test_access_v2(
    frozen: FrozenPrimaryStateV2,
    *,
    analysis_policy: AnalysisPolicyV2,
    fold_id: str,
    holdout_configuration: str,
    test_episode_ids: tuple[str, ...],
) -> PrimaryTestAccessTokenV2:
    """Issue the only primary-path token that permits held-out bytes to open."""

    episodes = tuple(test_episode_ids)
    if not isinstance(frozen, FrozenPrimaryStateV2):
        _fail("primary_freeze_missing")
    if (
        frozen.fold_id != fold_id
        or frozen.holdout_configuration != holdout_configuration
        or frozen.analysis_policy_sha256 != analysis_policy.policy_sha256
    ):
        _fail("primary_freeze_binding_mismatch")
    if not episodes or len(set(episodes)) != len(episodes):
        _fail("outer_test_binding_mismatch")
    return PrimaryTestAccessTokenV2(
        fold_id=fold_id,
        holdout_configuration=holdout_configuration,
        test_episode_ids=episodes,
        freeze_state_sha256=frozen.freeze_state_sha256,
        freeze_candidate_id=frozen.candidate_id,
        analysis_policy_sha256=frozen.analysis_policy_sha256,
    )


def _entry_map(inventory: DatasetInventoryV2) -> Mapping[str, EpisodeInventoryEntryV2]:
    return {entry.episode_id: entry for entry in inventory.entries}


def _metric_policy_sha256(policy: AnalysisPolicyV2) -> str:
    return canonical_sha256(
        {
            "gate_template": dict(policy.gate_template),
            "horizons": list(policy.horizons),
            "metric_schema": dict(policy.metric_schema),
        }
    )


def _budget_sha256(policy: AnalysisPolicyV2) -> str:
    return canonical_sha256(
        {
            "candidate_ids": [item.candidate_id for item in candidate_grid_v2(policy)],
            "data_prefixes": list(policy.data_prefixes),
        }
    )


def _role_result(
    role: ModelRoleV2,
    decision: FoldProtocolDecisionV2,
    outcome: RoleOutcomeV2,
) -> RoleResultV2:
    fields = {
        "role": role,
        "fold_id": decision.fold_id,
        "analysis_policy_sha256": decision.analysis_policy_sha256,
        "metric_policy_sha256": decision.metric_policy_sha256,
        "budget_sha256": decision.budget_sha256,
        "decision_sha256": decision.decision_sha256,
        "status": outcome.status,
        "reason_code": outcome.reason_code,
        "artifact_sha256": outcome.artifact_sha256,
    }
    if role in {ModelRoleV2.POOLED, ModelRoleV2.CONDITIONAL}:
        return SelectionEligibleRoleResultV2(selection_eligible=True, **fields)
    return DiagnosticRoleResultV2(selection_eligible=False, **fields)


class FoldExecutionV2:
    """State machine that seals source decisions before exposing outer test data."""

    def __init__(
        self,
        *,
        fold: LOCOFoldManifestV2,
        primary_view: PrimaryLOCOViewV2,
        inventory: DatasetInventoryV2,
        policy: AnalysisPolicyV2,
    ) -> None:
        if (
            fold.fold_id != primary_view.fold_id
            or fold.holdout_configuration != primary_view.holdout_configuration
            or fold.source_configurations != tuple(primary_view.source_configurations)
            or fold.primary_source_episode_ids != tuple(primary_view.decision_episode_ids)
            or fold.primary_heldout_test_episode_ids != tuple(primary_view.outer_test_episode_ids)
            or fold.inventory_sha256 != primary_view.inventory_sha256
            or fold.inventory_sha256 != inventory.inventory_sha256
        ):
            _fail("fold_manifest_drift")
        if len(fold.source_configurations) != 7:
            _fail("source_configuration_count_invalid")
        if fold.holdout_configuration in fold.source_configurations:
            _fail("heldout_design_leakage")
        self.fold = fold
        self.primary_view = primary_view
        self.inventory = inventory
        self.policy = policy
        self.decision: FoldProtocolDecisionV2 | None = None
        self.dataset_accesses: tuple[OpenedArtifactRecordV2, ...] = ()
        self.statistic_accesses: tuple[StatisticAccessRecordV2, ...] = ()
        self.test_accesses: tuple[OpenedArtifactRecordV2, ...] = ()
        self.expert_accesses: tuple[OpenedArtifactRecordV2, ...] = ()
        self._source_payloads: tuple[Any, ...] = ()
        self._test_payloads: tuple[Any, ...] = ()
        self._expert_payloads: tuple[Any, ...] = ()

    def seal_decision(
        self,
        *,
        source_opener: Callable[[EpisodeInventoryEntryV2], T],
        candidate_evaluator: Callable[
            [CandidateSpecV2, tuple[T, ...], LOCOFoldManifestV2],
            CandidateValidationResultV2,
        ],
        sealed_at: str,
        output_path: str | Path | None = None,
    ) -> FoldProtocolDecisionV2:
        if self.test_accesses:
            _fail("post_test_retune")
        if self.decision is not None:
            _fail("fold_decision_exists")
        payloads, audit = load_primary_decision_view_v2(
            self.primary_view, self.inventory, source_opener
        )
        validate_primary_access_audit_v2(self.fold, audit)
        self._source_payloads = tuple(payloads)
        self.dataset_accesses = audit.opened_artifacts

        source_set = set(self.fold.source_configurations)
        hashes_by_configuration = {
            configuration: tuple(
                record.transition_sha256
                for record in audit.opened_artifacts
                if record.configuration == configuration
            )
            for configuration in self.fold.source_configurations
        }
        evaluated: list[tuple[int, CandidateValidationResultV2]] = []
        statistic_records: list[StatisticAccessRecordV2] = []
        for index, candidate in enumerate(candidate_grid_v2(self.policy)):
            result = candidate_evaluator(candidate, tuple(payloads), self.fold)
            if not isinstance(result, CandidateValidationResultV2):
                _fail("candidate_result_invalid")
            if result.candidate != candidate:
                _fail("candidate_binding_mismatch")
            if result.budget_data_prefix != candidate.data_prefix:
                _fail("different_budget")
            score_set = set(result.source_scores)
            if self.fold.holdout_configuration in score_set or not score_set <= source_set:
                _fail("heldout_statistic_access")
            if score_set != source_set:
                _fail("source_statistic_set_mismatch")
            if result.source_episode_sha256s != self.fold.source_episode_sha256s:
                _fail("source_statistic_hash_mismatch")
            for configuration in self.fold.source_configurations:
                statistic_records.append(
                    StatisticAccessRecordV2(
                        candidate_id=candidate.candidate_id,
                        configuration=configuration,
                        episode_sha256s=hashes_by_configuration[configuration],
                    )
                )
            if result.converged:
                evaluated.append((index, result))
        self.statistic_accesses = tuple(statistic_records)
        if not evaluated:
            _fail("candidate_grid_no_converged_result")

        def key(item: tuple[int, CandidateValidationResultV2]) -> tuple[float, float, int]:
            index, result = item
            scores = tuple(float(result.source_scores[name]) for name in self.fold.source_configurations)
            return max(scores), sum(scores) / len(scores), index

        evaluated_by_family = {
            ModelRoleV2.POOLED.value: tuple(
                item for item in evaluated if item[1].candidate.platform_schema == "none"
            ),
            ModelRoleV2.CONDITIONAL.value: tuple(
                item for item in evaluated if item[1].candidate.platform_schema != "none"
            ),
        }
        if any(not items for items in evaluated_by_family.values()):
            _fail("candidate_family_no_converged_result")
        selected_results = {
            family: min(items, key=key)[1]
            for family, items in evaluated_by_family.items()
        }
        diagnostics: dict[str, dict[str, float | int]] = {}
        for family, selected_result in selected_results.items():
            source_scores = tuple(
                float(selected_result.source_scores[name])
                for name in self.fold.source_configurations
            )
            diagnostics[family] = {
                "condition_number": selected_result.condition_number,
                "design_rank": selected_result.design_rank,
                "design_width": selected_result.design_width,
                "source_macro": sum(source_scores) / len(source_scores),
                "source_worst": max(source_scores),
            }
        decision = FoldProtocolDecisionV2(
            fold_id=self.fold.fold_id,
            holdout_configuration=self.fold.holdout_configuration,
            source_configurations=self.fold.source_configurations,
            source_episode_sha256s=self.fold.source_episode_sha256s,
            selected_candidates={
                family: result.candidate
                for family, result in selected_results.items()
            },
            diagnostics=diagnostics,
            source_gates=dict(self.policy.gate_template),
            sealed_at=sealed_at,
            inventory_sha256=self.fold.inventory_sha256,
            analysis_policy_sha256=self.policy.policy_sha256,
            metric_policy_sha256=_metric_policy_sha256(self.policy),
            budget_sha256=_budget_sha256(self.policy),
            platform_normalizer_sha256s={
                family: result.platform_normalizer_sha256
                for family, result in selected_results.items()
            },
            test_open_count_at_seal=len(self.test_accesses),
        )
        if output_path is not None:
            _write_decision(decision, output_path)
        self.decision = decision
        return decision

    def open_primary_test(
        self,
        *,
        test_opener: Callable[[EpisodeInventoryEntryV2], T],
        policy: AnalysisPolicyV2,
        access_token: PrimaryTestAccessTokenV2 | None = None,
    ) -> tuple[T, ...]:
        if self.decision is None:
            _fail("fold_decision_missing")
        if policy.policy_sha256 != self.decision.analysis_policy_sha256:
            _fail("analysis_policy_drift")
        if not isinstance(access_token, PrimaryTestAccessTokenV2):
            _fail("primary_freeze_missing")
        if (
            access_token.fold_id != self.fold.fold_id
            or access_token.holdout_configuration
            != self.fold.holdout_configuration
            or access_token.test_episode_ids
            != self.fold.primary_heldout_test_episode_ids
            or access_token.freeze_candidate_id != self.decision.candidate_id
            or access_token.analysis_policy_sha256
            != self.decision.analysis_policy_sha256
        ):
            _fail("primary_freeze_binding_mismatch")
        if self.test_accesses:
            _fail("heldout_test_already_open")
        entries = _entry_map(self.inventory)
        payloads: list[T] = []
        records: list[OpenedArtifactRecordV2] = []
        for episode_id in self.primary_view.outer_test_episode_ids:
            entry = entries.get(episode_id)
            if entry is None:
                _fail("inventory_set_mismatch", episode_id)
            if entry.configuration != self.fold.holdout_configuration or entry.role != "test":
                _fail("outer_test_binding_mismatch", episode_id)
            payloads.append(test_opener(entry))
            records.append(
                OpenedArtifactRecordV2(
                    episode_id=entry.episode_id,
                    configuration=entry.configuration,
                    role=entry.role,
                    transition_sha256=entry.transition_sha256,
                )
            )
        self._test_payloads = tuple(payloads)
        self.test_accesses = tuple(records)
        return self._test_payloads

    def open_expert_decision(
        self,
        *,
        expert_view: ExpertLOCOViewV2,
        expert_opener: Callable[[EpisodeInventoryEntryV2], T],
    ) -> tuple[T, ...]:
        if self.decision is None:
            _fail("fold_decision_missing")
        if (
            expert_view.selection_eligible is not False
            or expert_view.fold_id != self.fold.fold_id
            or expert_view.holdout_configuration != self.fold.holdout_configuration
            or tuple(expert_view.decision_episode_ids)
            != self.fold.expert_fit_validation_episode_ids
            or tuple(expert_view.test_episode_ids) != self.fold.expert_test_episode_ids
            or expert_view.inventory_sha256 != self.fold.inventory_sha256
        ):
            _fail("expert_view_binding_mismatch")
        if self.expert_accesses:
            _fail("expert_decision_already_open")
        entries = _entry_map(self.inventory)
        payloads: list[T] = []
        records: list[OpenedArtifactRecordV2] = []
        for episode_id in expert_view.decision_episode_ids:
            entry = entries.get(episode_id)
            if entry is None:
                _fail("inventory_set_mismatch", episode_id)
            if (
                entry.configuration != self.fold.holdout_configuration
                or entry.role not in {"fit", "validation"}
            ):
                _fail("expert_view_binding_mismatch", episode_id)
            payloads.append(expert_opener(entry))
            records.append(
                OpenedArtifactRecordV2(
                    episode_id=entry.episode_id,
                    configuration=entry.configuration,
                    role=entry.role,
                    transition_sha256=entry.transition_sha256,
                )
            )
        self._expert_payloads = tuple(payloads)
        self.expert_accesses = tuple(records)
        return self._expert_payloads

    def run_roles(
        self,
        *,
        role_runner: Callable[
            [ModelRoleV2, tuple[Any, ...], tuple[Any, ...], FoldProtocolDecisionV2],
            RoleOutcomeV2,
        ],
        reference_runner: Callable[
            [tuple[Any, ...], tuple[Any, ...], FoldProtocolDecisionV2],
            RoleOutcomeV2,
        ]
        | None = None,
    ) -> RoleResultMatrixV2:
        if self.decision is None:
            _fail("fold_decision_missing")
        if not self.test_accesses:
            _fail("outer_test_not_open")
        results: list[RoleResultV2] = []
        for role in ModelRoleV2:
            if role == ModelRoleV2.PERSISTENCE:
                fit_payloads: tuple[Any, ...] = ()
            elif role == ModelRoleV2.HELDOUT_EXPERT:
                if not self.expert_accesses:
                    _fail("expert_decision_not_open")
                fit_payloads = self._expert_payloads
            else:
                fit_payloads = self._source_payloads
            outcome = role_runner(role, fit_payloads, self._test_payloads, self.decision)
            if not isinstance(outcome, RoleOutcomeV2):
                _fail("role_outcome_invalid", role.value)
            results.append(_role_result(role, self.decision, outcome))

        reference: ReferenceDiagnosticResultV2 | None = None
        if reference_runner is not None:
            outcome = reference_runner(
                self._source_payloads, self._test_payloads, self.decision
            )
            if not isinstance(outcome, RoleOutcomeV2):
                _fail("role_outcome_invalid", "reference")
            reference = ReferenceDiagnosticResultV2(
                namespace=_REFERENCE_NAMESPACE,
                selection_eligible=False,
                fold_id=self.decision.fold_id,
                analysis_policy_sha256=self.decision.analysis_policy_sha256,
                metric_policy_sha256=self.decision.metric_policy_sha256,
                budget_sha256=self.decision.budget_sha256,
                decision_sha256=self.decision.decision_sha256,
                status=outcome.status,
                reason_code=outcome.reason_code,
                artifact_sha256=outcome.artifact_sha256,
            )
        return RoleResultMatrixV2(tuple(results), reference)


def validate_fold_model_binding_v2(
    decision: FoldProtocolDecisionV2,
    model: Any,
    *,
    family: ModelRoleV2 | str,
) -> None:
    family_name = family.value if isinstance(family, ModelRoleV2) else family
    if family_name not in _PRIMARY_KOOPMAN_FAMILIES:
        _fail("primary_candidate_family_binding_mismatch")
    selected = decision.selected_candidates[family_name]
    expected_conditioning = (
        "none" if selected.platform_schema == "none" else "platform_affine"
    )
    if (
        getattr(model, "fold_id", None) != decision.fold_id
        or getattr(model, "observable_schema", None)
        != selected.observable_schema
        or getattr(model, "ridge", None) != selected.ridge
        or getattr(model, "normalization", None) != selected.normalization
        or getattr(model, "conditioning", None) != expected_conditioning
    ):
        _fail("fold_model_binding_mismatch")
    if (
        getattr(model, "platform_normalizer_sha256", None)
        != decision.platform_normalizer_sha256s[family_name]
    ):
        _fail("stale_normalizer")
