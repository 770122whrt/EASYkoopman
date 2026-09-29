"""Source-only Phase 8.1 candidate selection and immutable primary freeze.

The APIs in this module deliberately have no held-out descriptor or test input.
They operate on the seven source configurations only and seal every attempted
candidate, including candidates rejected by the numerical-admission contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any

from koopman.evidence_v2 import canonical_json_bytes, canonical_sha256
from koopman.model_v21 import (
    CONDITIONING_NONE_V21,
    CONDITIONING_STRUCTURED_PCA2_V21,
)


PRIMARY_METRICS_V21 = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)
ELIGIBLE_FAMILIES_V21 = ("pooled", "conditional")
SOURCE_CONFIGURATION_MODE_V21 = "report_all_no_ranking"
IDENTITY_ESTIMATOR_EQUIVALENCE_CLASS_V21 = (
    "so3_linear_increment_ridge_v1"
)
CONDITION_LIMIT_V21 = 1.0e8


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


def _metric_mapping(
    value: Mapping[str, float | None],
    *,
    allow_none: bool,
    path: str,
) -> Mapping[str, float | None]:
    if tuple(value) != PRIMARY_METRICS_V21 and set(value) != set(PRIMARY_METRICS_V21):
        _fail("primary_metric_set_mismatch", path)
    ordered: dict[str, float | None] = {}
    for metric in PRIMARY_METRICS_V21:
        item = value[metric]
        if item is None:
            if not allow_none:
                _fail("metric_value_invalid", f"{path}.{metric}")
            ordered[metric] = None
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            _fail("metric_value_invalid", f"{path}.{metric}")
        item = float(item)
        if not math.isfinite(item) or item < 0.0:
            _fail("metric_value_invalid", f"{path}.{metric}")
        ordered[metric] = item
    return MappingProxyType(ordered)


@dataclass(frozen=True)
class CandidateSpecV21:
    family: str
    observable_schema: str
    data_prefix: int
    ridge: float
    normalization: str
    conditioning: str
    label: str
    candidate_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.family not in ELIGIBLE_FAMILIES_V21:
            _fail("candidate_family_invalid")
        if self.observable_schema not in {"so3_identity_v1", "so3_kinematic_v1"}:
            _fail("candidate_observable_invalid")
        if isinstance(self.data_prefix, bool) or self.data_prefix <= 0:
            _fail("candidate_data_prefix_invalid")
        if not math.isfinite(float(self.ridge)) or self.ridge < 0.0:
            _fail("candidate_ridge_invalid")
        if self.normalization not in {"none", "standard_v1"}:
            _fail("candidate_normalization_invalid")
        expected_conditioning = (
            CONDITIONING_NONE_V21
            if self.family == "pooled"
            else CONDITIONING_STRUCTURED_PCA2_V21
        )
        if self.conditioning != expected_conditioning:
            _fail("candidate_conditioning_invalid")
        if not self.label:
            _fail("candidate_label_invalid")
        object.__setattr__(self, "ridge", float(self.ridge))
        object.__setattr__(self, "candidate_id", canonical_sha256(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "conditioning": self.conditioning,
            "data_prefix": self.data_prefix,
            "family": self.family,
            "label": self.label,
            "normalization": self.normalization,
            "observable_schema": self.observable_schema,
            "ridge": self.ridge,
        }


@dataclass(frozen=True)
class NumericalDiagnosticsV21:
    design_rank: int
    effective_rank: float
    design_width: int
    regularized_condition: float

    def __post_init__(self) -> None:
        for name in ("design_rank", "design_width"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _fail("numerical_diagnostic_invalid", name)
        if self.design_width <= 0 or self.design_rank > self.design_width:
            _fail("numerical_diagnostic_invalid", "design_width")
        effective_rank = float(self.effective_rank)
        if not math.isfinite(effective_rank) or effective_rank < 0.0:
            _fail("numerical_diagnostic_invalid", "effective_rank")
        condition = float(self.regularized_condition)
        if not math.isfinite(condition) or condition < 0.0:
            _fail("numerical_diagnostic_invalid", "regularized_condition")
        object.__setattr__(self, "effective_rank", effective_rank)
        object.__setattr__(self, "regularized_condition", condition)

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_rank": self.design_rank,
            "design_width": self.design_width,
            "effective_rank": self.effective_rank,
            "regularized_condition": self.regularized_condition,
        }


@dataclass(frozen=True)
class SourceMetricRecordV21:
    configuration: str
    candidate_errors: Mapping[str, float | None]
    persistence_errors: Mapping[str, float]
    simple_linear_errors: Mapping[str, float | None]

    def __post_init__(self) -> None:
        if not self.configuration:
            _fail("source_configuration_invalid")
        object.__setattr__(
            self,
            "candidate_errors",
            _metric_mapping(
                self.candidate_errors,
                allow_none=True,
                path=f"{self.configuration}.candidate",
            ),
        )
        object.__setattr__(
            self,
            "persistence_errors",
            _metric_mapping(
                self.persistence_errors,
                allow_none=False,
                path=f"{self.configuration}.persistence",
            ),
        )
        object.__setattr__(
            self,
            "simple_linear_errors",
            _metric_mapping(
                self.simple_linear_errors,
                allow_none=True,
                path=f"{self.configuration}.simple_linear",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": dict(self.candidate_errors),
            "persistence": dict(self.persistence_errors),
            "simple_linear": dict(self.simple_linear_errors),
        }


@dataclass(frozen=True)
class CandidateEvaluationV21:
    candidate: CandidateSpecV21
    source_records: tuple[SourceMetricRecordV21, ...]
    numerics: NumericalDiagnosticsV21
    converged: bool
    rejection_reason: str | None
    model_identity: str | None
    normalizer_identity: str | None
    pca_identity: str | None

    def __post_init__(self) -> None:
        records = tuple(self.source_records)
        if len(records) != 7 or len({record.configuration for record in records}) != 7:
            _fail("source_configuration_set_mismatch")
        if not isinstance(self.converged, bool):
            _fail("candidate_convergence_invalid")
        if self.converged:
            if self.rejection_reason is not None or not self.model_identity:
                _fail("candidate_outcome_invalid")
            if any(
                value is None
                for record in records
                for value in record.candidate_errors.values()
            ):
                _fail("candidate_metric_missing")
        else:
            if not self.rejection_reason or self.model_identity is not None:
                _fail("candidate_outcome_invalid")
        if self.candidate.family == "conditional" and self.converged and not self.pca_identity:
            _fail("conditional_pca_identity_missing")
        if self.candidate.family == "pooled" and self.pca_identity is not None:
            _fail("pooled_pca_identity_forbidden")
        object.__setattr__(self, "source_records", records)


def robust_relative_source_score_v21(
    candidate_errors: Mapping[str, float],
    persistence_errors: Mapping[str, float],
    simple_linear_errors: Mapping[str, float],
) -> tuple[float, Mapping[str, float]]:
    """Return max of six unweighted robust-relative ratios.

    A zero candidate over a zero better-baseline reference is exact parity and
    has ratio one.  A positive candidate over a zero reference is ineligible;
    no epsilon is introduced.
    """

    values = (
        _metric_mapping(candidate_errors, allow_none=False, path="candidate"),
        _metric_mapping(persistence_errors, allow_none=False, path="persistence"),
        _metric_mapping(simple_linear_errors, allow_none=False, path="simple_linear"),
    )
    ratios: dict[str, float] = {}
    for metric in PRIMARY_METRICS_V21:
        candidate = float(values[0][metric])
        reference = min(float(values[1][metric]), float(values[2][metric]))
        if reference == 0.0:
            if candidate > 0.0:
                _fail("source_score_reference_zero_candidate_positive", metric)
            ratios[metric] = 1.0
        else:
            ratios[metric] = candidate / reference
    return max(ratios.values()), MappingProxyType(ratios)


@dataclass(frozen=True)
class CandidateLedgerEntryV21:
    candidate: CandidateSpecV21
    source_configuration_metrics: Mapping[str, Mapping[str, Mapping[str, float | None]]]
    candidate_equal_configuration_macro: Mapping[str, float] | None
    persistence_equal_configuration_macro: Mapping[str, float]
    simple_linear_equal_configuration_macro: Mapping[str, float] | None
    ratios: Mapping[str, float]
    source_score: float | None
    numerics: NumericalDiagnosticsV21
    converged: bool
    selection_eligible: bool
    rejection_reason: str | None
    model_identity: str | None
    normalizer_identity: str | None
    pca_identity: str | None
    estimator_equivalence_class: str | None

    def __post_init__(self) -> None:
        source: dict[str, Mapping[str, Mapping[str, float | None]]] = {}
        for configuration, values in self.source_configuration_metrics.items():
            source[configuration] = MappingProxyType(
                {
                    role: MappingProxyType(dict(metrics))
                    for role, metrics in values.items()
                }
            )
        object.__setattr__(self, "source_configuration_metrics", MappingProxyType(source))
        for name in (
            "candidate_equal_configuration_macro",
            "persistence_equal_configuration_macro",
            "simple_linear_equal_configuration_macro",
            "ratios",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, MappingProxyType(dict(value)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict()
            | {"candidate_id": self.candidate.candidate_id},
            "candidate_equal_configuration_macro": (
                None
                if self.candidate_equal_configuration_macro is None
                else dict(self.candidate_equal_configuration_macro)
            ),
            "converged": self.converged,
            "estimator_equivalence_class": self.estimator_equivalence_class,
            "model_identity": self.model_identity,
            "normalizer_identity": self.normalizer_identity,
            "numerics": self.numerics.to_dict(),
            "pca_identity": self.pca_identity,
            "persistence_equal_configuration_macro": dict(
                self.persistence_equal_configuration_macro
            ),
            "ratios": dict(self.ratios),
            "rejection_reason": self.rejection_reason,
            "selection_eligible": self.selection_eligible,
            "simple_linear_equal_configuration_macro": (
                None
                if self.simple_linear_equal_configuration_macro is None
                else dict(self.simple_linear_equal_configuration_macro)
            ),
            "source_configuration_metrics": {
                configuration: {
                    role: dict(metrics) for role, metrics in values.items()
                }
                for configuration, values in self.source_configuration_metrics.items()
            },
            "source_score": self.source_score,
        }


def _macro(
    records: Sequence[SourceMetricRecordV21], role: str
) -> Mapping[str, float] | None:
    result: dict[str, float] = {}
    for metric in PRIMARY_METRICS_V21:
        values = [getattr(record, role)[metric] for record in records]
        if any(value is None for value in values):
            return None
        result[metric] = sum(float(value) for value in values) / len(values)
    return MappingProxyType(result)


def _entry(evaluation: CandidateEvaluationV21) -> CandidateLedgerEntryV21:
    candidate_macro = _macro(evaluation.source_records, "candidate_errors")
    persistence_macro = _macro(evaluation.source_records, "persistence_errors")
    simple_macro = _macro(evaluation.source_records, "simple_linear_errors")
    assert persistence_macro is not None
    reason = evaluation.rejection_reason
    eligible = evaluation.converged
    if eligible and simple_macro is None:
        eligible = False
        reason = "simple_linear_baseline_failed"
    if eligible and evaluation.numerics.design_rank != evaluation.numerics.design_width:
        eligible = False
        reason = "design_rank_insufficient"
    if eligible and evaluation.numerics.regularized_condition > CONDITION_LIMIT_V21:
        eligible = False
        reason = "regularized_condition_exceeds_limit"
    ratios: Mapping[str, float] = MappingProxyType({})
    score: float | None = None
    if eligible:
        assert candidate_macro is not None
        try:
            score, ratios = robust_relative_source_score_v21(
                candidate_macro, persistence_macro, simple_macro
            )
        except ValueError as error:
            eligible = False
            reason = str(error)
    equivalence = (
        IDENTITY_ESTIMATOR_EQUIVALENCE_CLASS_V21
        if evaluation.candidate.family == "pooled"
        and evaluation.candidate.observable_schema == "so3_identity_v1"
        else None
    )
    source_metrics = {
        record.configuration: {
            "candidate": record.candidate_errors,
            "persistence": record.persistence_errors,
            "simple_linear": record.simple_linear_errors,
        }
        for record in evaluation.source_records
    }
    return CandidateLedgerEntryV21(
        candidate=evaluation.candidate,
        source_configuration_metrics=source_metrics,
        candidate_equal_configuration_macro=candidate_macro,
        persistence_equal_configuration_macro=persistence_macro,
        simple_linear_equal_configuration_macro=simple_macro,
        ratios=ratios,
        source_score=score,
        numerics=evaluation.numerics,
        converged=evaluation.converged,
        selection_eligible=eligible,
        rejection_reason=None if eligible else reason,
        model_identity=evaluation.model_identity,
        normalizer_identity=evaluation.normalizer_identity,
        pca_identity=evaluation.pca_identity,
        estimator_equivalence_class=equivalence,
    )


def _ranking_key_v21(
    entry: CandidateLedgerEntryV21,
    family_order: Sequence[str],
) -> tuple[Any, ...]:
    return (
        float(entry.source_score),
        entry.candidate.data_prefix,
        0 if entry.candidate.observable_schema == "so3_identity_v1" else 1,
        entry.candidate.ridge,
        0 if entry.candidate.normalization == "none" else 1,
        tuple(family_order).index(entry.candidate.family),
        entry.candidate.candidate_id,
    )


@dataclass(frozen=True)
class SourceCandidateLedgerV21:
    source_configurations: tuple[str, ...]
    family_order: tuple[str, ...]
    candidates: tuple[CandidateLedgerEntryV21, ...]
    ranking: tuple[str, ...]
    selected_candidates: Mapping[str, str]
    source_configuration_mode: str = SOURCE_CONFIGURATION_MODE_V21
    sealed: bool = True
    version: str = "phase8.1-source-candidate-ledger-v1"
    ledger_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_configurations", tuple(self.source_configurations))
        object.__setattr__(self, "family_order", tuple(self.family_order))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "ranking", tuple(self.ranking))
        object.__setattr__(
            self, "selected_candidates", MappingProxyType(dict(self.selected_candidates))
        )
        if len(self.source_configurations) != 7 or len(set(self.source_configurations)) != 7:
            _fail("source_configuration_set_mismatch")
        if (
            len(self.family_order) != len(ELIGIBLE_FAMILIES_V21)
            or set(self.family_order) != set(ELIGIBLE_FAMILIES_V21)
        ):
            _fail("family_order_invalid")
        if not self.sealed or self.source_configuration_mode != SOURCE_CONFIGURATION_MODE_V21:
            _fail("source_ledger_not_sealed")
        object.__setattr__(
            self, "ledger_sha256", canonical_sha256(self.to_dict(include_sha256=False))
        )

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, Any]:
        value = {
            "candidates": [entry.to_dict() for entry in self.candidates],
            "family_order": list(self.family_order),
            "ranking": list(self.ranking),
            "sealed": self.sealed,
            "selected_candidates": dict(self.selected_candidates),
            "source_configuration_mode": self.source_configuration_mode,
            "source_configurations": list(self.source_configurations),
            "version": self.version,
        }
        if include_sha256:
            value["ledger_sha256"] = self.ledger_sha256
        return value


def build_source_candidate_ledger_v21(
    evaluations: Sequence[CandidateEvaluationV21],
    *,
    source_configurations: Sequence[str],
    expected_candidates: Sequence[CandidateSpecV21],
    family_order: Sequence[str] = ELIGIBLE_FAMILIES_V21,
) -> SourceCandidateLedgerV21:
    """Seal a complete source-only ledger; no held-out input exists here."""

    sources = tuple(source_configurations)
    families = tuple(family_order)
    if len(sources) != 7 or len(set(sources)) != 7:
        _fail("source_configuration_set_mismatch")
    if len(families) != len(ELIGIBLE_FAMILIES_V21) or set(families) != set(
        ELIGIBLE_FAMILIES_V21
    ):
        _fail("family_order_invalid")
    expected = tuple(expected_candidates)
    results = tuple(evaluations)
    expected_ids = tuple(candidate.candidate_id for candidate in expected)
    result_ids = tuple(result.candidate.candidate_id for result in results)
    if len(set(expected_ids)) != len(expected_ids) or set(result_ids) != set(expected_ids):
        _fail("candidate_result_set_mismatch")
    by_id = {result.candidate.candidate_id: result for result in results}
    ordered = tuple(by_id[candidate_id] for candidate_id in expected_ids)
    for result in ordered:
        if tuple(record.configuration for record in result.source_records) != sources:
            _fail("source_configuration_set_mismatch")
    entries = tuple(_entry(result) for result in ordered)
    eligible = [entry for entry in entries if entry.selection_eligible]
    ranked = sorted(eligible, key=lambda entry: _ranking_key_v21(entry, families))
    selected: dict[str, str] = {}
    for family in families:
        family_entries = [entry for entry in ranked if entry.candidate.family == family]
        if family_entries:
            selected[family] = family_entries[0].candidate.candidate_id
    return SourceCandidateLedgerV21(
        source_configurations=sources,
        family_order=families,
        candidates=entries,
        ranking=tuple(entry.candidate.candidate_id for entry in ranked),
        selected_candidates=selected,
    )


def write_source_candidate_ledger_v21(
    ledger: SourceCandidateLedgerV21, path: str | Path
) -> Path:
    target = Path(path)
    part = target.with_name(f"{target.name}.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or part.exists():
        _fail("artifact_exists")
    try:
        with part.open("xb") as stream:
            stream.write(canonical_json_bytes(ledger.to_dict()))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(part, target)
    finally:
        if part.exists():
            part.unlink()
    return target


@dataclass(frozen=True)
class FrozenPrimaryV21:
    ledger_sha256: str
    selected_candidates: Mapping[str, str]
    model_identities: Mapping[str, str]
    normalizer_identities: Mapping[str, str]
    pca_identities: Mapping[str, str]
    frozen_at: str
    state: str = "PRIMARY_FROZEN"
    authorization_eligible: bool = False
    test_open_count_at_freeze: int = 0
    freeze_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "selected_candidates",
            "model_identities",
            "normalizer_identities",
            "pca_identities",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        families = set(self.selected_candidates)
        if (
            not families
            or set(self.model_identities) != families
            or set(self.normalizer_identities) != families
            or not set(self.pca_identities).issubset({"conditional"})
            or ("conditional" in families) != ("conditional" in self.pca_identities)
        ):
            _fail("primary_freeze_binding_invalid")
        if (
            self.state != "PRIMARY_FROZEN"
            or self.authorization_eligible is not False
            or self.test_open_count_at_freeze != 0
        ):
            _fail("primary_freeze_state_invalid")
        object.__setattr__(self, "freeze_sha256", canonical_sha256(self.to_dict(False)))

    def to_dict(self, include_sha256: bool = True) -> dict[str, Any]:
        value = {
            "authorization_eligible": self.authorization_eligible,
            "frozen_at": self.frozen_at,
            "ledger_sha256": self.ledger_sha256,
            "model_identities": dict(self.model_identities),
            "normalizer_identities": dict(self.normalizer_identities),
            "pca_identities": dict(self.pca_identities),
            "selected_candidates": dict(self.selected_candidates),
            "state": self.state,
            "test_open_count_at_freeze": self.test_open_count_at_freeze,
        }
        if include_sha256:
            value["freeze_sha256"] = self.freeze_sha256
        return value


def freeze_primary_v21(
    ledger: SourceCandidateLedgerV21,
    *,
    model_identities: Mapping[str, str] | None = None,
    normalizer_identities: Mapping[str, str] | None = None,
    pca_identities: Mapping[str, str] | None = None,
    frozen_at: str,
) -> FrozenPrimaryV21:
    if not isinstance(ledger, SourceCandidateLedgerV21) or not ledger.sealed:
        _fail("source_ledger_not_sealed")
    by_id = {
        entry.candidate.candidate_id: entry for entry in ledger.candidates
    }
    ranked = sorted(
        (entry for entry in ledger.candidates if entry.selection_eligible),
        key=lambda entry: _ranking_key_v21(entry, ledger.family_order),
    )
    expected_ranking = tuple(entry.candidate.candidate_id for entry in ranked)
    expected_selected: dict[str, str] = {}
    for entry in ranked:
        expected_selected.setdefault(
            entry.candidate.family, entry.candidate.candidate_id
        )
    if (
        ledger.ranking != expected_ranking
        or dict(ledger.selected_candidates) != expected_selected
    ):
        _fail("primary_freeze_selected_candidate_invalid", "ledger_selection")
    expected_models: dict[str, str] = {}
    expected_normalizers: dict[str, str] = {}
    expected_pca: dict[str, str] = {}
    for family, candidate_id in ledger.selected_candidates.items():
        entry = by_id.get(candidate_id)
        if (
            family not in ELIGIBLE_FAMILIES_V21
            or entry is None
            or entry.candidate.family != family
            or not entry.selection_eligible
            or candidate_id not in ledger.ranking
        ):
            _fail("primary_freeze_selected_candidate_invalid", family)
        if not entry.model_identity or not entry.normalizer_identity:
            _fail("primary_freeze_selected_artifact_missing", family)
        expected_models[family] = entry.model_identity
        expected_normalizers[family] = entry.normalizer_identity
        if family == "conditional":
            if not entry.pca_identity:
                _fail("primary_freeze_selected_artifact_missing", "conditional.pca")
            expected_pca[family] = entry.pca_identity
        elif entry.pca_identity is not None:
            _fail("primary_freeze_selected_artifact_invalid", "pooled.pca")

    expected_bindings = {
        "model_identities": expected_models,
        "normalizer_identities": expected_normalizers,
        "pca_identities": expected_pca,
    }
    caller_bindings = {
        "model_identities": model_identities,
        "normalizer_identities": normalizer_identities,
        "pca_identities": pca_identities,
    }
    for name, caller_value in caller_bindings.items():
        if caller_value is not None and dict(caller_value) != expected_bindings[name]:
            _fail("primary_freeze_binding_mismatch", name)
    return FrozenPrimaryV21(
        ledger_sha256=ledger.ledger_sha256,
        selected_candidates=ledger.selected_candidates,
        model_identities=expected_models,
        normalizer_identities=expected_normalizers,
        pca_identities=expected_pca,
        frozen_at=frozen_at,
    )
