"""Fail-closed Phase 8 selection and test-free final-refit contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import math
from pathlib import Path
import random
from types import MappingProxyType
from typing import Any

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.evidence_v2 import file_sha256, load_bounded_json, validate_phase8_evidence
from koopman.metrics_v2 import OFFICIAL_ERROR_METRICS_V2, REQUIRED_HORIZON_LABELS_V2
from koopman.protocol_v2 import AnalysisPolicyV2, load_analysis_policy_v1


SELECTION_RESULT_VERSION_V2 = "phase8-selection-result-v1"
EVALUATION_RESULT_VERSION_V2 = "phase8-ood-evaluation-v1"
ELIGIBLE_FAMILIES_V2 = ("pooled_koopman_v2", "conditional_koopman_v2")
REQUIRED_ROLES_V2 = (
    "persistence",
    "simple_linear_v2",
    "source_per_configuration_koopman_v2",
    "pooled_koopman_v2",
    "conditional_koopman_v2",
    "heldout_expert_upper_bound_v2",
)
PRIMARY_INPUTS_V2 = ("state_11", "virtual_control_4")
CONDITIONAL_INPUTS_V2 = (*PRIMARY_INPUTS_V2, "platform_physical_descriptor")


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("metric_value_invalid", path)
    result = float(value)
    if not math.isfinite(result):
        _fail("metric_nonfinite", path)
    return result


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("type_invalid", path)
    return value


def _evaluation_summary_path(envelope_path: Path) -> Path:
    envelope = load_bounded_json(envelope_path)
    references = envelope.get("referenced_files")
    if not isinstance(references, list):
        _fail("reference_set_invalid")
    matches = [item for item in references if item.get("path") == "evaluation_summary.json"]
    if len(matches) != 1:
        _fail("evaluation_summary_reference_invalid")
    path = envelope_path.parent / "evaluation_summary.json"
    if file_sha256(path) != matches[0].get("sha256"):
        _fail("reference_hash_mismatch", "evaluation_summary.json")
    if file_sha256(path) != envelope.get("decision_sha256"):
        _fail("decision_hash_mismatch")
    return path


def _validate_freeze(fold: Mapping[str, Any], policy: AnalysisPolicyV2) -> None:
    decision = _mapping(fold.get("decision"), "decision")
    frozen = _mapping(fold.get("pre_test_freeze"), "pre_test_freeze")
    access = _mapping(fold.get("test_access"), "test_access")
    if frozen.get("state") != "frozen":
        _fail("primary_freeze_missing")
    if frozen.get("candidate_id") != decision.get("candidate_id"):
        _fail("freeze_candidate_mismatch")
    if frozen.get("decision_sha256") != decision.get("decision_sha256"):
        _fail("freeze_decision_mismatch")
    if frozen.get("analysis_policy_sha256") != policy.policy_sha256:
        _fail("analysis_policy_drift")
    if frozen.get("source_configurations") != fold.get("source_configurations"):
        _fail("heldout_design_leakage")
    if any(
        frozen.get(name) != 0
        for name in (
            "candidate_revision",
            "model_revision",
            "test_open_count_at_freeze",
            "post_test_mutation_count",
        )
    ):
        _fail("post_test_retune")
    models = _mapping(frozen.get("primary_model_sha256s"), "primary_model_sha256s")
    if set(models) != {
        "simple_linear_v2",
        "source_per_configuration_koopman_v2",
        "pooled_koopman_v2",
        "conditional_koopman_v2",
    } or any(not _is_sha256(value) for value in models.values()):
        _fail("primary_freeze_model_set_invalid")
    if access.get("authorized_by_freeze") is not True:
        _fail("primary_test_access_unauthorized")
    if access.get("freeze_candidate_id") != frozen.get("candidate_id"):
        _fail("freeze_candidate_mismatch")
    episodes = access.get("test_episode_ids")
    if not isinstance(episodes, list) or len(episodes) != 3 or len(set(episodes)) != 3:
        _fail("outer_test_binding_mismatch")


def _validate_role(
    fold: Mapping[str, Any], role_name: str, role: Mapping[str, Any]
) -> dict[tuple[str, str], Mapping[str, Any]]:
    expected_eligible = role_name in ELIGIBLE_FAMILIES_V2
    if role.get("role") != role_name:
        _fail("role_binding_mismatch", role_name)
    if role_name == "heldout_expert_upper_bound_v2" and role.get("selection_eligible") is not False:
        _fail("expert_promotion_forbidden")
    if role.get("selection_eligible") is not expected_eligible:
        _fail("role_eligibility_invalid", role_name)
    expected_inputs = CONDITIONAL_INPUTS_V2 if role_name == "conditional_koopman_v2" else PRIMARY_INPUTS_V2
    if tuple(role.get("input_fields", ())) != expected_inputs:
        _fail("model_input_forbidden", role_name)
    if role.get("status") not in {"success", "failed"}:
        _fail("role_status_invalid", role_name)
    if role.get("status") == "failed":
        if not role.get("reason_code"):
            _fail("role_reason_code_invalid", role_name)
        return {}
    if role.get("reason_code") is not None:
        _fail("role_reason_code_invalid", role_name)
    if role_name != "persistence" and not _is_sha256(role.get("model_sha256")):
        _fail("model_hash_invalid", role_name)
    episodes = role.get("episode_results")
    expected_ids = tuple(fold["test_access"]["test_episode_ids"])
    if not isinstance(episodes, list) or len(episodes) != len(expected_ids):
        _fail("episode_result_set_mismatch", role_name)
    results: dict[tuple[str, str], Mapping[str, Any]] = {}
    actual_ids: list[str] = []
    for episode in episodes:
        item = _mapping(episode, f"{role_name}.episode")
        configuration = str(item.get("configuration"))
        family = str(item.get("family_repetition"))
        episode_id = str(item.get("episode_id"))
        if configuration != fold.get("holdout_configuration"):
            _fail("heldout_result_binding_mismatch")
        if (configuration, family) in results:
            _fail("duplicate_episode_result")
        horizons = _mapping(item.get("horizons"), "horizons")
        if len(horizons) != len(REQUIRED_HORIZON_LABELS_V2) or set(horizons) != set(
            REQUIRED_HORIZON_LABELS_V2
        ):
            _fail("aggregate_horizon_set_mismatch")
        for horizon_name, horizon in horizons.items():
            entry = _mapping(horizon, f"horizon.{horizon_name}")
            if entry.get("status") not in {"success", "failed"}:
                _fail("metric_status_invalid")
            values = _mapping(entry.get("values"), "metric.values")
            if len(values) != len(OFFICIAL_ERROR_METRICS_V2) or set(values) != set(
                OFFICIAL_ERROR_METRICS_V2
            ):
                _fail("metric_schema_mismatch")
            for metric_name, value in values.items():
                if entry.get("status") == "success":
                    _finite(value, f"{horizon_name}.{metric_name}")
                elif value is not None:
                    _fail("metric_failure_values_invalid")
            for count_name in (
                "nonfinite_count",
                "invalid_quaternion_count",
                "projection_failure_count",
                "divergence_count",
            ):
                count = entry.get(count_name)
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    _fail("metric_count_invalid", count_name)
        results[(configuration, family)] = item
        actual_ids.append(episode_id)
    if tuple(actual_ids) != expected_ids:
        _fail("episode_result_set_mismatch", role_name)
    return results


def _paired_lower_bound(
    baseline: Mapping[tuple[str, str], Mapping[str, Any]],
    candidate: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    metric: str,
    policy: AnalysisPolicyV2,
) -> float:
    bootstrap = policy.bootstrap
    configurations = tuple(SUPPORTED_EMBODIMENTS)
    pairs_by_configuration: dict[str, list[float]] = {}
    for configuration in configurations:
        keys = sorted(key for key in baseline if key[0] == configuration)
        if keys != sorted(key for key in candidate if key[0] == configuration):
            _fail("bootstrap_pairing_mismatch", configuration)
        pairs_by_configuration[configuration] = [
            _finite(baseline[key]["horizons"]["full"]["values"][metric], metric)
            - _finite(candidate[key]["horizons"]["full"]["values"][metric], metric)
            for key in keys
        ]
    rng = random.Random(int(bootstrap["seed"]))
    samples: list[float] = []
    for _ in range(int(bootstrap["resamples"])):
        per_configuration = []
        for configuration in configurations:
            blocks = pairs_by_configuration[configuration]
            per_configuration.append(
                sum(rng.choice(blocks) for _ in blocks) / len(blocks)
            )
        samples.append(sum(per_configuration) / len(per_configuration))
    samples.sort()
    index = max(0, min(len(samples) - 1, int(float(bootstrap["alpha"]) * len(samples))))
    return samples[index]


def _family_diagnostics(
    family: str,
    role_results: Mapping[str, Mapping[tuple[str, str], Mapping[str, Any]]],
    policy: AnalysisPolicyV2,
) -> dict[str, Any]:
    candidate = role_results[family]
    if not candidate:
        return {
            "all_hard_gates_pass": False,
            "baseline_gates_pass": False,
            "conditional_margin_pass": False,
            "reason_codes": ["role_failed"],
        }
    gate = policy.gate_template
    reasons: list[str] = []
    health_counts = {
        name: sum(
            int(episode["horizons"][horizon][name])
            for episode in candidate.values()
            for horizon in REQUIRED_HORIZON_LABELS_V2
        )
        for name in (
            "nonfinite_count",
            "invalid_quaternion_count",
            "divergence_count",
        )
    }
    if (
        health_counts["nonfinite_count"] > int(gate["nonfinite_max"])
        or health_counts["invalid_quaternion_count"] > int(gate["invalid_quaternion_max"])
        or health_counts["divergence_count"] > int(gate["divergence_max"])
    ):
        reasons.append("finite_quaternion_divergence_gate_failed")

    baseline_checks: dict[str, Any] = {}
    for baseline_name in ("persistence", "simple_linear_v2"):
        baseline = role_results[baseline_name]
        metric_checks: dict[str, Any] = {}
        for metric in OFFICIAL_ERROR_METRICS_V2:
            baseline_macro = sum(
                _finite(item["horizons"]["full"]["values"][metric], metric)
                for item in baseline.values()
            ) / len(baseline)
            candidate_macro = sum(
                _finite(item["horizons"]["full"]["values"][metric], metric)
                for item in candidate.values()
            ) / len(candidate)
            minimum = float(gate["minimum_improvement_fraction"])
            improvement_pass = candidate_macro <= baseline_macro * (1.0 - minimum)
            lower_bound = _paired_lower_bound(
                baseline, candidate, metric=metric, policy=policy
            )
            bootstrap_pass = lower_bound > 0.0
            per_configuration_pass = True
            for configuration in SUPPORTED_EMBODIMENTS:
                baseline_values = [
                    _finite(value["horizons"]["full"]["values"][metric], metric)
                    for key, value in baseline.items()
                    if key[0] == configuration
                ]
                candidate_values = [
                    _finite(value["horizons"]["full"]["values"][metric], metric)
                    for key, value in candidate.items()
                    if key[0] == configuration
                ]
                if (
                    sum(candidate_values) / len(candidate_values)
                    > (sum(baseline_values) / len(baseline_values))
                    * (1.0 + float(gate["noninferiority_fraction"]))
                ):
                    per_configuration_pass = False
            metric_checks[metric] = {
                "baseline_macro": baseline_macro,
                "candidate_macro": candidate_macro,
                "improvement_pass": improvement_pass,
                "bootstrap_lower_bound": lower_bound,
                "bootstrap_pass": bootstrap_pass,
                "per_configuration_noninferiority_pass": per_configuration_pass,
            }
            if not (improvement_pass and bootstrap_pass and per_configuration_pass):
                reasons.append("baseline_improvement_failed")
        baseline_checks[baseline_name] = metric_checks
    baseline_pass = "baseline_improvement_failed" not in reasons

    conditional_margin_pass = family != "conditional_koopman_v2"
    conditional_margin: dict[str, Any] = {}
    if family == "conditional_koopman_v2":
        pooled = role_results["pooled_koopman_v2"]
        conditional_margin_pass = bool(pooled)
        for metric in OFFICIAL_ERROR_METRICS_V2:
            pooled_macro = sum(
                _finite(item["horizons"]["full"]["values"][metric], metric)
                for item in pooled.values()
            ) / len(pooled)
            candidate_macro = sum(
                _finite(item["horizons"]["full"]["values"][metric], metric)
                for item in candidate.values()
            ) / len(candidate)
            passed = candidate_macro <= pooled_macro * (
                1.0 - float(gate["conditional_margin_fraction"])
            )
            conditional_margin[metric] = {
                "pooled_macro": pooled_macro,
                "conditional_macro": candidate_macro,
                "pass": passed,
            }
            conditional_margin_pass = conditional_margin_pass and passed
        if not conditional_margin_pass:
            reasons.append("conditional_margin_failed")
    return {
        "all_hard_gates_pass": not reasons,
        "baseline_gates_pass": baseline_pass,
        "baseline_checks": baseline_checks,
        "conditional_margin": conditional_margin,
        "conditional_margin_pass": conditional_margin_pass,
        "health_counts": health_counts,
        "reason_codes": sorted(set(reasons)),
    }


@dataclass(frozen=True)
class Phase8SelectionResultV2:
    status: str
    selected_family: str | None
    reason_codes: tuple[str, ...]
    family_diagnostics: Mapping[str, Any]
    evaluation_envelope_path: str
    evaluation_envelope_sha256: str
    selected_model_path: str | None = None
    version: str = SELECTION_RESULT_VERSION_V2

    def __post_init__(self) -> None:
        if self.status not in {"koopman_selection", "no_selection"}:
            _fail("selection_status_invalid")
        if self.status == "koopman_selection":
            if self.selected_family not in ELIGIBLE_FAMILIES_V2:
                _fail("selected_family_invalid")
        elif self.selected_family is not None or self.selected_model_path is not None:
            _fail("no_selection_model_path_forbidden")
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(
            self, "family_diagnostics", MappingProxyType(dict(self.family_diagnostics))
        )


def select_phase8_candidate(
    evaluation_envelope: str | Path,
    analysis_policy: str | Path,
) -> Phase8SelectionResultV2:
    """Recompute the frozen selector from exact leaf evidence only."""

    envelope_path = Path(evaluation_envelope).resolve()
    validate_phase8_evidence(
        envelope_path, required_qualification="offline_koopman_ood_evaluation"
    )
    policy = load_analysis_policy_v1(analysis_policy)
    payload = load_bounded_json(_evaluation_summary_path(envelope_path))
    if payload.get("evaluation_version") != EVALUATION_RESULT_VERSION_V2:
        _fail("evaluation_version_mismatch")
    if payload.get("analysis_policy_sha256") != policy.policy_sha256:
        _fail("analysis_policy_drift")
    if payload.get("analysis_gate_template") != dict(policy.gate_template):
        _fail("analysis_policy_drift")
    if payload.get("bootstrap_policy") != dict(policy.bootstrap):
        _fail("analysis_policy_drift")
    folds = payload.get("folds")
    if not isinstance(folds, list) or tuple(
        fold.get("holdout_configuration") for fold in folds
    ) != tuple(SUPPORTED_EMBODIMENTS):
        _fail("fold_set_mismatch")

    role_results: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {
        role: {} for role in REQUIRED_ROLES_V2
    }
    for fold in folds:
        configuration = fold.get("holdout_configuration")
        sources = fold.get("source_configurations")
        if (
            not isinstance(sources, list)
            or len(sources) != 7
            or set(sources) != set(SUPPORTED_EMBODIMENTS) - {configuration}
        ):
            _fail("heldout_design_leakage")
        _validate_freeze(fold, policy)
        roles = _mapping(fold.get("roles"), "roles")
        if len(roles) != len(REQUIRED_ROLES_V2) or set(roles) != set(REQUIRED_ROLES_V2):
            _fail("role_matrix_incomplete")
        reference = _mapping(fold.get("reference_diagnostic"), "reference_diagnostic")
        if reference.get("selection_eligible") is not False:
            _fail("reference_diagnostic_not_eligible")
        for role_name in REQUIRED_ROLES_V2:
            results = _validate_role(fold, role_name, _mapping(roles[role_name], role_name))
            overlap = set(role_results[role_name]) & set(results)
            if overlap:
                _fail("duplicate_episode_result")
            role_results[role_name].update(results)

    diagnostics = {
        family: _family_diagnostics(family, role_results, policy)
        for family in ELIGIBLE_FAMILIES_V2
    }
    if diagnostics["conditional_koopman_v2"]["all_hard_gates_pass"]:
        selected = "conditional_koopman_v2"
    elif diagnostics["pooled_koopman_v2"]["all_hard_gates_pass"]:
        selected = "pooled_koopman_v2"
    else:
        selected = None
    reasons = sorted(
        {
            reason
            for family in ELIGIBLE_FAMILIES_V2
            for reason in diagnostics[family]["reason_codes"]
            if reason != "conditional_margin_failed" or selected is None
        }
    )
    if selected is None and not reasons:
        reasons = ["selection_gate_failed"]
    return Phase8SelectionResultV2(
        status="koopman_selection" if selected is not None else "no_selection",
        selected_family=selected,
        reason_codes=tuple(reasons),
        family_diagnostics=diagnostics,
        evaluation_envelope_path=str(envelope_path),
        evaluation_envelope_sha256=file_sha256(envelope_path),
        selected_model_path=None,
    )


@dataclass(frozen=True)
class FinalRefitEpisodeV2:
    episode_id: str
    configuration: str
    role: str
    transition_sha256: str
    payload: Any

    def __post_init__(self) -> None:
        if self.role not in {"fit", "validation"}:
            _fail("final_refit_test_access")
        if not _is_sha256(self.transition_sha256):
            _fail("artifact_hash_invalid", "transition_sha256")


@dataclass(frozen=True)
class FinalRefitResultV2:
    selected_family: str
    selected_candidate: Any
    fitted_model: Any
    opened_episode_ids: tuple[str, ...]
    opened_episode_sha256s: tuple[str, ...]


def refit_without_outer_test(
    episodes: Sequence[FinalRefitEpisodeV2],
    *,
    selected_family: str,
    inner_selector: Callable[[tuple[FinalRefitEpisodeV2, ...]], Any],
    model_fitter: Callable[[str, Any, tuple[FinalRefitEpisodeV2, ...]], Any],
) -> FinalRefitResultV2:
    """Rerun inner selection and fitting on all-eight fit+validation roles only."""

    values = tuple(episodes)
    if selected_family not in ELIGIBLE_FAMILIES_V2:
        _fail("selected_family_invalid")
    if not values or any(not isinstance(item, FinalRefitEpisodeV2) for item in values):
        _fail("final_refit_episode_set_invalid")
    if set(item.configuration for item in values) != set(SUPPORTED_EMBODIMENTS):
        _fail("final_refit_configuration_set_mismatch")
    if len({item.episode_id for item in values}) != len(values):
        _fail("duplicate_episode_id")
    candidate = inner_selector(values)
    model = model_fitter(selected_family, candidate, values)
    return FinalRefitResultV2(
        selected_family=selected_family,
        selected_candidate=candidate,
        fitted_model=model,
        opened_episode_ids=tuple(item.episode_id for item in values),
        opened_episode_sha256s=tuple(item.transition_sha256 for item in values),
    )
