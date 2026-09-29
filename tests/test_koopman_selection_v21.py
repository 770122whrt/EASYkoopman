from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.loco_v21 import CandidateSpecV21, PRIMARY_METRICS_V21


HORIZONS = ("5", "20", "60", "full")
ROLE_PROTOCOL_SHA256 = "a" * 64


def _test_bindings(configuration: str) -> tuple[object, ...]:
    from koopman.evaluation_v21 import ProtocolEpisodeBindingV21

    return tuple(
        ProtocolEpisodeBindingV21(
            episode_id=f"{configuration}-test-family-{index}",
            configuration=configuration,
            role="test",
            family_repetition=f"family-{index}",
            transition_sha256=(
                f"{SUPPORTED_EMBODIMENTS.index(configuration) * 3 + index + 1:064x}"
            ),
            transition_path=f"episodes/{configuration}-test-{index}.jsonl",
            manifest_path=f"manifests/{configuration}-test-{index}.manifest.json",
            transition_count=512,
            role_protocol_sha256=ROLE_PROTOCOL_SHA256,
        )
        for index in range(3)
    )


def _test_token(configuration: str) -> object:
    from koopman.evaluation_v21 import PrimaryTestTokenV21

    bindings = _test_bindings(configuration)
    return PrimaryTestTokenV21(
        heldout_configuration=configuration,
        test_episode_ids=tuple(binding.episode_id for binding in bindings),
        primary_freeze_sha256="b" * 64,
        diagnostic_sha256="c" * 64,
        expert_freeze_sha256="d" * 64,
        test_transition_sha256s=tuple(binding.transition_sha256 for binding in bindings),
        test_family_repetitions=tuple(binding.family_repetition for binding in bindings),
        role_protocol_sha256=ROLE_PROTOCOL_SHA256,
    )


def _horizon(value: float, *, divergence: int = 0) -> object:
    from koopman.selection_v21 import HorizonOuterEvidenceV21

    return HorizonOuterEvidenceV21(
        metrics=dict.fromkeys(PRIMARY_METRICS_V21, value),
        status="success",
        reason_code=None,
        transition_count=512,
        window_count=1,
        nonfinite_count=0,
        invalid_quaternion_count=0,
        quaternion_unit_norm_drift_count=0,
        quaternion_projection_count=0,
        divergence_count=divergence,
    )


def _failed_horizon(reason: str = "rollout_diverged") -> object:
    from koopman.selection_v21 import HorizonOuterEvidenceV21

    return HorizonOuterEvidenceV21(
        metrics=dict.fromkeys(PRIMARY_METRICS_V21, None),
        status="failed",
        reason_code=reason,
        transition_count=512,
        window_count=1,
        nonfinite_count=0,
        invalid_quaternion_count=0,
        quaternion_unit_norm_drift_count=0,
        quaternion_projection_count=0,
        divergence_count=1,
    )


def _episodes(configuration: str, value: float) -> tuple[object, ...]:
    from koopman.selection_v21 import EpisodeOuterEvidenceV21

    return tuple(
        EpisodeOuterEvidenceV21(
            binding=binding,
            horizons={name: _horizon(value) for name in HORIZONS},
        )
        for binding in _test_bindings(configuration)
    )


def _folds(
    *,
    persistence: float = 1.0,
    simple: float = 0.9,
    pooled: float = 0.7,
    conditional: float = 0.69,
) -> tuple[object, ...]:
    from koopman.selection_v21 import (
        BaselineOuterEvidenceV21,
        EligibleFamilyOuterEvidenceV21,
        FoldOuterEvidenceV21,
    )

    return tuple(
        FoldOuterEvidenceV21(
            heldout_configuration=configuration,
            test_token=_test_token(configuration),
            persistence=BaselineOuterEvidenceV21(
                "persistence", _episodes(configuration, persistence)
            ),
            simple_linear=BaselineOuterEvidenceV21(
                "simple_linear", _episodes(configuration, simple)
            ),
            pooled=EligibleFamilyOuterEvidenceV21(
                "pooled", True, "success", None, _episodes(configuration, pooled)
            ),
            conditional=EligibleFamilyOuterEvidenceV21(
                "conditional",
                True,
                "success",
                None,
                _episodes(configuration, conditional),
            ),
        )
        for configuration in SUPPORTED_EMBODIMENTS
    )


def test_outer_selector_applies_frozen_gates_and_selects_only_family() -> None:
    from koopman.selection_v21 import select_outer_family_v21

    pooled = select_outer_family_v21(_folds())
    conditional = select_outer_family_v21(_folds(conditional=0.6))

    assert pooled.status == "SELECTION"
    assert pooled.selected_family == "pooled"
    assert conditional.status == "SELECTION"
    assert conditional.selected_family == "conditional"
    assert pooled.family_diagnostics["pooled"]["all_hard_gates_pass"] is True
    assert pooled.family_diagnostics["conditional"]["conditional_margin_pass"] is False


def test_outer_selector_returns_reason_coded_no_selection() -> None:
    from koopman.selection_v21 import select_outer_family_v21

    result = select_outer_family_v21(_folds(pooled=1.2, conditional=1.1))

    assert result.status == "NO_SELECTION"
    assert result.selected_family is None
    assert "baseline_improvement_failed" in result.reason_codes


def test_failed_pooled_family_makes_conditional_margin_ineligible_without_crash() -> None:
    from koopman.selection_v21 import EligibleFamilyOuterEvidenceV21, select_outer_family_v21

    folds = list(_folds(conditional=0.6))
    for fold in folds:
        object.__setattr__(
            fold,
            "pooled",
            EligibleFamilyOuterEvidenceV21(
                "pooled", True, "failed", "source_candidate_unavailable", ()
            ),
        )
    result = select_outer_family_v21(tuple(folds))
    assert result.status == "NO_SELECTION"
    assert result.selected_family is None
    assert result.family_diagnostics["pooled"]["reason_codes"] == ("role_failed",)
    assert "conditional_margin_failed" in result.reason_codes


def test_outer_selector_requires_exact_eight_complete_eligible_folds() -> None:
    from koopman.selection_v21 import (
        BaselineOuterEvidenceV21,
        select_outer_family_v21,
    )

    with pytest.raises(ValueError, match="fold_set_mismatch"):
        select_outer_family_v21(_folds()[:-1])
    folds = list(_folds())
    object.__setattr__(
        folds[0],
        "persistence",
        BaselineOuterEvidenceV21("persistence", folds[0].persistence.episodes[:2]),
    )
    with pytest.raises(ValueError, match="outer_episode_protocol_binding_mismatch"):
        select_outer_family_v21(tuple(folds))
    with pytest.raises(TypeError):
        type(folds[1])(
            heldout_configuration=folds[1].heldout_configuration,
            test_token=folds[1].test_token,
            persistence=folds[1].persistence,
            simple_linear=folds[1].simple_linear,
            pooled=folds[1].pooled,
            conditional=folds[1].conditional,
            expert={"selection_eligible": False},
        )


def test_invalid_rollout_is_a_hard_gate_and_selector_has_no_override_inputs() -> None:
    from koopman.selection_v21 import (
        EpisodeOuterEvidenceV21,
        EligibleFamilyOuterEvidenceV21,
        select_outer_family_v21,
    )

    folds = list(_folds(conditional=1.2))
    original = folds[0]
    poisoned_episodes = list(original.pooled.episodes)
    first = poisoned_episodes[0]
    poisoned_horizons = dict(first.horizons)
    poisoned_horizons["20"] = _horizon(0.7, divergence=1)
    poisoned_episodes[0] = EpisodeOuterEvidenceV21(
        first.binding,
        poisoned_horizons,
    )
    object.__setattr__(
        original,
        "pooled",
        EligibleFamilyOuterEvidenceV21(
            "pooled", True, "success", None, tuple(poisoned_episodes)
        ),
    )
    result = select_outer_family_v21(tuple(folds))
    assert result.status == "NO_SELECTION"
    assert "finite_quaternion_divergence_gate_failed" in result.reason_codes

    parameters = inspect.signature(select_outer_family_v21).parameters
    assert tuple(parameters) == ("folds",)
    assert all(
        forbidden not in name
        for name in parameters
        for forbidden in ("expert", "threshold", "override", "test", "vote")
    )


def test_failed_horizon_is_nullable_reason_coded_roundtripped_and_never_aggregated() -> None:
    from koopman.selection_v21 import (
        EpisodeOuterEvidenceV21,
        EligibleFamilyOuterEvidenceV21,
        HorizonOuterEvidenceV21,
        select_outer_family_v21,
    )

    failed = _failed_horizon()
    payload = failed.to_dict()
    assert payload["status"] == "failed"
    assert payload["reason_code"] == "rollout_diverged"
    assert payload["transition_count"] == 512
    assert payload["window_count"] == 1
    assert all(value is None for value in payload["metrics"].values())
    assert HorizonOuterEvidenceV21.from_dict(payload) == failed
    with pytest.raises(ValueError, match="outer_metric_failure_values_invalid"):
        HorizonOuterEvidenceV21(
            **{**payload, "metrics": dict.fromkeys(PRIMARY_METRICS_V21, 0.0)}
        )
    with pytest.raises(ValueError, match="quaternion_projection_forbidden"):
        HorizonOuterEvidenceV21.from_dict(
            {**payload, "quaternion_projection_count": 1}
        )

    folds = list(_folds(conditional=1.2))
    original = folds[0]
    episodes = list(original.pooled.episodes)
    first = episodes[0]
    horizons = dict(first.horizons)
    horizons["full"] = failed
    episodes[0] = EpisodeOuterEvidenceV21(first.binding, horizons)
    object.__setattr__(
        original,
        "pooled",
        EligibleFamilyOuterEvidenceV21(
            "pooled", True, "success", None, tuple(episodes)
        ),
    )
    decision = select_outer_family_v21(tuple(folds))
    assert decision.status == "NO_SELECTION"
    assert "role_failed" in decision.family_diagnostics["pooled"]["reason_codes"]

    baseline_folds = list(_folds())
    baseline_fold = baseline_folds[0]
    baseline_episodes = list(baseline_fold.persistence.episodes)
    baseline_first = baseline_episodes[0]
    baseline_horizons = dict(baseline_first.horizons)
    baseline_horizons["full"] = failed
    baseline_episodes[0] = EpisodeOuterEvidenceV21(
        baseline_first.binding, baseline_horizons
    )
    from koopman.selection_v21 import BaselineOuterEvidenceV21

    object.__setattr__(
        baseline_fold,
        "persistence",
        BaselineOuterEvidenceV21("persistence", tuple(baseline_episodes)),
    )
    baseline_decision = select_outer_family_v21(tuple(baseline_folds))
    assert baseline_decision.status == "NO_SELECTION"
    assert "baseline_role_failed" in baseline_decision.reason_codes


def test_bootstrap_and_threshold_policy_is_frozen_and_deterministic() -> None:
    from koopman.selection_v21 import FROZEN_PROMOTION_POLICY_V21, select_outer_family_v21

    assert FROZEN_PROMOTION_POLICY_V21 == {
        "bootstrap_resamples": 2000,
        "bootstrap_seed": 80304,
        "bootstrap_alpha": 0.05,
        "minimum_improvement_fraction": 0.01,
        "noninferiority_fraction": 0.1,
        "conditional_margin_fraction": 0.05,
    }
    first = select_outer_family_v21(_folds())
    second = select_outer_family_v21(_folds())
    assert first.family_diagnostics == second.family_diagnostics
    with pytest.raises(TypeError):
        first.family_diagnostics["pooled"]["baseline_checks"]["persistence"][
            "depth_rmse"
        ]["candidate_macro"] = 99.0


def _refit_candidate(label: str, *, family: str = "pooled") -> CandidateSpecV21:
    from koopman.model_v21 import CONDITIONING_STRUCTURED_PCA2_V21

    return CandidateSpecV21(
        family=family,
        observable_schema=(
            "so3_identity_v1" if label.endswith("identity") else "so3_kinematic_v1"
        ),
        data_prefix=8,
        ridge=1e-6,
        normalization="standard_v1",
        conditioning="none" if family == "pooled" else CONDITIONING_STRUCTURED_PCA2_V21,
        label=label,
    )


def _refit_bindings() -> tuple[object, ...]:
    from koopman.evaluation_v21 import ProtocolEpisodeBindingV21

    result = []
    sequence = 100
    for configuration in SUPPORTED_EMBODIMENTS:
        for role, count in (("fit", 6), ("validation", 3)):
            for index in range(count):
                sequence += 1
                result.append(
                    ProtocolEpisodeBindingV21(
                        episode_id=f"{configuration}-{role}-{index}",
                        configuration=configuration,
                        role=role,
                        family_repetition=f"family-{index}",
                        transition_sha256=f"{sequence:064x}",
                        transition_path=f"episodes/{configuration}-{role}-{index}.jsonl",
                        manifest_path=(
                            f"manifests/{configuration}-{role}-{index}.manifest.json"
                        ),
                        transition_count=512,
                        role_protocol_sha256=ROLE_PROTOCOL_SHA256,
                    )
                )
    return tuple(result)


def _publisher(tmp_path: Path, *, loader=None, replace=None) -> tuple[object, object, list]:
    from koopman.selection_v21 import FinalRefitDataSourceV21, FinalRefitPublisherV21

    calls: list[tuple] = []

    source = FinalRefitDataSourceV21(
        registered_episodes=_refit_bindings(),
        role_protocol_sha256=ROLE_PROTOCOL_SHA256,
        opener=lambda binding: (
            (_ for _ in ()).throw(AssertionError("test binding opened"))
            if binding.role == "test"
            else f"payload:{binding.episode_id}"
        ),
    )
    identity = _refit_candidate("all8-identity")
    kinematic = _refit_candidate("all8-kinematic")

    def inner_selector(family, fit, validation, candidates):
        calls.append(("select", family, tuple(item.role for item in fit + validation)))
        return candidates[-1]  # may differ from every historical fold winner

    def fitter(candidate, episodes):
        calls.append(("fit", candidate.candidate_id, tuple(item.role for item in episodes)))
        return {
            "candidate_id": candidate.candidate_id,
            "count": len(episodes),
            "normalizer_identity": "all8-normalizer",
            "pca_identity": None,
        }

    publisher = FinalRefitPublisherV21(
        data_source=source,
        candidates_by_family={"pooled": (identity, kinematic)},
        inner_selector=inner_selector,
        final_fitter=fitter,
        serializer=lambda model: repr(sorted(model.items())).encode("utf-8"),
        loader=(
            (
                lambda data: {
                    "candidate_id": kinematic.candidate_id,
                    "count": 16,
                    "normalizer_identity": "all8-normalizer",
                    "pca_identity": None,
                }
            )
            if loader is None
            else loader
        ),
        model_identity=lambda model: (
            model["candidate_id"],
            model.get("normalizer_identity"),
            model.get("pca_identity"),
        ),
        publication_root=tmp_path / "published-model",
        atomic_replace=replace,
    )
    return publisher, source, calls


def test_public_final_refit_api_is_selected_family_only_and_zero_test_read(
    tmp_path: Path,
) -> None:
    from koopman.selection_v21 import FinalRefitPublisherV21

    parameters = inspect.signature(FinalRefitPublisherV21.publish).parameters
    assert tuple(parameters) == ("self", "selected_family")
    publisher, source, calls = _publisher(tmp_path)
    result = publisher.publish("pooled")

    assert result.status == "SELECTION"
    assert result.selected_family == "pooled"
    assert result.selected_candidate_id == _refit_candidate("all8-kinematic").candidate_id
    assert result.selected_model_path is not None
    assert Path(result.selected_model_path).is_file()
    assert source.opened_roles == ("fit", "validation")
    assert len(source.opened_episode_ids) == 72
    assert all("test" not in episode_id for episode_id in source.opened_episode_ids)
    assert result.zero_test_read_audit is True
    assert calls[0][0] == "select"
    assert set(calls[0][2]) == {"fit", "validation"}
    assert calls[1][0] == "fit"
    assert set(calls[1][2]) == {"fit", "validation"}


def test_roundtrip_or_atomic_failure_is_pathless_no_selection_and_leak_free(
    tmp_path: Path,
) -> None:
    failed_roundtrip, _, _ = _publisher(
        tmp_path / "roundtrip",
        loader=lambda data: {
            "candidate_id": "wrong",
            "count": 16,
            "normalizer_identity": "all8-normalizer",
            "pca_identity": None,
        },
    )
    roundtrip = failed_roundtrip.publish("pooled")
    assert roundtrip.status == "NO_SELECTION"
    assert roundtrip.selected_model_path is None
    assert roundtrip.reason_code == "final_refit_roundtrip_failed"
    assert not (tmp_path / "roundtrip" / "published-model").exists()

    def interrupted(source, target):
        raise OSError("synthetic interrupted publication")

    interrupted_publisher, source, _ = _publisher(
        tmp_path / "interrupted", replace=interrupted
    )
    interrupted_result = interrupted_publisher.publish("pooled")
    assert interrupted_result.status == "NO_SELECTION"
    assert interrupted_result.selected_model_path is None
    assert interrupted_result.reason_code == "atomic_publication_failed"
    assert source.opened_roles == ("fit", "validation")
    publication_parent = tmp_path / "interrupted"
    assert not (publication_parent / "published-model").exists()
    assert list(publication_parent.glob(".phase81-refit-*")) == []


def test_final_refit_rejects_test_role_and_family_mismatch_without_publication(
    tmp_path: Path,
) -> None:
    from koopman.selection_v21 import (
        FinalRefitDataSourceV21,
        FinalRefitEpisodeV21,
        FinalRefitPublisherV21,
    )

    with pytest.raises(ValueError, match="final_refit_test_episode_forbidden"):
        FinalRefitEpisodeV21(_test_bindings(SUPPORTED_EMBODIMENTS[0])[0], object())
    publisher, _, _ = _publisher(tmp_path)
    result = publisher.publish("conditional")
    assert result.status == "NO_SELECTION"
    assert result.reason_code == "final_refit_candidate_family_missing"
    assert result.selected_model_path is None


def test_final_refit_data_source_requires_exact_48_fit_24_validation_hash_bindings() -> None:
    from koopman.selection_v21 import FinalRefitDataSourceV21

    bindings = _refit_bindings()
    source = FinalRefitDataSourceV21(
        registered_episodes=bindings,
        role_protocol_sha256=ROLE_PROTOCOL_SHA256,
        opener=lambda binding: binding.episode_id,
    )
    assert len(source.registered_fit_episode_ids) == 48
    assert len(source.registered_validation_episode_ids) == 24
    assert len(source.registered_transition_sha256s) == 72
    with pytest.raises(ValueError, match="final_refit_registered_episode_set_invalid"):
        FinalRefitDataSourceV21(
            registered_episodes=bindings[:-1],
            role_protocol_sha256=ROLE_PROTOCOL_SHA256,
            opener=lambda binding: binding.episode_id,
        )
