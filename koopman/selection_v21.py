"""Frozen outer-family selection and test-free Phase 8.1 final publication."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import random
import tempfile
from types import MappingProxyType
from typing import Any

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.evidence_v2 import canonical_json_bytes, canonical_sha256
from koopman.evaluation_v21 import (
    PrimaryTestTokenV21,
    ProtocolEpisodeBindingV21,
)
from koopman.loco_v21 import (
    ELIGIBLE_FAMILIES_V21,
    PRIMARY_METRICS_V21,
    CandidateSpecV21,
)


REQUIRED_HORIZONS_V21 = ("5", "20", "60", "full")
FROZEN_PROMOTION_POLICY_V21 = MappingProxyType(
    {
        "bootstrap_resamples": 2000,
        "bootstrap_seed": 80304,
        "bootstrap_alpha": 0.05,
        "minimum_improvement_fraction": 0.01,
        "noninferiority_fraction": 0.1,
        "conditional_margin_fraction": 0.05,
    }
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _metric_map(
    value: Mapping[str, float | None], path: str, *, status: str
) -> Mapping[str, float | None]:
    if set(value) != set(PRIMARY_METRICS_V21):
        _fail("outer_metric_set_mismatch", path)
    result: dict[str, float | None] = {}
    for metric in PRIMARY_METRICS_V21:
        item = value[metric]
        if status == "failed":
            if item is not None:
                _fail("outer_metric_failure_values_invalid", f"{path}.{metric}")
            result[metric] = None
        else:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                _fail("outer_metric_invalid", f"{path}.{metric}")
            number = float(item)
            if not math.isfinite(number) or number < 0.0:
                _fail("outer_metric_invalid", f"{path}.{metric}")
            result[metric] = number
    return MappingProxyType(result)


@dataclass(frozen=True)
class HorizonOuterEvidenceV21:
    metrics: Mapping[str, float | None]
    status: str
    reason_code: str | None
    transition_count: int
    window_count: int
    nonfinite_count: int
    invalid_quaternion_count: int
    quaternion_unit_norm_drift_count: int
    quaternion_projection_count: int
    divergence_count: int

    def __post_init__(self) -> None:
        if self.status not in {"success", "failed"} or (
            (self.status == "success") != (self.reason_code is None)
        ):
            _fail("outer_horizon_status_invalid")
        object.__setattr__(
            self,
            "metrics",
            _metric_map(self.metrics, "horizon", status=self.status),
        )
        for name in (
            "transition_count",
            "window_count",
            "nonfinite_count",
            "invalid_quaternion_count",
            "quaternion_unit_norm_drift_count",
            "quaternion_projection_count",
            "divergence_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _fail("outer_health_count_invalid", name)
        if self.transition_count == 0 or self.window_count == 0:
            _fail("outer_evidence_count_invalid")
        if self.quaternion_projection_count != 0:
            _fail("quaternion_projection_forbidden")

    def to_dict(self) -> dict[str, Any]:
        return {
            "divergence_count": self.divergence_count,
            "invalid_quaternion_count": self.invalid_quaternion_count,
            "metrics": dict(self.metrics),
            "nonfinite_count": self.nonfinite_count,
            "quaternion_projection_count": self.quaternion_projection_count,
            "quaternion_unit_norm_drift_count": self.quaternion_unit_norm_drift_count,
            "reason_code": self.reason_code,
            "status": self.status,
            "transition_count": self.transition_count,
            "window_count": self.window_count,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HorizonOuterEvidenceV21":
        if not isinstance(value, Mapping) or set(value) != {
            "divergence_count",
            "invalid_quaternion_count",
            "metrics",
            "nonfinite_count",
            "quaternion_projection_count",
            "quaternion_unit_norm_drift_count",
            "reason_code",
            "status",
            "transition_count",
            "window_count",
        }:
            _fail("outer_horizon_evidence_invalid")
        return cls(
            metrics=value["metrics"],
            status=value["status"],
            reason_code=value["reason_code"],
            transition_count=value["transition_count"],
            window_count=value["window_count"],
            nonfinite_count=value["nonfinite_count"],
            invalid_quaternion_count=value["invalid_quaternion_count"],
            quaternion_unit_norm_drift_count=value[
                "quaternion_unit_norm_drift_count"
            ],
            quaternion_projection_count=value["quaternion_projection_count"],
            divergence_count=value["divergence_count"],
        )


@dataclass(frozen=True)
class EpisodeOuterEvidenceV21:
    binding: ProtocolEpisodeBindingV21
    horizons: Mapping[str, HorizonOuterEvidenceV21]

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ProtocolEpisodeBindingV21):
            _fail("outer_episode_binding_invalid")
        if self.binding.role != "test":
            _fail("outer_episode_protocol_binding_mismatch")
        if set(self.horizons) != set(REQUIRED_HORIZONS_V21):
            _fail("outer_horizon_set_mismatch")
        object.__setattr__(
            self,
            "horizons",
            MappingProxyType(
                {name: self.horizons[name] for name in REQUIRED_HORIZONS_V21}
            ),
        )

    @property
    def episode_id(self) -> str:
        return self.binding.episode_id

    @property
    def configuration(self) -> str:
        return self.binding.configuration

    @property
    def family_repetition(self) -> str:
        return self.binding.family_repetition

    @property
    def transition_sha256(self) -> str:
        return self.binding.transition_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding": self.binding.to_dict(),
            "horizons": {
                name: horizon.to_dict() for name, horizon in self.horizons.items()
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EpisodeOuterEvidenceV21":
        if not isinstance(value, Mapping) or set(value) != {"binding", "horizons"}:
            _fail("outer_episode_evidence_invalid")
        return cls(
            binding=ProtocolEpisodeBindingV21(**dict(value["binding"])),
            horizons={
                name: HorizonOuterEvidenceV21.from_dict(horizon)
                for name, horizon in value["horizons"].items()
            },
        )


@dataclass(frozen=True)
class BaselineOuterEvidenceV21:
    role: str
    episodes: tuple[EpisodeOuterEvidenceV21, ...]
    selection_eligible: bool = False

    def __post_init__(self) -> None:
        if self.role not in {"persistence", "simple_linear"}:
            _fail("baseline_role_invalid")
        if self.selection_eligible is not False:
            _fail("baseline_selection_eligible")
        object.__setattr__(self, "episodes", tuple(self.episodes))
        if not self.episodes:
            _fail("outer_episode_set_invalid")


@dataclass(frozen=True)
class EligibleFamilyOuterEvidenceV21:
    family: str
    selection_eligible: bool
    status: str
    reason_code: str | None
    episodes: tuple[EpisodeOuterEvidenceV21, ...]

    def __post_init__(self) -> None:
        if self.family not in ELIGIBLE_FAMILIES_V21 or self.selection_eligible is not True:
            _fail("outer_family_ineligible")
        if self.status not in {"success", "failed"}:
            _fail("outer_family_status_invalid")
        object.__setattr__(self, "episodes", tuple(self.episodes))
        if self.status == "success":
            if self.reason_code is not None or not self.episodes:
                _fail("outer_family_outcome_invalid")
        elif not self.reason_code:
            _fail("outer_family_outcome_invalid")


@dataclass(frozen=True)
class FoldOuterEvidenceV21:
    heldout_configuration: str
    test_token: PrimaryTestTokenV21
    persistence: BaselineOuterEvidenceV21
    simple_linear: BaselineOuterEvidenceV21
    pooled: EligibleFamilyOuterEvidenceV21
    conditional: EligibleFamilyOuterEvidenceV21

    def __post_init__(self) -> None:
        if (
            not isinstance(self.test_token, PrimaryTestTokenV21)
            or self.test_token.heldout_configuration != self.heldout_configuration
        ):
            _fail("outer_test_token_binding_mismatch")
        if self.persistence.role != "persistence" or self.simple_linear.role != "simple_linear":
            _fail("outer_role_binding_invalid")
        if self.pooled.family != "pooled" or self.conditional.family != "conditional":
            _fail("outer_role_binding_invalid")
        _validate_fold_episode_bindings(self)

    @property
    def completed(self) -> bool:
        """Completion is derived from the frozen token and exact evidence set."""

        _validate_fold_episode_bindings(self)
        return True


def _validate_fold_episode_bindings(fold: FoldOuterEvidenceV21) -> None:
    token = fold.test_token
    expected = tuple(
        zip(
            token.test_episode_ids,
            token.test_transition_sha256s,
            token.test_family_repetitions,
            strict=True,
        )
    )
    for evidence in (
        fold.persistence,
        fold.simple_linear,
        fold.pooled,
        fold.conditional,
    ):
        if (
            isinstance(evidence, EligibleFamilyOuterEvidenceV21)
            and evidence.status == "failed"
            and not evidence.episodes
        ):
            continue
        actual = tuple(
            (
                episode.episode_id,
                episode.transition_sha256,
                episode.family_repetition,
            )
            for episode in evidence.episodes
        )
        if actual != expected or any(
            episode.configuration != fold.heldout_configuration
            or episode.binding.role != "test"
            or episode.binding.role_protocol_sha256 != token.role_protocol_sha256
            for episode in evidence.episodes
        ):
            _fail("outer_episode_protocol_binding_mismatch")


def fold_outer_evidence_to_dict_v21(fold: FoldOuterEvidenceV21) -> dict[str, Any]:
    def role_payload(value: Any) -> dict[str, Any]:
        result = {
            "episodes": [episode.to_dict() for episode in value.episodes],
            "selection_eligible": value.selection_eligible,
        }
        if isinstance(value, BaselineOuterEvidenceV21):
            result["role"] = value.role
        else:
            result.update(
                {
                    "family": value.family,
                    "reason_code": value.reason_code,
                    "status": value.status,
                }
            )
        return result

    return {
        "conditional": role_payload(fold.conditional),
        "heldout_configuration": fold.heldout_configuration,
        "persistence": role_payload(fold.persistence),
        "pooled": role_payload(fold.pooled),
        "simple_linear": role_payload(fold.simple_linear),
        "test_token": fold.test_token.to_dict(),
    }


def fold_outer_evidence_from_dict_v21(value: Mapping[str, Any]) -> FoldOuterEvidenceV21:
    if not isinstance(value, Mapping) or set(value) != {
        "conditional",
        "heldout_configuration",
        "persistence",
        "pooled",
        "simple_linear",
        "test_token",
    }:
        _fail("outer_fold_evidence_invalid")

    def episodes(payload: Mapping[str, Any]) -> tuple[EpisodeOuterEvidenceV21, ...]:
        raw = payload.get("episodes")
        if not isinstance(raw, list):
            _fail("outer_fold_evidence_invalid")
        return tuple(EpisodeOuterEvidenceV21.from_dict(item) for item in raw)

    persistence = value["persistence"]
    simple = value["simple_linear"]
    pooled = value["pooled"]
    conditional = value["conditional"]
    return FoldOuterEvidenceV21(
        heldout_configuration=str(value["heldout_configuration"]),
        test_token=PrimaryTestTokenV21.from_dict(value["test_token"]),
        persistence=BaselineOuterEvidenceV21(
            role=str(persistence["role"]),
            episodes=episodes(persistence),
            selection_eligible=persistence["selection_eligible"],
        ),
        simple_linear=BaselineOuterEvidenceV21(
            role=str(simple["role"]),
            episodes=episodes(simple),
            selection_eligible=simple["selection_eligible"],
        ),
        pooled=EligibleFamilyOuterEvidenceV21(
            family=str(pooled["family"]),
            selection_eligible=pooled["selection_eligible"],
            status=str(pooled["status"]),
            reason_code=pooled["reason_code"],
            episodes=episodes(pooled),
        ),
        conditional=EligibleFamilyOuterEvidenceV21(
            family=str(conditional["family"]),
            selection_eligible=conditional["selection_eligible"],
            status=str(conditional["status"]),
            reason_code=conditional["reason_code"],
            episodes=episodes(conditional),
        ),
    )


@dataclass(frozen=True)
class OuterFamilyDecisionV21:
    status: str
    selected_family: str | None
    reason_codes: tuple[str, ...]
    family_diagnostics: Mapping[str, Any]
    version: str = "phase8.1-outer-family-decision-v1"
    decision_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(
            self,
            "family_diagnostics",
            _deep_freeze(self.family_diagnostics),
        )
        if self.status == "SELECTION":
            if self.selected_family not in ELIGIBLE_FAMILIES_V21:
                _fail("outer_selected_family_invalid")
        elif self.status == "NO_SELECTION":
            if self.selected_family is not None:
                _fail("outer_no_selection_family_forbidden")
        else:
            _fail("outer_selection_status_invalid")
        object.__setattr__(
            self,
            "decision_sha256",
            canonical_sha256(
                {
                    "family_diagnostics": _plain_diagnostics(self.family_diagnostics),
                    "reason_codes": list(self.reason_codes),
                    "selected_family": self.selected_family,
                    "status": self.status,
                    "version": self.version,
                }
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_sha256": self.decision_sha256,
            "family_diagnostics": _plain_diagnostics(self.family_diagnostics),
            "reason_codes": list(self.reason_codes),
            "selected_family": self.selected_family,
            "status": self.status,
            "version": self.version,
        }


def _plain_diagnostics(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_diagnostics(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_diagnostics(item) for item in value]
    return value


def _combine(
    folds: Sequence[FoldOuterEvidenceV21], role: str
) -> Mapping[tuple[str, str], EpisodeOuterEvidenceV21]:
    result: dict[tuple[str, str], EpisodeOuterEvidenceV21] = {}
    for fold in folds:
        evidence = getattr(fold, role)
        episodes = evidence.episodes
        for episode in episodes:
            if episode.configuration != fold.heldout_configuration:
                _fail("outer_episode_configuration_mismatch")
            key = episode.configuration, episode.family_repetition
            if key in result:
                _fail("outer_episode_duplicate")
            result[key] = episode
    return MappingProxyType(result)


def _macro(
    episodes: Mapping[tuple[str, str], EpisodeOuterEvidenceV21], metric: str
) -> float:
    per_configuration: list[float] = []
    for configuration in SUPPORTED_EMBODIMENTS:
        values = [
            _successful_metric(episode.horizons["full"], metric)
            for key, episode in episodes.items()
            if key[0] == configuration
        ]
        if not values:
            _fail("outer_episode_pairing_mismatch", configuration)
        per_configuration.append(sum(values) / len(values))
    return sum(per_configuration) / len(per_configuration)


def _successful_metric(horizon: HorizonOuterEvidenceV21, metric: str) -> float:
    if horizon.status != "success":
        _fail("failed_horizon_aggregation_forbidden", horizon.reason_code)
    value = horizon.metrics[metric]
    if value is None:
        _fail("failed_horizon_aggregation_forbidden", metric)
    return float(value)


def _paired_lower_bound(
    baseline: Mapping[tuple[str, str], EpisodeOuterEvidenceV21],
    candidate: Mapping[tuple[str, str], EpisodeOuterEvidenceV21],
    metric: str,
) -> float:
    if set(baseline) != set(candidate):
        _fail("bootstrap_pairing_mismatch")
    pairs: dict[str, list[float]] = {}
    for configuration in SUPPORTED_EMBODIMENTS:
        keys = sorted(key for key in baseline if key[0] == configuration)
        pairs[configuration] = [
            _successful_metric(baseline[key].horizons["full"], metric)
            - _successful_metric(candidate[key].horizons["full"], metric)
            for key in keys
        ]
    rng = random.Random(int(FROZEN_PROMOTION_POLICY_V21["bootstrap_seed"]))
    samples: list[float] = []
    for _ in range(int(FROZEN_PROMOTION_POLICY_V21["bootstrap_resamples"])):
        configuration_means = []
        for configuration in SUPPORTED_EMBODIMENTS:
            values = pairs[configuration]
            configuration_means.append(
                sum(rng.choice(values) for _ in values) / len(values)
            )
        samples.append(sum(configuration_means) / len(configuration_means))
    samples.sort()
    index = int(
        float(FROZEN_PROMOTION_POLICY_V21["bootstrap_alpha"]) * len(samples)
    )
    return samples[max(0, min(index, len(samples) - 1))]


def _family_diagnostics(
    family: str,
    roles: Mapping[str, Mapping[tuple[str, str], EpisodeOuterEvidenceV21]],
    role_status: Mapping[str, str],
) -> dict[str, Any]:
    if role_status[family] != "success":
        return {
            "all_hard_gates_pass": False,
            "baseline_gates_pass": False,
            "conditional_margin_pass": False,
            "reason_codes": ["role_failed"],
        }
    if any(
        role_status[name] != "success"
        for name in ("persistence", "simple_linear")
    ):
        return {
            "all_hard_gates_pass": False,
            "baseline_gates_pass": False,
            "conditional_margin_pass": False,
            "reason_codes": ["baseline_role_failed"],
        }
    candidate = roles[family]
    reasons: list[str] = []
    health = {
        count: sum(
            getattr(episode.horizons[horizon], count)
            for episode in candidate.values()
            for horizon in REQUIRED_HORIZONS_V21
        )
        for count in (
            "nonfinite_count",
            "invalid_quaternion_count",
            "quaternion_unit_norm_drift_count",
            "divergence_count",
        )
    }
    if any(health.values()):
        reasons.append("finite_quaternion_divergence_gate_failed")
    baseline_checks: dict[str, Any] = {}
    for baseline_name in ("persistence", "simple_linear"):
        baseline = roles[baseline_name]
        if set(baseline) != set(candidate):
            _fail("outer_episode_pairing_mismatch")
        metric_checks: dict[str, Any] = {}
        for metric in PRIMARY_METRICS_V21:
            baseline_macro = _macro(baseline, metric)
            candidate_macro = _macro(candidate, metric)
            improvement_pass = candidate_macro <= baseline_macro * (
                1.0
                - float(FROZEN_PROMOTION_POLICY_V21["minimum_improvement_fraction"])
            )
            lower_bound = _paired_lower_bound(baseline, candidate, metric)
            bootstrap_pass = lower_bound > 0.0
            per_configuration_pass = True
            for configuration in SUPPORTED_EMBODIMENTS:
                baseline_values = [
                    _successful_metric(episode.horizons["full"], metric)
                    for key, episode in baseline.items()
                    if key[0] == configuration
                ]
                candidate_values = [
                    _successful_metric(episode.horizons["full"], metric)
                    for key, episode in candidate.items()
                    if key[0] == configuration
                ]
                if sum(candidate_values) / len(candidate_values) > (
                    sum(baseline_values)
                    / len(baseline_values)
                    * (
                        1.0
                        + float(
                            FROZEN_PROMOTION_POLICY_V21["noninferiority_fraction"]
                        )
                    )
                ):
                    per_configuration_pass = False
            metric_checks[metric] = {
                "baseline_macro": baseline_macro,
                "bootstrap_lower_bound": lower_bound,
                "bootstrap_pass": bootstrap_pass,
                "candidate_macro": candidate_macro,
                "improvement_pass": improvement_pass,
                "per_configuration_noninferiority_pass": per_configuration_pass,
            }
            if not (improvement_pass and bootstrap_pass and per_configuration_pass):
                reasons.append("baseline_improvement_failed")
        baseline_checks[baseline_name] = metric_checks
    baseline_pass = "baseline_improvement_failed" not in reasons

    margin_pass = family == "pooled"
    margin: dict[str, Any] = {}
    if family == "conditional":
        pooled = roles["pooled"]
        margin_pass = (
            role_status["pooled"] == "success"
            and bool(pooled)
            and set(pooled) == set(candidate)
        )
        if margin_pass:
            for metric in PRIMARY_METRICS_V21:
                pooled_macro = _macro(pooled, metric)
                conditional_macro = _macro(candidate, metric)
                passed = conditional_macro <= pooled_macro * (
                    1.0
                    - float(
                        FROZEN_PROMOTION_POLICY_V21["conditional_margin_fraction"]
                    )
                )
                margin[metric] = {
                    "conditional_macro": conditional_macro,
                    "pass": passed,
                    "pooled_macro": pooled_macro,
                }
                margin_pass = margin_pass and passed
        if not margin_pass:
            reasons.append("conditional_margin_failed")
    return {
        "all_hard_gates_pass": not reasons,
        "baseline_checks": baseline_checks,
        "baseline_gates_pass": baseline_pass,
        "conditional_margin": margin,
        "conditional_margin_pass": margin_pass,
        "health_counts": health,
        "reason_codes": sorted(set(reasons)),
    }


def select_outer_family_v21(
    folds: Sequence[FoldOuterEvidenceV21],
) -> OuterFamilyDecisionV21:
    """Apply the frozen exact-eight outer gate and emit family identity only."""

    fold_set = tuple(folds)
    if tuple(fold.heldout_configuration for fold in fold_set) != tuple(
        SUPPORTED_EMBODIMENTS
    ):
        _fail("fold_set_mismatch")
    protocol_hashes = {fold.test_token.role_protocol_sha256 for fold in fold_set}
    if len(protocol_hashes) != 1:
        _fail("outer_role_protocol_mismatch")
    for fold in fold_set:
        _validate_fold_episode_bindings(fold)
    roles = {
        role: _combine(fold_set, role)
        for role in ("persistence", "simple_linear", "pooled", "conditional")
    }
    def role_success(role: str) -> bool:
        return all(
            horizon.status == "success"
            for fold in fold_set
            for episode in getattr(fold, role).episodes
            for horizon in episode.horizons.values()
        )

    status = {
        "persistence": "success" if role_success("persistence") else "failed",
        "simple_linear": "success" if role_success("simple_linear") else "failed",
        "pooled": "success"
        if all(fold.pooled.status == "success" for fold in fold_set)
        and role_success("pooled")
        else "failed",
        "conditional": "success"
        if all(fold.conditional.status == "success" for fold in fold_set)
        and role_success("conditional")
        else "failed",
    }
    diagnostics = {
        family: _family_diagnostics(family, roles, status)
        for family in ELIGIBLE_FAMILIES_V21
    }
    if diagnostics["conditional"]["all_hard_gates_pass"]:
        selected: str | None = "conditional"
    elif diagnostics["pooled"]["all_hard_gates_pass"]:
        selected = "pooled"
    else:
        selected = None
    reasons = tuple(
        sorted(
            {
                reason
                for family in ELIGIBLE_FAMILIES_V21
                for reason in diagnostics[family]["reason_codes"]
                if reason != "conditional_margin_failed" or selected is None
            }
        )
    )
    return OuterFamilyDecisionV21(
        status="SELECTION" if selected else "NO_SELECTION",
        selected_family=selected,
        reason_codes=reasons,
        family_diagnostics=diagnostics,
    )


@dataclass(frozen=True)
class FinalRefitEpisodeV21:
    binding: ProtocolEpisodeBindingV21
    payload: Any

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ProtocolEpisodeBindingV21):
            _fail("final_refit_episode_binding_invalid")
        if self.binding.role == "test":
            _fail("final_refit_test_episode_forbidden")
        if self.binding.role not in {"fit", "validation"}:
            _fail("final_refit_episode_role_invalid")
        if (
            not self.binding.episode_id
            or self.binding.configuration not in SUPPORTED_EMBODIMENTS
        ):
            _fail("final_refit_episode_binding_invalid")

    @property
    def episode_id(self) -> str:
        return self.binding.episode_id

    @property
    def configuration(self) -> str:
        return self.binding.configuration

    @property
    def role(self) -> str:
        return self.binding.role

    @property
    def transition_sha256(self) -> str:
        return self.binding.transition_sha256


class FinalRefitDataSourceV21:
    """Exact protocol-bound 48-fit/24-validation source with read audit."""

    def __init__(
        self,
        *,
        registered_episodes: Sequence[ProtocolEpisodeBindingV21],
        role_protocol_sha256: str,
        opener: Callable[[ProtocolEpisodeBindingV21], Any],
    ) -> None:
        bindings = tuple(registered_episodes)
        if (
            len(bindings) != 72
            or len({binding.episode_id for binding in bindings}) != 72
            or any(
                not isinstance(binding, ProtocolEpisodeBindingV21)
                or binding.role not in {"fit", "validation"}
                or binding.configuration not in SUPPORTED_EMBODIMENTS
                or binding.role_protocol_sha256 != role_protocol_sha256
                for binding in bindings
            )
        ):
            _fail("final_refit_registered_episode_set_invalid")
        for configuration in SUPPORTED_EMBODIMENTS:
            for role, expected_count in (("fit", 6), ("validation", 3)):
                selected = tuple(
                    binding
                    for binding in bindings
                    if binding.configuration == configuration and binding.role == role
                )
                if (
                    len(selected) != expected_count
                    or len({binding.family_repetition for binding in selected})
                    != expected_count
                ):
                    _fail("final_refit_registered_episode_set_invalid")
        self._bindings = bindings
        self.role_protocol_sha256 = role_protocol_sha256
        self._opener = opener
        self._opened_roles: list[str] = []
        self._opened_episode_ids: list[str] = []
        self._opened_transition_sha256s: list[str] = []

    @property
    def registered_fit_episode_ids(self) -> tuple[str, ...]:
        return tuple(
            binding.episode_id for binding in self._bindings if binding.role == "fit"
        )

    @property
    def registered_validation_episode_ids(self) -> tuple[str, ...]:
        return tuple(
            binding.episode_id
            for binding in self._bindings
            if binding.role == "validation"
        )

    @property
    def registered_transition_sha256s(self) -> tuple[str, ...]:
        return tuple(binding.transition_sha256 for binding in self._bindings)

    @property
    def opened_roles(self) -> tuple[str, ...]:
        return tuple(self._opened_roles)

    @property
    def opened_episode_ids(self) -> tuple[str, ...]:
        return tuple(self._opened_episode_ids)

    @property
    def opened_transition_sha256s(self) -> tuple[str, ...]:
        return tuple(self._opened_transition_sha256s)

    def open_role(self, role: str) -> tuple[FinalRefitEpisodeV21, ...]:
        if role not in {"fit", "validation"}:
            _fail("final_refit_test_access")
        bindings = tuple(binding for binding in self._bindings if binding.role == role)
        episodes = tuple(
            FinalRefitEpisodeV21(binding, self._opener(binding)) for binding in bindings
        )
        expected_total = 48 if role == "fit" else 24
        if (
            len(episodes) != expected_total
            or any(episode.role != role for episode in episodes)
            or {episode.configuration for episode in episodes} != set(SUPPORTED_EMBODIMENTS)
            or len({episode.episode_id for episode in episodes}) != len(episodes)
        ):
            _fail("final_refit_episode_set_invalid", role)
        self._opened_roles.append(role)
        self._opened_episode_ids.extend(episode.episode_id for episode in episodes)
        self._opened_transition_sha256s.extend(
            episode.transition_sha256 for episode in episodes
        )
        return episodes


@dataclass(frozen=True)
class FinalPublicationResultV21:
    status: str
    selected_family: str | None
    selected_candidate_id: str | None
    selected_model_path: str | None
    reason_code: str | None
    zero_test_read_audit: bool
    version: str = "phase8.1-final-publication-v1"

    def __post_init__(self) -> None:
        if self.status == "SELECTION":
            if (
                self.selected_family not in ELIGIBLE_FAMILIES_V21
                or not self.selected_candidate_id
                or not self.selected_model_path
                or self.reason_code is not None
                or self.zero_test_read_audit is not True
            ):
                _fail("final_publication_result_invalid")
        elif self.status == "NO_SELECTION":
            if (
                self.selected_family is not None
                or self.selected_candidate_id is not None
                or self.selected_model_path is not None
                or not self.reason_code
            ):
                _fail("final_publication_result_invalid")
        else:
            _fail("final_publication_result_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_family": self.selected_family,
            "selected_model_path": self.selected_model_path,
            "status": self.status,
            "version": self.version,
            "zero_test_read_audit": self.zero_test_read_audit,
        }


class FinalRefitPublisherV21:
    """Configured test-free refitter; public decision input is family only."""

    def __init__(
        self,
        *,
        data_source: FinalRefitDataSourceV21,
        candidates_by_family: Mapping[str, Sequence[CandidateSpecV21]],
        inner_selector: Callable[
            [
                str,
                tuple[FinalRefitEpisodeV21, ...],
                tuple[FinalRefitEpisodeV21, ...],
                tuple[CandidateSpecV21, ...],
            ],
            CandidateSpecV21,
        ],
        final_fitter: Callable[
            [CandidateSpecV21, tuple[FinalRefitEpisodeV21, ...]], Any
        ],
        serializer: Callable[[Any], bytes],
        loader: Callable[[bytes], Any],
        model_identity: Callable[[Any], str],
        publication_root: str | Path,
        atomic_replace: Callable[[str | Path, str | Path], Any] | None = None,
    ) -> None:
        self._data_source = data_source
        self._candidates = MappingProxyType(
            {family: tuple(values) for family, values in candidates_by_family.items()}
        )
        self._inner_selector = inner_selector
        self._final_fitter = final_fitter
        self._serializer = serializer
        self._loader = loader
        self._model_identity = model_identity
        self._publication_root = Path(publication_root)
        self._atomic_replace = os.replace if atomic_replace is None else atomic_replace

    def _no_selection(self, reason: str) -> FinalPublicationResultV21:
        return FinalPublicationResultV21(
            status="NO_SELECTION",
            selected_family=None,
            selected_candidate_id=None,
            selected_model_path=None,
            reason_code=reason,
            zero_test_read_audit="test" not in self._data_source.opened_roles,
        )

    def publish(self, selected_family: str) -> FinalPublicationResultV21:
        if selected_family not in ELIGIBLE_FAMILIES_V21:
            return self._no_selection("final_refit_family_invalid")
        candidates = self._candidates.get(selected_family)
        if not candidates or any(candidate.family != selected_family for candidate in candidates):
            return self._no_selection("final_refit_candidate_family_missing")
        if self._data_source.opened_roles:
            return self._no_selection("final_refit_data_source_reused")
        try:
            fit = self._data_source.open_role("fit")
            validation = self._data_source.open_role("validation")
        except Exception:
            return self._no_selection("final_refit_data_open_failed")
        if self._data_source.opened_roles != ("fit", "validation"):
            return self._no_selection("final_refit_zero_test_read_failed")
        try:
            selected = self._inner_selector(
                selected_family, fit, validation, tuple(candidates)
            )
        except Exception:
            return self._no_selection("final_refit_inner_selection_failed")
        if (
            not isinstance(selected, CandidateSpecV21)
            or selected.family != selected_family
            or selected.candidate_id not in {candidate.candidate_id for candidate in candidates}
        ):
            return self._no_selection("final_refit_inner_selection_invalid")
        try:
            model = self._final_fitter(selected, fit + validation)
            serialized = self._serializer(model)
            if not isinstance(serialized, bytes) or not serialized:
                _fail("final_refit_serialization_invalid")
        except Exception:
            return self._no_selection("final_refit_fit_failed")

        target = self._publication_root
        if target.exists():
            return self._no_selection("final_refit_publication_target_exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(
                prefix=".phase81-refit-", dir=target.parent
            ) as staging_name:
                staging = Path(staging_name)
                staged_model = staging / "selected_model.bin"
                with staged_model.open("xb") as stream:
                    stream.write(serialized)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    loaded = self._loader(staged_model.read_bytes())
                    if self._model_identity(loaded) != self._model_identity(model):
                        _fail("final_refit_roundtrip_failed")
                except Exception:
                    return self._no_selection("final_refit_roundtrip_failed")
                manifest = {
                    "opened_episode_ids": list(self._data_source.opened_episode_ids),
                    "opened_transition_sha256s": list(
                        self._data_source.opened_transition_sha256s
                    ),
                    "opened_roles": list(self._data_source.opened_roles),
                    "role_protocol_sha256": self._data_source.role_protocol_sha256,
                    "model_identity": self._model_identity(model),
                    "selected_candidate": selected.to_dict()
                    | {"candidate_id": selected.candidate_id},
                    "selected_family": selected_family,
                    "test_read_count": 0,
                    "version": "phase8.1-final-model-manifest-v1",
                }
                (staging / "selection_result.json").write_bytes(
                    canonical_json_bytes(manifest)
                )
                try:
                    self._atomic_replace(staging, target)
                except Exception:
                    return self._no_selection("atomic_publication_failed")
        except Exception:
            return self._no_selection("atomic_publication_failed")
        model_path = target / "selected_model.bin"
        if not model_path.is_file() or "test" in self._data_source.opened_roles:
            return self._no_selection("final_refit_zero_test_read_failed")
        return FinalPublicationResultV21(
            status="SELECTION",
            selected_family=selected_family,
            selected_candidate_id=selected.candidate_id,
            selected_model_path=str(model_path.resolve()),
            reason_code=None,
            zero_test_read_audit=True,
        )


class DatasetFinalRefitBackendV21:
    """First-party all-eight fit/validation backend for final publication."""

    def __init__(
        self,
        *,
        dataset_root: str | Path,
        analysis_policy_path: str | Path,
        expected_source_commit: str,
        expected_evidence_level: str,
    ) -> None:
        from koopman.evaluation_v21 import DatasetFormalLocoBackendV21

        self._loader = DatasetFormalLocoBackendV21(
            dataset_root=dataset_root,
            analysis_policy_path=analysis_policy_path,
            expected_source_commit=expected_source_commit,
            expected_evidence_level=expected_evidence_level,
        )
        self.analysis_policy = self._loader.analysis_policy
        self.last_inner_ledger: tuple[Mapping[str, Any], ...] = ()

    def open_episode(self, binding: ProtocolEpisodeBindingV21) -> Any:
        return self._loader.open_episode(binding)

    def candidates(self, selected_family: str) -> tuple[CandidateSpecV21, ...]:
        if selected_family not in ELIGIBLE_FAMILIES_V21:
            _fail("final_refit_family_invalid")
        return tuple(
            candidate
            for candidate in self._loader._candidate_grid()
            if candidate.family == selected_family
        )

    @staticmethod
    def _select_fit(
        episodes: Sequence[FinalRefitEpisodeV21],
        *,
        prefix: int,
    ) -> tuple[FinalRefitEpisodeV21, ...]:
        selected = []
        for configuration in SUPPORTED_EMBODIMENTS:
            matches = tuple(
                episode
                for episode in episodes
                if episode.role == "fit" and episode.configuration == configuration
            )
            if len(matches) < prefix:
                _fail("fit_prefix_unavailable", configuration)
            selected.extend(matches[:prefix])
        return tuple(selected)

    @staticmethod
    def _descriptor(dataset: Any) -> Any:
        from koopman.platform_features_v21 import build_physical_core_descriptor_v21

        return build_physical_core_descriptor_v21(dataset.platform_contexts)

    @classmethod
    def _fit_candidate(
        cls,
        candidate: CandidateSpecV21,
        episodes: Sequence[FinalRefitEpisodeV21],
        *,
        use_all_rows: bool,
    ) -> Mapping[str, Any]:
        import numpy as np

        from koopman.model_v21 import (
            CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21,
            ControlledEDMDV21,
            build_increment_targets_v21,
        )
        from koopman.platform_features_v21 import fit_final_refit_pca_v21

        source = tuple(episodes)
        selected = source if use_all_rows else cls._select_fit(
            source, prefix=candidate.data_prefix
        )
        if not selected or {episode.configuration for episode in selected} != set(
            SUPPORTED_EMBODIMENTS
        ):
            _fail("final_refit_episode_set_invalid")
        states = np.concatenate([episode.payload.state_11 for episode in selected])
        memory = np.concatenate(
            [episode.payload.actuator_memory_4 for episode in selected]
        )
        controls = np.concatenate(
            [episode.payload.virtual_control_4 for episode in selected]
        )
        targets = np.concatenate(
            [
                build_increment_targets_v21(
                    episode.payload.state_11, episode.payload.Y
                )
                for episode in selected
            ]
        )
        projector = None
        kwargs: dict[str, Any] = {}
        if candidate.family == "conditional":
            descriptors = {
                configuration: cls._descriptor(
                    next(
                        episode.payload
                        for episode in selected
                        if episode.configuration == configuration
                    )
                )
                for configuration in SUPPORTED_EMBODIMENTS
            }
            projector = fit_final_refit_pca_v21(descriptors)
            scores = {
                configuration: projector.transform(descriptor)
                for configuration, descriptor in descriptors.items()
            }
            kwargs = {
                "platform_scores": np.concatenate(
                    [
                        np.repeat(
                            scores[episode.configuration][None, :],
                            episode.payload.sample_count,
                            axis=0,
                        )
                        for episode in selected
                    ]
                ),
                "row_configurations": tuple(
                    configuration
                    for episode in selected
                    for configuration in [episode.configuration]
                    * episode.payload.sample_count
                ),
                "source_configurations": tuple(SUPPORTED_EMBODIMENTS),
                "population_scope": CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21,
            }
        model = ControlledEDMDV21.fit(
            states,
            memory,
            controls,
            targets,
            observable_schema=candidate.observable_schema,
            conditioning=candidate.conditioning,
            ridge=candidate.ridge,
            normalization=candidate.normalization,
            **kwargs,
        )
        return {
            "candidate": candidate,
            "model": model,
            "projector": projector,
        }

    @classmethod
    def _configuration_errors(
        cls,
        bundle: Mapping[str, Any],
        validation: Sequence[FinalRefitEpisodeV21],
    ) -> Mapping[str, Mapping[str, float]] | None:
        result: dict[str, Mapping[str, float]] = {}
        model = bundle["model"]
        projector = bundle["projector"]
        for configuration in SUPPORTED_EMBODIMENTS:
            values = []
            for episode in validation:
                if episode.configuration != configuration:
                    continue
                artifact = __import__(
                    "koopman.evaluation_v21", fromlist=["DatasetFormalLocoBackendV21"]
                ).DatasetFormalLocoBackendV21._artifact(
                    model,
                    episode.payload,
                    projector=projector,
                )
                values.append(artifact.horizons["full"])
            if not values or any(value.status != "success" for value in values):
                return None
            result[configuration] = {
                metric: sum(float(value.values[metric]) for value in values)
                / len(values)
                for metric in PRIMARY_METRICS_V21
            }
        return MappingProxyType(result)

    @staticmethod
    def _macro(
        errors: Mapping[str, Mapping[str, float]],
    ) -> Mapping[str, float]:
        return MappingProxyType(
            {
                metric: sum(float(errors[configuration][metric]) for configuration in SUPPORTED_EMBODIMENTS)
                / len(SUPPORTED_EMBODIMENTS)
                for metric in PRIMARY_METRICS_V21
            }
        )

    def inner_select(
        self,
        selected_family: str,
        fit: tuple[FinalRefitEpisodeV21, ...],
        validation: tuple[FinalRefitEpisodeV21, ...],
        candidates: tuple[CandidateSpecV21, ...],
    ) -> CandidateSpecV21:
        from koopman.loco_v21 import robust_relative_source_score_v21

        if (
            selected_family not in ELIGIBLE_FAMILIES_V21
            or len(fit) != 48
            or len(validation) != 24
            or not candidates
            or any(candidate.family != selected_family for candidate in candidates)
        ):
            _fail("final_refit_inner_selection_invalid")
        persistence_bundle = {
            "model": __import__(
                "koopman.evaluation_v21", fromlist=["_PersistenceIncrementModelV21"]
            )._PersistenceIncrementModelV21(),
            "projector": None,
        }
        persistence_errors = self._configuration_errors(
            persistence_bundle, validation
        )
        if persistence_errors is None:
            _fail("persistence_validation_failed")
        entries = []
        for candidate in candidates:
            try:
                bundle = self._fit_candidate(
                    candidate, fit, use_all_rows=False
                )
                candidate_errors = self._configuration_errors(bundle, validation)
                simple_spec = CandidateSpecV21(
                    family="pooled",
                    observable_schema="so3_identity_v1",
                    data_prefix=candidate.data_prefix,
                    ridge=candidate.ridge,
                    normalization=candidate.normalization,
                    conditioning="none",
                    label=f"final-simple:{candidate.candidate_id}",
                )
                simple_bundle = self._fit_candidate(
                    simple_spec, fit, use_all_rows=False
                )
                simple_errors = self._configuration_errors(simple_bundle, validation)
                if candidate_errors is None or simple_errors is None:
                    raise ValueError("final_refit_validation_failed")
                source_score, ratios = robust_relative_source_score_v21(
                    self._macro(candidate_errors),
                    self._macro(persistence_errors),
                    self._macro(simple_errors),
                )
                entries.append(
                    {
                        "candidate": candidate,
                        "candidate_id": candidate.candidate_id,
                        "ratios": dict(ratios),
                        "rejection_reason": None,
                        "source_score": source_score,
                        "status": "success",
                    }
                )
            except Exception as exc:
                entries.append(
                    {
                        "candidate": candidate,
                        "candidate_id": candidate.candidate_id,
                        "ratios": {},
                        "rejection_reason": str(exc) or "final_refit_candidate_failed",
                        "source_score": None,
                        "status": "failed",
                    }
                )
        self.last_inner_ledger = tuple(
            MappingProxyType(
                {
                    **{key: value for key, value in entry.items() if key != "candidate"},
                    "candidate": entry["candidate"].to_dict(),
                }
            )
            for entry in entries
        )
        eligible = [entry for entry in entries if entry["status"] == "success"]
        if not eligible:
            _fail("final_refit_candidate_set_failed")
        eligible.sort(
            key=lambda entry: (
                float(entry["source_score"]),
                entry["candidate"].data_prefix,
                0
                if entry["candidate"].observable_schema == "so3_identity_v1"
                else 1,
                entry["candidate"].ridge,
                0 if entry["candidate"].normalization == "none" else 1,
                entry["candidate"].candidate_id,
            )
        )
        return eligible[0]["candidate"]

    def final_fit(
        self,
        candidate: CandidateSpecV21,
        episodes: tuple[FinalRefitEpisodeV21, ...],
    ) -> Mapping[str, Any]:
        if len(episodes) != 72 or any(episode.role == "test" for episode in episodes):
            _fail("final_refit_episode_set_invalid")
        return self._fit_candidate(candidate, episodes, use_all_rows=True)

    @staticmethod
    def serialize(bundle: Mapping[str, Any]) -> bytes:
        from koopman.evidence_v2 import canonical_json_bytes

        candidate = bundle["candidate"]
        model = bundle["model"]
        projector = bundle["projector"]
        return canonical_json_bytes(
            {
                "candidate": candidate.to_dict()
                | {"candidate_id": candidate.candidate_id},
                "model": model.to_dict(),
                "projector": None if projector is None else projector.to_dict(),
                "version": "phase8.1-final-refit-model-bundle-v1",
            }
        )

    @staticmethod
    def load(data: bytes) -> Mapping[str, Any]:
        import json

        from koopman.model_v21 import ControlledEDMDV21
        from koopman.platform_features_v21 import SourcePCAProjectorV21

        value = json.loads(data)
        if value.get("version") != "phase8.1-final-refit-model-bundle-v1":
            _fail("final_refit_model_bundle_invalid")
        candidate_payload = dict(value["candidate"])
        candidate_id = candidate_payload.pop("candidate_id")
        candidate = CandidateSpecV21(**candidate_payload)
        if candidate.candidate_id != candidate_id:
            _fail("final_refit_model_bundle_invalid")
        return {
            "candidate": candidate,
            "model": ControlledEDMDV21.from_dict(value["model"]),
            "projector": (
                None
                if value["projector"] is None
                else SourcePCAProjectorV21.from_dict(value["projector"])
            ),
        }

    @staticmethod
    def model_identity(bundle: Mapping[str, Any]) -> tuple[str, str, str | None]:
        return (
            bundle["candidate"].candidate_id,
            bundle["model"].model_sha256,
            (
                None
                if bundle["projector"] is None
                else bundle["projector"].projector_sha256
            ),
        )
