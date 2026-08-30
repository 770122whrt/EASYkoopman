from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import inspect
from pathlib import Path

import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS


METRICS = (
    "depth_rmse",
    "linear_velocity_rmse",
    "angular_velocity_rmse",
    "so3_geodesic_mean_radians",
    "so3_geodesic_rmse_radians",
    "so3_geodesic_max_radians",
)
SOURCES = tuple(SUPPORTED_EMBODIMENTS[1:])


def _errors(value: float | None) -> dict[str, float | None]:
    return {metric: value for metric in METRICS}


def _spec(
    name: str,
    *,
    family: str = "pooled",
    observable: str = "so3_identity_v1",
) -> object:
    from koopman.loco_v21 import CandidateSpecV21
    from koopman.model_v21 import CONDITIONING_STRUCTURED_PCA2_V21

    return CandidateSpecV21(
        family=family,
        observable_schema=observable,
        data_prefix=2,
        ridge=1e-6,
        normalization="standard_v1",
        conditioning="none" if family == "pooled" else CONDITIONING_STRUCTURED_PCA2_V21,
        label=name,
    )


def _records(candidate_value: float | None, *, reference: float = 0.8) -> tuple[object, ...]:
    from koopman.loco_v21 import SourceMetricRecordV21

    return tuple(
        SourceMetricRecordV21(
            configuration=configuration,
            candidate_errors=_errors(candidate_value),
            persistence_errors=_errors(1.0),
            simple_linear_errors=_errors(reference),
        )
        for configuration in SOURCES
    )


def _evaluation(
    candidate: object,
    *,
    candidate_value: float | None = 0.4,
    rank: int = 22,
    width: int = 22,
    condition: float = 10.0,
    converged: bool = True,
    rejection_reason: str | None = None,
) -> object:
    from koopman.loco_v21 import CandidateEvaluationV21, NumericalDiagnosticsV21

    return CandidateEvaluationV21(
        candidate=candidate,
        source_records=_records(candidate_value),
        numerics=NumericalDiagnosticsV21(
            design_rank=rank,
            effective_rank=rank,
            design_width=width,
            regularized_condition=condition,
        ),
        converged=converged,
        rejection_reason=rejection_reason,
        model_identity=None if not converged else f"model-{candidate.label}",
        normalizer_identity=f"normalizer-{candidate.label}",
        pca_identity=(
            f"pca-{candidate.label}" if candidate.family == "conditional" else None
        ),
    )


def _ledger(*evaluations: object) -> object:
    from koopman.loco_v21 import build_source_candidate_ledger_v21

    return build_source_candidate_ledger_v21(
        evaluations,
        source_configurations=SOURCES,
        expected_candidates=tuple(value.candidate for value in evaluations),
    )


def test_complete_ledger_keeps_all_candidates_and_six_metric_ratios() -> None:
    pooled = _spec("pooled-identity")
    rejected = _spec("conditional-rank", family="conditional")

    ledger = _ledger(
        _evaluation(pooled),
        _evaluation(rejected, rank=65, width=66),
    )

    assert ledger.sealed is True
    assert ledger.source_configuration_mode == "report_all_no_ranking"
    assert tuple(ledger.source_configurations) == SOURCES
    assert len(ledger.candidates) == 2
    assert len(ledger.candidates[0].source_configuration_metrics) == 7
    assert set(ledger.candidates[0].ratios) == set(METRICS)
    assert set(ledger.candidates[0].candidate_equal_configuration_macro) == set(METRICS)
    assert all(value == pytest.approx(0.5) for value in ledger.candidates[0].ratios.values())
    assert ledger.candidates[0].source_score == pytest.approx(0.5)
    assert ledger.candidates[0].estimator_equivalence_class == (
        "so3_linear_increment_ridge_v1"
    )
    assert ledger.candidates[1].selection_eligible is False
    assert ledger.candidates[1].rejection_reason == "design_rank_insufficient"
    assert ledger.candidates[1].estimator_equivalence_class is None
    assert ledger.ranking == (pooled.candidate_id,)
    assert ledger.selected_candidates == {"pooled": pooled.candidate_id}


def test_zero_denominator_is_deterministic_without_epsilon() -> None:
    from koopman.loco_v21 import SourceMetricRecordV21

    parity = _spec("zero-parity")
    positive = _spec("zero-positive", observable="so3_kinematic_v1")
    zero_baselines = tuple(
        SourceMetricRecordV21(
            configuration=configuration,
            candidate_errors=_errors(0.0),
            persistence_errors=_errors(0.0),
            simple_linear_errors=_errors(0.0),
        )
        for configuration in SOURCES
    )
    positive_records = tuple(
        SourceMetricRecordV21(
            configuration=configuration,
            candidate_errors=_errors(0.1),
            persistence_errors=_errors(0.0),
            simple_linear_errors=_errors(0.0),
        )
        for configuration in SOURCES
    )
    from koopman.loco_v21 import CandidateEvaluationV21, NumericalDiagnosticsV21

    numerics = NumericalDiagnosticsV21(22, 22, 22, 1.0)
    ledger = _ledger(
        CandidateEvaluationV21(
            parity, zero_baselines, numerics, True, None, "model-zero", "norm-zero", None
        ),
        CandidateEvaluationV21(
            positive,
            positive_records,
            numerics,
            True,
            None,
            "model-positive",
            "norm-positive",
            None,
        ),
    )

    assert ledger.candidates[0].source_score == pytest.approx(1.0)
    assert set(ledger.candidates[0].ratios.values()) == {1.0}
    assert ledger.candidates[1].source_score is None
    assert ledger.candidates[1].rejection_reason.startswith(
        "source_score_reference_zero_candidate_positive:"
    )


def test_condition_and_nonconvergence_are_reason_coded_not_dropped() -> None:
    condition = _spec("bad-condition")
    solver = _spec("solver-failed", observable="so3_kinematic_v1")
    ledger = _ledger(
        _evaluation(condition, condition=1.0e8 + 1.0),
        _evaluation(
            solver,
            candidate_value=None,
            converged=False,
            rejection_reason="ridge_solve_failed",
        ),
    )

    by_id = {entry.candidate.candidate_id: entry for entry in ledger.candidates}
    assert by_id[condition.candidate_id].rejection_reason == (
        "regularized_condition_exceeds_limit"
    )
    assert by_id[solver.candidate_id].rejection_reason == "ridge_solve_failed"
    assert ledger.ranking == ()


def test_missing_simple_linear_baseline_is_selection_ineligible() -> None:
    from koopman.loco_v21 import (
        CandidateEvaluationV21,
        NumericalDiagnosticsV21,
        SourceMetricRecordV21,
    )

    candidate = _spec("simple-linear-failed")
    records = tuple(
        SourceMetricRecordV21(
            configuration=configuration,
            candidate_errors=_errors(0.4),
            persistence_errors=_errors(1.0),
            simple_linear_errors=_errors(None),
        )
        for configuration in SOURCES
    )
    evaluation = CandidateEvaluationV21(
        candidate,
        records,
        NumericalDiagnosticsV21(22, 22.0, 22, 2.0),
        True,
        None,
        "model-simple-linear-failed",
        "normalizer-simple-linear-failed",
        None,
    )

    ledger = _ledger(evaluation)
    entry = ledger.candidates[0]
    assert entry.selection_eligible is False
    assert entry.rejection_reason == "simple_linear_baseline_failed"
    assert entry.source_score is None
    assert ledger.ranking == ()


def test_family_order_from_policy_precedes_candidate_id_fallback() -> None:
    from koopman.loco_v21 import build_source_candidate_ledger_v21

    pooled = _spec("z-pooled", family="pooled")
    conditional = _spec("a-conditional", family="conditional")
    evaluations = (
        _evaluation(pooled),
        _evaluation(conditional, rank=66, width=66),
    )

    conditional_first = build_source_candidate_ledger_v21(
        evaluations,
        source_configurations=SOURCES,
        expected_candidates=(pooled, conditional),
        family_order=("conditional", "pooled"),
    )
    pooled_first = build_source_candidate_ledger_v21(
        evaluations,
        source_configurations=SOURCES,
        expected_candidates=(pooled, conditional),
        family_order=("pooled", "conditional"),
    )

    assert conditional_first.ranking[:2] == (
        conditional.candidate_id,
        pooled.candidate_id,
    )
    assert pooled_first.ranking[:2] == (
        pooled.candidate_id,
        conditional.candidate_id,
    )


def test_effective_rank_records_entropy_rank_as_float() -> None:
    from koopman.loco_v21 import NumericalDiagnosticsV21

    diagnostics = NumericalDiagnosticsV21(
        design_rank=22,
        effective_rank=17.25,
        design_width=22,
        regularized_condition=3.0,
    )
    assert diagnostics.effective_rank == pytest.approx(17.25)


def test_missing_candidate_result_fails_closed() -> None:
    from koopman.loco_v21 import build_source_candidate_ledger_v21

    present = _spec("present")
    missing = _spec("missing", observable="so3_kinematic_v1")
    with pytest.raises(ValueError, match="candidate_result_set_mismatch"):
        build_source_candidate_ledger_v21(
            (_evaluation(present),),
            source_configurations=SOURCES,
            expected_candidates=(present, missing),
        )


def test_heldout_statistics_cannot_enter_selector_signature() -> None:
    from koopman.loco_v21 import build_source_candidate_ledger_v21

    parameters = inspect.signature(build_source_candidate_ledger_v21).parameters
    assert all("heldout" not in name and "diagnostic" not in name for name in parameters)
    candidate = _spec("pooled")
    with pytest.raises(TypeError):
        build_source_candidate_ledger_v21(
            (_evaluation(candidate),),
            source_configurations=SOURCES,
            expected_candidates=(candidate,),
            heldout_descriptor={"forbidden": True},
        )


def test_sealed_ledger_and_primary_freeze_are_immutable_and_not_authorized(
    tmp_path: Path,
) -> None:
    from koopman.loco_v21 import (
        freeze_primary_v21,
        write_source_candidate_ledger_v21,
    )

    pooled = _spec("pooled")
    conditional = _spec("conditional", family="conditional")
    ledger = _ledger(_evaluation(pooled), _evaluation(conditional, rank=66, width=66))
    path = write_source_candidate_ledger_v21(ledger, tmp_path / "source_candidate_ledger.json")
    frozen = freeze_primary_v21(
        ledger,
        frozen_at="2026-08-30T00:00:00Z",
    )

    assert path.name == "source_candidate_ledger.json"
    assert frozen.state == "PRIMARY_FROZEN"
    assert frozen.authorization_eligible is False
    assert frozen.test_open_count_at_freeze == 0
    assert frozen.model_identities == {
        "pooled": "model-pooled",
        "conditional": "model-conditional",
    }
    assert frozen.normalizer_identities == {
        "pooled": "normalizer-pooled",
        "conditional": "normalizer-conditional",
    }
    assert frozen.pca_identities == {"conditional": "pca-conditional"}
    with pytest.raises(FrozenInstanceError):
        frozen.state = "TEST_AUTHORIZED"
    with pytest.raises(TypeError):
        ledger.selected_candidates["pooled"] = "mutated"
    with pytest.raises(TypeError):
        frozen.model_identities["pooled"] = "mutated"


@pytest.mark.parametrize(
    ("binding_name", "mutation"),
    (
        ("model_identities", {"pooled": "model-not-selected"}),
        ("normalizer_identities", {"pooled": "normalizer-not-selected"}),
        ("pca_identities", {"conditional": "pca-not-selected"}),
    ),
)
def test_primary_freeze_rejects_caller_identity_mismatch(
    binding_name: str, mutation: dict[str, str]
) -> None:
    from koopman.loco_v21 import freeze_primary_v21

    pooled = _spec("pooled")
    conditional = _spec("conditional", family="conditional")
    ledger = _ledger(_evaluation(pooled), _evaluation(conditional, rank=66, width=66))
    expected = {
        "model_identities": {
            "pooled": "model-pooled",
            "conditional": "model-conditional",
        },
        "normalizer_identities": {
            "pooled": "normalizer-pooled",
            "conditional": "normalizer-conditional",
        },
        "pca_identities": {"conditional": "pca-conditional"},
    }
    expected[binding_name] = mutation

    with pytest.raises(ValueError, match=f"primary_freeze_binding_mismatch:{binding_name}"):
        freeze_primary_v21(
            ledger,
            **expected,
            frozen_at="2026-08-30T00:00:00Z",
        )


def test_primary_freeze_cannot_bind_nonselected_same_family_artifact() -> None:
    from koopman.loco_v21 import freeze_primary_v21

    selected = _spec("selected")
    loser = _spec("loser", observable="so3_kinematic_v1")
    ledger = _ledger(
        _evaluation(selected, candidate_value=0.2),
        _evaluation(loser, candidate_value=0.6, rank=56, width=56),
    )
    assert ledger.selected_candidates == {"pooled": selected.candidate_id}

    with pytest.raises(ValueError, match="primary_freeze_binding_mismatch:model_identities"):
        freeze_primary_v21(
            ledger,
            model_identities={"pooled": "model-loser"},
            normalizer_identities={"pooled": "normalizer-loser"},
            pca_identities={},
            frozen_at="2026-08-30T00:00:00Z",
        )


def test_primary_freeze_rejects_ledger_whose_selected_map_skips_family_winner() -> None:
    from koopman.loco_v21 import freeze_primary_v21

    winner = _spec("winner")
    runner_up = _spec("runner-up", observable="so3_kinematic_v1")
    ledger = _ledger(
        _evaluation(winner, candidate_value=0.2),
        _evaluation(runner_up, candidate_value=0.6, rank=56, width=56),
    )
    inconsistent = replace(
        ledger, selected_candidates={"pooled": runner_up.candidate_id}
    )

    with pytest.raises(ValueError, match="primary_freeze_selected_candidate_invalid"):
        freeze_primary_v21(
            inconsistent,
            frozen_at="2026-08-30T00:00:00Z",
        )


def test_conditional_identifier_is_unique_across_candidate_and_model() -> None:
    from koopman.model_v21 import CONDITIONING_STRUCTURED_PCA2_V21

    candidate = _spec("conditional", family="conditional")
    assert CONDITIONING_STRUCTURED_PCA2_V21 == "structured_pca2"
    assert candidate.conditioning == CONDITIONING_STRUCTURED_PCA2_V21
    with pytest.raises(ValueError, match="candidate_conditioning_invalid"):
        type(candidate)(
            family="conditional",
            observable_schema="so3_identity_v1",
            data_prefix=2,
            ridge=1e-6,
            normalization="standard_v1",
            conditioning="structured_pca_r2_v1",
            label="legacy-drift",
        )
