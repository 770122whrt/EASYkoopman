from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.loco_v21 import (
    CandidateEvaluationV21,
    CandidateSpecV21,
    NumericalDiagnosticsV21,
    PRIMARY_METRICS_V21,
    SourceMetricRecordV21,
    build_source_candidate_ledger_v21,
    freeze_primary_v21,
)


HOLDOUT = SUPPORTED_EMBODIMENTS[0]
SOURCES = tuple(SUPPORTED_EMBODIMENTS[1:])
ROLE_PROTOCOL_SHA256 = "a" * 64


def _metric(value: float) -> dict[str, float]:
    return dict.fromkeys(PRIMARY_METRICS_V21, value)


def _primary() -> tuple[object, object]:
    candidate = CandidateSpecV21(
        family="pooled",
        observable_schema="so3_identity_v1",
        data_prefix=2,
        ridge=1e-6,
        normalization="standard_v1",
        conditioning="none",
        label="primary-pooled",
    )
    records = tuple(
        SourceMetricRecordV21(configuration, _metric(0.5), _metric(1.0), _metric(0.8))
        for configuration in SOURCES
    )
    evaluation = CandidateEvaluationV21(
        candidate,
        records,
        NumericalDiagnosticsV21(22, 22, 22, 5.0),
        True,
        None,
        "primary-model",
        "primary-normalizer",
        None,
    )
    ledger = build_source_candidate_ledger_v21(
        (evaluation,),
        source_configurations=SOURCES,
        expected_candidates=(candidate,),
    )
    frozen = freeze_primary_v21(
        ledger,
        model_identities={"pooled": "primary-model"},
        normalizer_identities={"pooled": "primary-normalizer"},
        pca_identities={},
        frozen_at="2026-08-30T00:00:00Z",
    )
    return ledger, frozen


class _SourceTransform:
    def __init__(self) -> None:
        self.calls: list[tuple[float, ...]] = []

    def diagnose_heldout_descriptor(self, descriptor: tuple[float, ...]) -> dict:
        self.calls.append(descriptor)
        return {
            "outside_source_range_indices": [2],
            "inside_convex_hull": False,
            "pca_residual_l2": 0.25,
        }


def _diagnose(session: object, tmp_path: Path | None = None) -> object:
    transform = _SourceTransform()
    diagnostic = session.generate_heldout_descriptor_diagnostic(
        source_transform=transform,
        heldout_descriptor=(1.0, 2.0, 3.0),
        output_path=(None if tmp_path is None else tmp_path / "heldout_descriptor_diagnostic.json"),
    )
    assert transform.calls == [(1.0, 2.0, 3.0)]
    return diagnostic


def _test_bindings() -> tuple[object, ...]:
    from koopman.evaluation_v21 import ProtocolEpisodeBindingV21

    return tuple(
        ProtocolEpisodeBindingV21(
            episode_id=f"{HOLDOUT}-test-family-{index}",
            configuration=HOLDOUT,
            role="test",
            family_repetition=f"family-{index}",
            transition_sha256=f"{index + 1:064x}",
            transition_path=f"episodes/{HOLDOUT}-test-{index}.jsonl",
            manifest_path=f"manifests/{HOLDOUT}-test-{index}.manifest.json",
            transition_count=512,
            role_protocol_sha256=ROLE_PROTOCOL_SHA256,
        )
        for index in range(3)
    )


def _session() -> object:
    from koopman.evaluation_v21 import FoldEvaluationSessionV21

    ledger, frozen = _primary()
    return FoldEvaluationSessionV21(
        HOLDOUT,
        ledger,
        frozen,
        test_episode_bindings=_test_bindings(),
        role_protocol_sha256=ROLE_PROTOCOL_SHA256,
    )


def _expert_candidates() -> tuple[object, ...]:
    from koopman.evaluation_v21 import ExpertCandidateSpecV21

    return (
        ExpertCandidateSpecV21("expert-a", "so3_identity_v1", 1e-6, "none"),
        ExpertCandidateSpecV21("expert-b", "so3_kinematic_v1", 1e-4, "standard_v1"),
    )


def _expert_episodes() -> tuple[tuple[object, ...], tuple[object, ...]]:
    from koopman.evaluation_v21 import ExpertEpisodeV21

    fit = tuple(
        ExpertEpisodeV21(f"{HOLDOUT}-fit-{index}", HOLDOUT, "fit", f"fit-{index}")
        for index in range(2)
    )
    validation = tuple(
        ExpertEpisodeV21(
            f"{HOLDOUT}-validation-{index}",
            HOLDOUT,
            "validation",
            f"validation-{index}",
        )
        for index in range(2)
    )
    return fit, validation


def _expert_persistence(path: Path) -> dict[str, object]:
    def serializer(fitted: object) -> bytes:
        return json.dumps(fitted, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    def loader(payload: bytes) -> object:
        return json.loads(payload.decode("utf-8"))

    def identities(loaded: object) -> tuple[str, str]:
        assert isinstance(loaded, dict)
        return str(loaded["model_identity"]), str(loaded["normalizer_identity"])

    return {
        "artifact_path": path,
        "serializer": serializer,
        "loader": loader,
        "identity_reader": identities,
    }


def test_primary_freeze_alone_cannot_authorize_test() -> None:
    session = _session()

    assert session.state == "PRIMARY_FROZEN"
    with pytest.raises(ValueError, match="test_authorization_order_invalid"):
        session.authorize_primary_test()
    with pytest.raises(ValueError, match="test_open_order_invalid"):
        session.open_primary_test(object(), opener=lambda value: value)


def test_diagnostic_is_post_freeze_selection_ineligible_and_cannot_write_back(
    tmp_path: Path,
) -> None:
    ledger, frozen = _primary()
    ledger_hash = ledger.ledger_sha256
    freeze_hash = frozen.freeze_sha256
    session = _session()
    diagnostic = _diagnose(session, tmp_path)

    assert session.state == "HELDOUT_DIAGNOSTIC_GENERATED"
    assert diagnostic.selection_eligible is False
    assert diagnostic.source_ledger_sha256 == ledger_hash
    assert diagnostic.primary_freeze_sha256 == freeze_hash
    assert (tmp_path / "heldout_descriptor_diagnostic.json").is_file()
    assert ledger.ledger_sha256 == ledger_hash
    assert frozen.freeze_sha256 == freeze_hash
    with pytest.raises(TypeError):
        diagnostic.report["inside_convex_hull"] = True
    with pytest.raises(ValueError, match="diagnostic_order_invalid"):
        _diagnose(session)


def test_expert_uses_heldout_fit_and_validation_for_independent_selection(
    tmp_path: Path,
) -> None:
    _, frozen = _primary()
    session = _session()
    _diagnose(session)
    fit, validation = _expert_episodes()
    fit_calls: list[tuple[str, tuple[str, ...]]] = []
    validation_calls: list[tuple[str, tuple[str, ...]]] = []

    def fitter(candidate, payloads):
        fit_calls.append((candidate.label, tuple(payloads)))
        return {
            "candidate": candidate.label,
            "model_identity": f"model-{candidate.label}",
            "normalizer_identity": f"normalizer-{candidate.label}",
        }

    def evaluator(model, payloads):
        validation_calls.append((model["candidate"], tuple(payloads)))
        score = 0.2 if model["candidate"] == "expert-b" else 0.4
        return _metric(score), _metric(2.0), _metric(1.0)

    expert = session.select_and_freeze_expert(
        candidates=_expert_candidates(),
        fit_episodes=fit,
        validation_episodes=validation,
        fitter=fitter,
        evaluator=evaluator,
        **_expert_persistence(tmp_path / "expert" / "selected_model.json"),
    )

    assert session.state == "EXPERT_FROZEN"
    assert expert.selection_eligible is False
    assert expert.nonpromoting is True
    assert expert.status == "success"
    assert expert.selected_candidate_id == _expert_candidates()[1].candidate_id
    assert expert.model_artifact_name == "selected_model.json"
    assert expert.model_artifact_sha256 == hashlib.sha256(
        (tmp_path / "expert" / "selected_model.json").read_bytes()
    ).hexdigest()
    assert all(payloads == ("fit-0", "fit-1") for _, payloads in fit_calls)
    assert all(
        payloads == ("validation-0", "validation-1")
        for _, payloads in validation_calls
    )
    assert tuple(item.candidate.label for item in expert.ledger) == (
        "expert-a",
        "expert-b",
    )
    assert frozen.freeze_sha256 == session.primary_freeze.freeze_sha256


def test_expert_data_prefix_controls_fit_and_robust_relative_selection(
    tmp_path: Path,
) -> None:
    from koopman.evaluation_v21 import ExpertCandidateSpecV21, ExpertEpisodeV21

    assert "data_prefix" in inspect.signature(ExpertCandidateSpecV21).parameters
    candidates = (
        ExpertCandidateSpecV21(
            label="prefix-2",
            observable_schema="so3_identity_v1",
            data_prefix=2,
            ridge=1e-6,
            normalization="none",
        ),
        ExpertCandidateSpecV21(
            label="prefix-4",
            observable_schema="so3_identity_v1",
            data_prefix=4,
            ridge=1e-6,
            normalization="none",
        ),
    )
    fit = tuple(
        ExpertEpisodeV21(f"{HOLDOUT}-fit-{index}", HOLDOUT, "fit", f"fit-{index}")
        for index in range(6)
    )
    _, validation = _expert_episodes()
    fitted_prefixes: list[tuple[str, tuple[str, ...]]] = []

    def fitter(candidate, payloads):
        fitted_prefixes.append((candidate.label, tuple(payloads)))
        return {
            "candidate": candidate.label,
            "model_identity": f"model-{candidate.label}",
            "normalizer_identity": f"normalizer-{candidate.label}",
        }

    def evaluator(model, payloads):
        del payloads
        candidate_error = 0.75 if model["candidate"] == "prefix-4" else 1.25
        return _metric(candidate_error), _metric(2.0), _metric(1.0)

    session = _session()
    _diagnose(session)
    expert = session.select_and_freeze_expert(
        candidates=candidates,
        fit_episodes=fit,
        validation_episodes=validation,
        fitter=fitter,
        evaluator=evaluator,
        **_expert_persistence(tmp_path / "expert" / "selected_model.json"),
    )

    assert fitted_prefixes == [
        ("prefix-2", ("fit-0", "fit-1")),
        ("prefix-4", ("fit-0", "fit-1", "fit-2", "fit-3")),
    ]
    assert expert.selected_candidate_id == candidates[1].candidate_id
    assert expert.ledger[1].validation_score == pytest.approx(0.75)
    assert all(
        value == pytest.approx(0.75)
        for value in expert.ledger[1].ratios.values()
    )


def test_expert_relative_selection_is_invariant_to_metric_unit_scaling(
    tmp_path: Path,
) -> None:
    from koopman.evaluation_v21 import ExpertCandidateSpecV21

    candidates = (
        ExpertCandidateSpecV21(
            label="uniform-ratio",
            observable_schema="so3_identity_v1",
            data_prefix=2,
            ridge=1e-6,
            normalization="none",
        ),
        ExpertCandidateSpecV21(
            label="raw-max-decoy",
            observable_schema="so3_kinematic_v1",
            data_prefix=2,
            ridge=1e-6,
            normalization="none",
        ),
    )
    fit, validation = _expert_episodes()

    def run(scale: float, name: str) -> str:
        session = _session()
        _diagnose(session)

        def fitter(candidate, payloads):
            del payloads
            return {
                "candidate": candidate.label,
                "model_identity": f"model-{candidate.label}",
                "normalizer_identity": f"normalizer-{candidate.label}",
            }

        def evaluator(model, payloads):
            del payloads
            reference = _metric(1.0)
            reference["linear_velocity_rmse"] = 100.0 * scale
            persistence = _metric(2.0)
            persistence["linear_velocity_rmse"] = 200.0 * scale
            candidate_metrics = _metric(
                0.5 if model["candidate"] == "uniform-ratio" else 0.6
            )
            candidate_metrics["linear_velocity_rmse"] = (
                (50.0 if model["candidate"] == "uniform-ratio" else 40.0)
                * scale
            )
            return candidate_metrics, persistence, reference

        expert = session.select_and_freeze_expert(
            candidates=candidates,
            fit_episodes=fit,
            validation_episodes=validation,
            fitter=fitter,
            evaluator=evaluator,
            **_expert_persistence(tmp_path / name / "selected_model.json"),
        )
        assert expert.selected_candidate_id is not None
        return expert.selected_candidate_id

    assert run(1.0, "original-units") == candidates[0].candidate_id
    assert run(1.0e-3, "scaled-units") == candidates[0].candidate_id


def test_expert_is_nonconditional_and_failure_does_not_block_primary_test(
    tmp_path: Path,
) -> None:
    from koopman.evaluation_v21 import (
        ExpertCandidateSpecV21,
    )

    with pytest.raises(ValueError, match="expert_conditioning_forbidden"):
        ExpertCandidateSpecV21(
            "bad", "so3_identity_v1", 1e-6, "standard_v1", conditioning="conditional"
        )
    _, frozen = _primary()
    session = _session()
    _diagnose(session)
    fit, validation = _expert_episodes()

    def failed_fitter(candidate, payloads):
        raise RuntimeError("synthetic fit failure")

    expert = session.select_and_freeze_expert(
        candidates=_expert_candidates(),
        fit_episodes=fit,
        validation_episodes=validation,
        fitter=failed_fitter,
        evaluator=lambda model, payloads: (0.0, _metric(0.0)),
        **_expert_persistence(tmp_path / "expert" / "selected_model.json"),
    )
    assert expert.status == "failed"
    assert expert.reason_code == "expert_candidate_set_failed"
    assert expert.model_artifact_sha256 is None
    assert not (tmp_path / "expert" / "selected_model.json").exists()

    token = session.authorize_primary_test()
    assert session.state == "TEST_AUTHORIZED"
    assert token.primary_freeze_sha256 == frozen.freeze_sha256
    assert token.test_episode_ids == tuple(item.episode_id for item in _test_bindings())
    assert token.test_transition_sha256s == tuple(
        item.transition_sha256 for item in _test_bindings()
    )
    assert token.role_protocol_sha256 == ROLE_PROTOCOL_SHA256
    opened = session.open_primary_test(
        token, opener=lambda binding: f"opened:{binding.episode_id}"
    )
    assert opened == tuple(
        f"opened:{binding.episode_id}" for binding in _test_bindings()
    )
    assert session.state == "TEST_OPENED"
    with pytest.raises(ValueError, match="test_open_order_invalid"):
        session.open_primary_test(token, opener=lambda value: value)


def test_expert_artifact_is_frozen_roundtripped_and_never_changes_primary_identity(
    tmp_path: Path,
) -> None:
    from koopman.evaluation_v21 import validate_expert_artifact_v21

    _, frozen = _primary()
    session = _session()
    _diagnose(session)
    fit, validation = _expert_episodes()
    expert = session.select_and_freeze_expert(
        candidates=_expert_candidates(),
        fit_episodes=fit,
        validation_episodes=validation,
        fitter=lambda candidate, payloads: {
            "candidate": candidate.label,
            "model_identity": candidate.label,
            "normalizer_identity": candidate.label,
        },
        evaluator=lambda model, payloads: (
            _metric(0.1),
            _metric(2.0),
            _metric(1.0),
        ),
        **_expert_persistence(tmp_path / "expert" / "selected_model.json"),
    )
    with pytest.raises(FrozenInstanceError):
        expert.status = "promoted"
    with pytest.raises(TypeError):
        expert.validation_metrics["depth_rmse"] = 99.0
    artifact_path = tmp_path / "expert" / "selected_model.json"
    validate_expert_artifact_v21(
        expert,
        artifact_path=artifact_path,
        loader=_expert_persistence(artifact_path)["loader"],
        identity_reader=_expert_persistence(artifact_path)["identity_reader"],
    )
    artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="expert_artifact_hash_mismatch"):
        validate_expert_artifact_v21(
            expert,
            artifact_path=artifact_path,
            loader=_expert_persistence(artifact_path)["loader"],
            identity_reader=_expert_persistence(artifact_path)["identity_reader"],
        )
    assert session.primary_freeze.freeze_sha256 == frozen.freeze_sha256


def test_test_episode_bindings_are_exact_three_and_token_cannot_substitute_hash(
    tmp_path: Path,
) -> None:
    from koopman.evaluation_v21 import FoldEvaluationSessionV21, ProtocolEpisodeBindingV21

    ledger, frozen = _primary()
    with pytest.raises(ValueError, match="registered_test_episode_set_invalid"):
        FoldEvaluationSessionV21(
            HOLDOUT,
            ledger,
            frozen,
            test_episode_bindings=_test_bindings()[:2],
            role_protocol_sha256=ROLE_PROTOCOL_SHA256,
        )
    wrong_role = list(_test_bindings())
    original = wrong_role[0]
    wrong_role[0] = ProtocolEpisodeBindingV21(
        episode_id=original.episode_id,
        configuration=original.configuration,
        role="validation",
        family_repetition=original.family_repetition,
        transition_sha256=original.transition_sha256,
        transition_path=original.transition_path,
        manifest_path=original.manifest_path,
        transition_count=512,
        role_protocol_sha256=ROLE_PROTOCOL_SHA256,
    )
    with pytest.raises(ValueError, match="registered_test_episode_set_invalid"):
        FoldEvaluationSessionV21(
            HOLDOUT,
            ledger,
            frozen,
            test_episode_bindings=wrong_role,
            role_protocol_sha256=ROLE_PROTOCOL_SHA256,
        )

    session = _session()
    _diagnose(session)
    fit, validation = _expert_episodes()
    session.select_and_freeze_expert(
        candidates=_expert_candidates(),
        fit_episodes=fit,
        validation_episodes=validation,
        fitter=lambda candidate, payloads: {
            "candidate": candidate.label,
            "model_identity": candidate.label,
            "normalizer_identity": candidate.label,
        },
        evaluator=lambda model, payloads: (0.1, _metric(0.1)),
        **_expert_persistence(tmp_path / "expert" / "selected_model.json"),
    )
    token = session.authorize_primary_test()
    object.__setattr__(token, "test_transition_sha256s", ("f" * 64,) * 3)
    with pytest.raises(ValueError, match="test_access_token_invalid"):
        session.open_primary_test(token, opener=lambda binding: binding)


def test_source_and_heldout_roles_use_the_same_rollout_callable() -> None:
    from koopman.evaluation_v21 import SharedRolloutEvaluatorV21

    calls: list[tuple[str, str]] = []

    def rollout(model, episode, **kwargs):
        calls.append((model, episode))
        return f"trace:{model}:{episode}"

    evaluator = SharedRolloutEvaluatorV21(rollout=rollout)
    source = evaluator.evaluate("source-model", ("source-0", "source-1"))
    heldout = evaluator.evaluate("heldout-model", ("heldout-0",))

    assert source == (
        "trace:source-model:source-0",
        "trace:source-model:source-1",
    )
    assert heldout == ("trace:heldout-model:heldout-0",)
    assert calls == [
        ("source-model", "source-0"),
        ("source-model", "source-1"),
        ("heldout-model", "heldout-0"),
    ]
    assert "rollout" in inspect.signature(SharedRolloutEvaluatorV21).parameters
