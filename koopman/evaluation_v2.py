"""One-shot, freeze-before-test Phase 8 LOCO numerical evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.baselines_v2 import (
    PersistenceBaselineV2,
    SimpleLinearBaselineV2,
    fit_simple_linear_baseline_v2,
)
from koopman.collection_v2 import (
    DatasetInventoryV2,
    EpisodeInventoryEntryV2,
)
from koopman.dataset_v2 import KoopmanDatasetV2, load_koopman_episode_v2
from koopman.evidence_v2 import (
    PHASE8_EVIDENCE_ENVELOPE_V1,
    atomic_write_json,
    canonical_sha256,
    file_sha256,
    load_bounded_json,
    referenced_file_records,
    validate_phase8_evidence,
)
from koopman.loco_v2 import (
    CandidateSpecV2,
    CandidateValidationResultV2,
    FoldExecutionV2,
    FrozenPrimaryStateV2,
    ModelRoleV2,
    authorize_primary_test_access_v2,
    robust_relative_source_score_v2,
    validate_fold_model_binding_v2,
)
from koopman.metrics_v2 import (
    OFFICIAL_ERROR_METRICS_V2,
    REQUIRED_HORIZON_LABELS_V2,
    EpisodeMetricArtifactV2,
    EpisodeTrajectoryV2,
    RolloutAnalysisPolicyV2,
    aggregate_configuration_metrics_v2,
    evaluate_model_episodes_v2,
    rollout_episode_v2,
    so3_geodesic_radians,
)
from koopman.model_v2 import ControlledEDMDV2
from koopman.platform_features_v2 import (
    PlatformFeatureDescriptorV2,
    build_platform_descriptor_v2,
    fit_platform_feature_normalizer_v2,
    select_platform_feature_schema_v2,
)
from koopman.preprocessing_v2 import (
    QuaternionPreprocessedEpisodeV2,
    preprocess_quaternion_episode_v2,
)
from koopman.protocol_v2 import (
    AnalysisPolicyV2,
    SOURCE_SCORE_PRIMARY_METRICS_V2,
    validate_main_role_protocol_v1,
)
from koopman.selection_v2 import EVALUATION_RESULT_VERSION_V2, REQUIRED_ROLES_V2
from koopman.splits_v2 import (
    LOCOSplitManifestV2,
    LOCOFoldManifestV2,
    expert_view_for_fold_v2,
    primary_view_for_fold_v2,
    validate_loco_split_manifest_v2,
)


EVALUATION_EXPERIMENT_ID_V2 = "phase8-08-05-loco-evaluation-v1"
OFFICIAL_ROLLOUT_POLICY_V2 = RolloutAnalysisPolicyV2(
    horizons=(5, 20, 60, "full"),
    quaternion_epsilon=1.0e-10,
    quaternion_projection_limit=0.25,
    depth_abs_max=100.0,
    linear_velocity_abs_max=100.0,
    angular_velocity_abs_max=100.0,
)
_SCENARIO_PREFIX = "phase8-main-"
_KNOWN_FAMILIES = (
    "independent_prbs",
    "bounded_multisine",
    "coupled_chirp",
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def family_repetition_v2(scenario: str) -> str:
    if not isinstance(scenario, str) or not scenario.startswith(_SCENARIO_PREFIX):
        _fail("test_family_unknown", str(scenario))
    family = scenario[len(_SCENARIO_PREFIX) :].replace("-", "_")
    if family not in _KNOWN_FAMILIES:
        _fail("test_family_unknown", scenario)
    return family


@dataclass(frozen=True)
class BoundPlatformModelV2:
    model: Any
    platform_descriptor: Any

    def predict_next(self, state: Any, control: Any) -> Any:
        return self.model.predict_next(
            state, control, platform_descriptor=self.platform_descriptor
        )


@dataclass
class LoadedEpisodeV2:
    entry: EpisodeInventoryEntryV2
    dataset: KoopmanDatasetV2
    preprocessed: QuaternionPreprocessedEpisodeV2 = field(init=False)
    _descriptors: dict[str, PlatformFeatureDescriptorV2] = field(
        init=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        self.preprocessed = preprocess_quaternion_episode_v2(
            self.dataset.X,
            self.dataset.Y,
            episode_id=self.entry.episode_id,
        )

    def descriptor(self, schema_name: str) -> PlatformFeatureDescriptorV2:
        if schema_name not in self._descriptors:
            self._descriptors[schema_name] = build_platform_descriptor_v2(
                self.dataset.platform_contexts,
                schema=select_platform_feature_schema_v2(schema_name),
            )
        return self._descriptors[schema_name]

    def trajectory(self) -> EpisodeTrajectoryV2:
        return EpisodeTrajectoryV2(
            episode_id=self.entry.episode_id,
            configuration=self.entry.configuration,
            states=self.preprocessed.states,
            controls=self.dataset.U,
            targets=self.preprocessed.targets,
        )


def _load_episode(root: Path, entry: EpisodeInventoryEntryV2) -> LoadedEpisodeV2:
    return LoadedEpisodeV2(
        entry=entry,
        dataset=load_koopman_episode_v2(
            root / entry.transition_path,
            root / entry.manifest_path,
        ),
    )


def _fit_episodes(
    episodes: Sequence[LoadedEpisodeV2],
    *,
    configurations: Sequence[str],
    data_prefix: int,
) -> tuple[LoadedEpisodeV2, ...]:
    selected: list[LoadedEpisodeV2] = []
    for configuration in configurations:
        matches = [
            episode
            for episode in episodes
            if episode.entry.configuration == configuration
            and episode.entry.role == "fit"
        ]
        if len(matches) < data_prefix:
            _fail("fit_prefix_unavailable", configuration)
        selected.extend(matches[:data_prefix])
    return tuple(selected)


def _validation_episodes(
    episodes: Sequence[LoadedEpisodeV2], configuration: str | None = None
) -> tuple[LoadedEpisodeV2, ...]:
    return tuple(
        episode
        for episode in episodes
        if episode.entry.role == "validation"
        and (configuration is None or episode.entry.configuration == configuration)
    )


def _arrays(
    episodes: Sequence[LoadedEpisodeV2],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    values = tuple(episodes)
    if not values:
        _fail("fit_episode_set_empty")
    return (
        np.concatenate([episode.preprocessed.states for episode in values]),
        np.concatenate([episode.dataset.U for episode in values]),
        np.concatenate([episode.preprocessed.targets for episode in values]),
    )


def _preprocessing_sha256(episodes: Sequence[LoadedEpisodeV2]) -> str:
    return canonical_sha256(
        {
            "episode_preprocessors": [
                {
                    "episode_id": episode.entry.episode_id,
                    "preprocessor_sha256": episode.preprocessed.preprocessor_sha256,
                }
                for episode in episodes
            ]
        }
    )


def fit_candidate_model_v2(
    candidate: CandidateSpecV2,
    episodes: Sequence[LoadedEpisodeV2],
    *,
    configurations: Sequence[str],
    fold: LOCOFoldManifestV2 | None,
) -> ControlledEDMDV2:
    fit_episodes = _fit_episodes(
        episodes,
        configurations=configurations,
        data_prefix=candidate.data_prefix,
    )
    states, controls, targets = _arrays(fit_episodes)
    conditioning = "none"
    descriptors: list[PlatformFeatureDescriptorV2] | None = None
    normalizer = None
    if candidate.platform_schema != "none":
        if fold is None:
            _fail("conditional_fold_required")
        conditioning = "platform_affine"
        schema = select_platform_feature_schema_v2(candidate.platform_schema)
        by_configuration = {
            configuration: next(
                episode.descriptor(candidate.platform_schema)
                for episode in fit_episodes
                if episode.entry.configuration == configuration
            )
            for configuration in fold.source_configurations
        }
        normalizer = fit_platform_feature_normalizer_v2(
            by_configuration,
            fold=fold,
            schema=schema,
        )
        descriptors = []
        for episode in fit_episodes:
            descriptors.extend(
                [episode.descriptor(candidate.platform_schema)]
                * episode.dataset.sample_count
            )
    return ControlledEDMDV2.fit(
        states,
        controls,
        targets,
        preprocessing_sha256=_preprocessing_sha256(fit_episodes),
        observable_schema=candidate.observable_schema,
        conditioning=conditioning,
        ridge=candidate.ridge,
        normalization=candidate.normalization,
        platform_descriptors=descriptors,
        platform_normalizer=normalizer,
        fold=fold,
    )


def _bound_model(
    model: ControlledEDMDV2,
    episode: LoadedEpisodeV2,
    candidate: CandidateSpecV2,
) -> Any:
    if candidate.platform_schema == "none":
        return model
    return BoundPlatformModelV2(
        model=model,
        platform_descriptor=episode.descriptor(candidate.platform_schema),
    )


def _full_errors(
    model: Any,
    episodes: Sequence[LoadedEpisodeV2],
    *,
    candidate: CandidateSpecV2 | None = None,
) -> dict[str, float] | None:
    totals = {name: [] for name in OFFICIAL_ERROR_METRICS_V2}
    for episode in episodes:
        active_model = model if candidate is None else _bound_model(model, episode, candidate)
        trajectory = episode.trajectory()
        trace = rollout_episode_v2(
            active_model,
            trajectory,
            start=0,
            steps=trajectory.transition_count,
            policy=OFFICIAL_ROLLOUT_POLICY_V2,
        )
        if trace.status != "success":
            return None
        predictions = trace.predictions
        truths = trajectory.targets
        depth = float(np.sqrt(np.mean(np.square(predictions[:, 0] - truths[:, 0]))))
        linear = float(
            np.sqrt(np.mean(np.square(predictions[:, 5:8] - truths[:, 5:8])))
        )
        angular = float(
            np.sqrt(np.mean(np.square(predictions[:, 8:11] - truths[:, 8:11])))
        )
        angles = np.asarray(
            so3_geodesic_radians(
                truths[:, 1:5],
                predictions[:, 1:5],
                quaternion_epsilon=OFFICIAL_ROLLOUT_POLICY_V2.quaternion_epsilon,
                projection_limit=OFFICIAL_ROLLOUT_POLICY_V2.quaternion_projection_limit,
            ),
            dtype=np.float64,
        )
        values = {
            "depth_rmse": depth,
            "linear_velocity_rmse": linear,
            "angular_velocity_rmse": angular,
            "so3_geodesic_mean_radians": float(np.mean(angles)),
            "so3_geodesic_rmse_radians": float(
                np.sqrt(np.mean(np.square(angles)))
            ),
            "so3_geodesic_max_radians": float(np.max(angles)),
        }
        for name, value in values.items():
            totals[name].append(value)
    return {name: float(np.mean(values)) for name, values in totals.items()}


def _simple_hash(model: SimpleLinearBaselineV2) -> str:
    return canonical_sha256(
        {
            "coefficient_matrix": model.coefficient_matrix.tolist(),
            "diagnostics": dict(model.diagnostics),
            "ridge": model.ridge,
            "role": model.role,
            "version": model.version,
        }
    )


class SourceCandidateEvaluatorV2:
    """Evaluate the frozen grid on source fit/validation bytes only."""

    def __init__(
        self,
        episodes: Sequence[LoadedEpisodeV2],
        fold: LOCOFoldManifestV2,
    ) -> None:
        self.episodes = tuple(episodes)
        self.fold = fold
        self._persistence_errors = {
            configuration: _full_errors(
                PersistenceBaselineV2(),
                _validation_episodes(self.episodes, configuration),
            )
            for configuration in fold.source_configurations
        }
        if any(value is None for value in self._persistence_errors.values()):
            _fail("persistence_validation_failed")
        self._simple_errors: dict[
            tuple[int, float], tuple[SimpleLinearBaselineV2, dict[str, dict[str, float]]]
        ] = {}

    def _simple(
        self, candidate: CandidateSpecV2
    ) -> tuple[SimpleLinearBaselineV2, dict[str, dict[str, float]]]:
        key = candidate.data_prefix, candidate.ridge
        if key not in self._simple_errors:
            selected = _fit_episodes(
                self.episodes,
                configurations=self.fold.source_configurations,
                data_prefix=candidate.data_prefix,
            )
            states, controls, targets = _arrays(selected)
            model = fit_simple_linear_baseline_v2(
                states, controls, targets, ridge=candidate.ridge
            )
            errors: dict[str, dict[str, float]] = {}
            for configuration in self.fold.source_configurations:
                result = _full_errors(
                    model, _validation_episodes(self.episodes, configuration)
                )
                errors[configuration] = (
                    dict.fromkeys(OFFICIAL_ERROR_METRICS_V2, sys.float_info.max)
                    if result is None
                    else result
                )
            self._simple_errors[key] = model, errors
        return self._simple_errors[key]

    def __call__(
        self,
        candidate: CandidateSpecV2,
        opened: tuple[LoadedEpisodeV2, ...],
        fold: LOCOFoldManifestV2,
    ) -> CandidateValidationResultV2:
        if tuple(opened) != self.episodes or fold != self.fold:
            _fail("candidate_evaluator_binding_mismatch")
        model: ControlledEDMDV2 | None = None
        source_scores = dict.fromkeys(fold.source_configurations, sys.float_info.max)
        converged = False
        try:
            model = fit_candidate_model_v2(
                candidate,
                self.episodes,
                configurations=fold.source_configurations,
                fold=fold,
            )
            _, simple_errors = self._simple(candidate)
            candidate_errors = {
                configuration: _full_errors(
                    model,
                    _validation_episodes(self.episodes, configuration),
                    candidate=candidate,
                )
                for configuration in fold.source_configurations
            }
            if all(value is not None for value in candidate_errors.values()):
                source_scores = {
                    configuration: robust_relative_source_score_v2(
                        candidate_errors[configuration],  # type: ignore[arg-type]
                        self._persistence_errors[configuration],  # type: ignore[arg-type]
                        simple_errors[configuration],
                        primary_metric_groups=SOURCE_SCORE_PRIMARY_METRICS_V2,
                    )
                    for configuration in fold.source_configurations
                }
                converged = True
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            converged = False
        diagnostics = {} if model is None else dict(model.diagnostics)
        condition = diagnostics.get("condition_number")
        return CandidateValidationResultV2(
            candidate=candidate,
            budget_data_prefix=candidate.data_prefix,
            source_scores=source_scores,
            source_episode_sha256s=fold.source_episode_sha256s,
            design_rank=int(diagnostics.get("design_rank", 0)),
            design_width=int(diagnostics.get("design_width", 1)),
            condition_number=(
                float(condition)
                if isinstance(condition, (int, float)) and math.isfinite(condition)
                else sys.float_info.max
            ),
            converged=converged,
            platform_normalizer_sha256=(
                None if model is None else model.platform_normalizer_sha256
            ),
        )


def _horizon_dict(value: Any) -> dict[str, Any]:
    return {
        "status": value.status,
        "reason_code": value.reason_code,
        "values": dict(value.values),
        "transition_count": value.transition_count,
        "window_count": value.window_count,
        "nonfinite_count": value.nonfinite_count,
        "invalid_quaternion_count": value.invalid_quaternion_count,
        "projection_failure_count": value.projection_failure_count,
        "divergence_count": value.divergence_count,
        "projection_count": value.projection_count,
        "projection_correction_max": value.projection_correction_max,
    }


def _episode_metric_dict(
    artifact: EpisodeMetricArtifactV2,
    entry: EpisodeInventoryEntryV2,
) -> dict[str, Any]:
    return {
        "configuration": artifact.configuration,
        "episode_id": artifact.episode_id,
        "family_repetition": family_repetition_v2(entry.scenario),
        "horizons": {
            name: _horizon_dict(value) for name, value in artifact.horizons.items()
        },
    }


def _role_payload(
    role: ModelRoleV2,
    model: Any,
    test_episodes: Sequence[LoadedEpisodeV2],
    *,
    model_sha256: str | None,
    conditional_candidate: CandidateSpecV2 | None = None,
) -> tuple[dict[str, Any], tuple[EpisodeMetricArtifactV2, ...]]:
    active = model
    if conditional_candidate is not None:
        active = BoundPlatformModelV2(
            model=model,
            platform_descriptor=test_episodes[0].descriptor(
                conditional_candidate.platform_schema
            ),
        )
    artifacts = evaluate_model_episodes_v2(
        active,
        tuple(episode.trajectory() for episode in test_episodes),
        policy=OFFICIAL_ROLLOUT_POLICY_V2,
    )
    failures = [
        horizon.reason_code
        for artifact in artifacts
        for horizon in artifact.horizons.values()
        if horizon.status == "failed"
    ]
    payload = {
        "role": role.value,
        "selection_eligible": role
        in {ModelRoleV2.POOLED, ModelRoleV2.CONDITIONAL},
        "status": "failed" if failures else "success",
        "reason_code": None if not failures else sorted(set(failures))[0],
        "model_sha256": model_sha256,
        "input_fields": (
            ["state_11", "virtual_control_4", "platform_physical_descriptor"]
            if role == ModelRoleV2.CONDITIONAL
            else ["state_11", "virtual_control_4"]
        ),
        "episode_results": [
            _episode_metric_dict(artifact, episode.entry)
            for artifact, episode in zip(artifacts, test_episodes, strict=True)
        ],
    }
    return payload, artifacts


def _save_simple(model: SimpleLinearBaselineV2, path: Path) -> None:
    atomic_write_json(
        path,
        {
            "coefficient_matrix": model.coefficient_matrix.tolist(),
            "diagnostics": dict(model.diagnostics),
            "model_sha256": _simple_hash(model),
            "ridge": model.ridge,
            "role": model.role,
            "version": model.version,
        },
    )


def _select_source_model(
    candidate: CandidateSpecV2,
    episodes: Sequence[LoadedEpisodeV2],
    fold: LOCOFoldManifestV2,
) -> tuple[ControlledEDMDV2, str, dict[str, Any]]:
    ranked: list[tuple[float, int, str, ControlledEDMDV2]] = []
    diagnostics: dict[str, Any] = {}
    for index, configuration in enumerate(fold.source_configurations):
        model = fit_candidate_model_v2(
            candidate,
            episodes,
            configurations=(configuration,),
            fold=None,
        )
        errors = _full_errors(
            model,
            _validation_episodes(episodes, configuration),
            candidate=candidate,
        )
        score = (
            sys.float_info.max
            if errors is None
            else max(float(value) for value in errors.values())
        )
        diagnostics[configuration] = {"validation_worst_metric": score}
        ranked.append((score, index, configuration, model))
    _, _, configuration, model = min(ranked)
    return model, configuration, diagnostics


def _aggregate_roles(
    artifacts: Mapping[str, Sequence[EpisodeMetricArtifactV2]],
) -> dict[str, Any]:
    return {
        role: aggregate_configuration_metrics_v2(
            values,
            expected_configurations=SUPPORTED_EMBODIMENTS,
            expected_horizons=REQUIRED_HORIZON_LABELS_V2,
        )
        for role, values in artifacts.items()
    }


def _validate_dataset_bindings(
    dataset_root: Path,
    dataset_envelope_path: Path,
    inventory_path: Path,
    split_path: Path,
    role_protocol_path: Path,
    inventory: DatasetInventoryV2,
    split: LOCOSplitManifestV2,
    role_protocol: Mapping[str, Any],
) -> None:
    envelope = load_bounded_json(dataset_envelope_path)
    if (
        envelope.get("qualification_level") != "server_isaac_identification_dataset"
        or envelope.get("artifact_origin_level") != "server_isaac_smoke"
    ):
        _fail("main_dataset_qualification_mismatch")
    if envelope.get("protocol_sha256") != file_sha256(role_protocol_path):
        _fail("role_protocol_hash_mismatch")
    if envelope.get("inventory_sha256") != file_sha256(inventory_path):
        _fail("inventory_hash_mismatch")
    if envelope.get("decision_sha256") != file_sha256(split_path):
        _fail("split_hash_mismatch")
    validate_main_role_protocol_v1(role_protocol)
    validate_loco_split_manifest_v2(split, inventory, role_protocol)
    if dataset_envelope_path.parent.resolve() != dataset_root.resolve():
        _fail("dataset_root_binding_mismatch")


def run_phase8_loco_evaluation_v2(
    *,
    dataset_root: str | Path,
    dataset_envelope_path: str | Path,
    inventory_path: str | Path,
    split_path: str | Path,
    role_protocol_path: str | Path,
    inventory: DatasetInventoryV2,
    split: LOCOSplitManifestV2,
    role_protocol: Mapping[str, Any],
    analysis_policy: AnalysisPolicyV2,
    output_root: str | Path,
    source_commit: str,
) -> Path:
    """Run all eight folds once and publish only a complete evaluation root."""

    root = Path(dataset_root).resolve()
    envelope_path = Path(dataset_envelope_path).resolve()
    inventory_file = Path(inventory_path).resolve()
    split_file = Path(split_path).resolve()
    role_file = Path(role_protocol_path).resolve()
    output = Path(output_root).resolve()
    if output.exists() or output.is_symlink():
        _fail("output_root_exists", str(output))
    if not _COMMIT_RE.fullmatch(source_commit):
        _fail("source_commit_invalid")
    _validate_dataset_bindings(
        root,
        envelope_path,
        inventory_file,
        split_file,
        role_file,
        inventory,
        split,
        role_protocol,
    )
    staging = output.with_name(f".{output.name}.staging-{os.getpid()}")
    if staging.exists() or staging.is_symlink():
        _fail("output_root_exists", str(staging))
    staging.mkdir(parents=True)
    all_artifacts: dict[str, list[EpisodeMetricArtifactV2]] = {
        role: [] for role in REQUIRED_ROLES_V2
    }
    fold_payloads: list[dict[str, Any]] = []
    for fold in split.folds:
        fold_root = staging / "folds" / fold.holdout_configuration
        fold_root.mkdir(parents=True)
        primary_view = primary_view_for_fold_v2(fold, inventory, role_protocol)
        expert_view = expert_view_for_fold_v2(fold, inventory, role_protocol)
        session = FoldExecutionV2(
            fold=fold,
            primary_view=primary_view,
            inventory=inventory,
            policy=analysis_policy,
        )
        evaluator_box: dict[str, SourceCandidateEvaluatorV2] = {}

        def candidate_evaluator(
            candidate: CandidateSpecV2,
            opened: tuple[LoadedEpisodeV2, ...],
            bound_fold: LOCOFoldManifestV2,
        ) -> CandidateValidationResultV2:
            if "value" not in evaluator_box:
                evaluator_box["value"] = SourceCandidateEvaluatorV2(opened, bound_fold)
            return evaluator_box["value"](candidate, opened, bound_fold)

        decision = session.seal_decision(
            source_opener=lambda entry: _load_episode(root, entry),
            candidate_evaluator=candidate_evaluator,
            sealed_at=_utc_now(),
            output_path=fold_root / "fold_protocol_decision.json",
        )
        source_episodes = evaluator_box["value"].episodes
        pooled_candidate = decision.selected_candidates[ModelRoleV2.POOLED.value]
        conditional_candidate = decision.selected_candidates[
            ModelRoleV2.CONDITIONAL.value
        ]
        pooled = fit_candidate_model_v2(
            pooled_candidate,
            source_episodes,
            configurations=fold.source_configurations,
            fold=fold,
        )
        conditional = fit_candidate_model_v2(
            conditional_candidate,
            source_episodes,
            configurations=fold.source_configurations,
            fold=fold,
        )
        validate_fold_model_binding_v2(
            decision, pooled, family=ModelRoleV2.POOLED
        )
        validate_fold_model_binding_v2(
            decision, conditional, family=ModelRoleV2.CONDITIONAL
        )
        pooled_fit = _fit_episodes(
            source_episodes,
            configurations=fold.source_configurations,
            data_prefix=pooled_candidate.data_prefix,
        )
        states, controls, targets = _arrays(pooled_fit)
        simple = fit_simple_linear_baseline_v2(
            states, controls, targets, ridge=pooled_candidate.ridge
        )
        source_model, source_configuration, source_diagnostics = _select_source_model(
            pooled_candidate, source_episodes, fold
        )
        model_root = fold_root / "models"
        pooled.save(model_root / "pooled_koopman_v2.json")
        conditional.save(model_root / "conditional_koopman_v2.json")
        source_model.save(model_root / "source_per_configuration_koopman_v2.json")
        _save_simple(simple, model_root / "simple_linear_v2.json")
        frozen = FrozenPrimaryStateV2(
            fold_id=fold.fold_id,
            holdout_configuration=fold.holdout_configuration,
            source_configurations=fold.source_configurations,
            source_episode_sha256s=fold.source_episode_sha256s,
            candidate_id=decision.candidate_id,
            decision_sha256=decision.decision_sha256,
            analysis_policy_sha256=analysis_policy.policy_sha256,
            primary_model_sha256s={
                ModelRoleV2.SIMPLE_LINEAR.value: _simple_hash(simple),
                ModelRoleV2.SOURCE_PER_CONFIGURATION.value: source_model.model_sha256,
                ModelRoleV2.POOLED.value: pooled.model_sha256,
                ModelRoleV2.CONDITIONAL.value: conditional.model_sha256,
            },
            frozen_at=_utc_now(),
        )
        atomic_write_json(fold_root / "pre_test_freeze.json", frozen.to_dict())

        expert_episodes = session.open_expert_decision(
            expert_view=expert_view,
            expert_opener=lambda entry: _load_episode(root, entry),
        )
        expert_fit = tuple(
            episode for episode in expert_episodes if episode.entry.role == "fit"
        )
        expert = fit_candidate_model_v2(
            pooled_candidate,
            expert_fit,
            configurations=(fold.holdout_configuration,),
            fold=None,
        )
        expert.save(model_root / "heldout_expert_upper_bound_v2.json")

        token = authorize_primary_test_access_v2(
            frozen,
            analysis_policy=analysis_policy,
            fold_id=fold.fold_id,
            holdout_configuration=fold.holdout_configuration,
            test_episode_ids=fold.primary_heldout_test_episode_ids,
        )
        test_episodes = session.open_primary_test(
            test_opener=lambda entry: _load_episode(root, entry),
            policy=analysis_policy,
            access_token=token,
        )
        role_models: tuple[
            tuple[ModelRoleV2, Any, str | None, CandidateSpecV2 | None], ...
        ] = (
            (ModelRoleV2.PERSISTENCE, PersistenceBaselineV2(), None, None),
            (ModelRoleV2.SIMPLE_LINEAR, simple, _simple_hash(simple), None),
            (
                ModelRoleV2.SOURCE_PER_CONFIGURATION,
                source_model,
                source_model.model_sha256,
                None,
            ),
            (ModelRoleV2.POOLED, pooled, pooled.model_sha256, None),
            (
                ModelRoleV2.CONDITIONAL,
                conditional,
                conditional.model_sha256,
                conditional_candidate,
            ),
            (
                ModelRoleV2.HELDOUT_EXPERT,
                expert,
                expert.model_sha256,
                None,
            ),
        )
        roles: dict[str, Any] = {}
        for role, model, model_sha, conditional_spec in role_models:
            role_payload, artifacts = _role_payload(
                role,
                model,
                test_episodes,
                model_sha256=model_sha,
                conditional_candidate=conditional_spec,
            )
            roles[role.value] = role_payload
            all_artifacts[role.value].extend(artifacts)
            atomic_write_json(
                fold_root / "metrics" / f"{role.value}.json", role_payload
            )
        fold_payloads.append(
            {
                "fold_id": fold.fold_id,
                "holdout_configuration": fold.holdout_configuration,
                "source_configurations": list(fold.source_configurations),
                "source_episode_sha256s": list(fold.source_episode_sha256s),
                "decision": decision.to_dict(include_sha256=True),
                "pre_test_freeze": frozen.to_dict(),
                "test_access": {
                    "authorized_by_freeze": True,
                    "freeze_candidate_id": token.freeze_candidate_id,
                    "freeze_state_sha256": token.freeze_state_sha256,
                    "test_episode_ids": list(token.test_episode_ids),
                },
                "source_per_configuration_choice": {
                    "selected_source_configuration": source_configuration,
                    "source_validation": source_diagnostics,
                },
                "roles": roles,
                "reference_diagnostic": {
                    "namespace": "diagnostic/reference_conditioned_v2",
                    "selection_eligible": False,
                    "status": "disabled",
                    "reason_code": "disabled_by_frozen_policy",
                },
            }
        )
    aggregate = _aggregate_roles(all_artifacts)
    atomic_write_json(staging / "aggregate_metrics.json", aggregate)
    summary = {
        "evaluation_version": EVALUATION_RESULT_VERSION_V2,
        "analysis_policy_sha256": analysis_policy.policy_sha256,
        "analysis_gate_template": dict(analysis_policy.gate_template),
        "bootstrap_policy": dict(analysis_policy.bootstrap),
        "role_protocol_sha256": file_sha256(role_file),
        "dataset_inventory_sha256": inventory.inventory_sha256,
        "loco_split_sha256": split.split_sha256,
        "rollout_policy": OFFICIAL_ROLLOUT_POLICY_V2.payload(),
        "rollout_policy_sha256": OFFICIAL_ROLLOUT_POLICY_V2.policy_sha256,
        "aggregate_metrics": aggregate,
        "folds": fold_payloads,
    }
    summary_path = staging / "evaluation_summary.json"
    atomic_write_json(summary_path, summary)
    runtime = {
        "data_artifact_origin": "server_isaac_smoke",
        "data_qualification": "server_isaac_identification_dataset",
        "evaluation_execution": "local_offline_deterministic",
        "numpy_version": np.__version__,
        "python_version": sys.version.split()[0],
        "rollout_policy_sha256": OFFICIAL_ROLLOUT_POLICY_V2.policy_sha256,
    }
    files = sorted(path for path in staging.rglob("*") if path.is_file())
    references = referenced_file_records(staging, files)
    evaluation_envelope = {
        "envelope_version": PHASE8_EVIDENCE_ENVELOPE_V1,
        "experiment_id": EVALUATION_EXPERIMENT_ID_V2,
        "artifact_origin_level": "server_isaac_smoke",
        "qualification_level": "offline_koopman_ood_evaluation",
        "source_commit": source_commit,
        "protocol_sha256": file_sha256(role_file),
        "runtime_provenance": runtime,
        "runtime_sha256": canonical_sha256(runtime),
        "inventory_sha256": file_sha256(inventory_file),
        "decision_sha256": file_sha256(summary_path),
        "referenced_files": references,
        "allowed_claims": ["heldout_configuration_prediction_evaluation"],
        "disallowed_claims": [
            "closed_loop_control_effectiveness",
            "environment_transfer",
            "agentic_behavior",
            "hardware_validity",
        ],
        "validator": {
            "name": "run_phase8_loco_evaluation_v2",
            "external_validation": True,
            "status": "pass",
        },
    }
    atomic_write_json(staging / "evaluation_envelope.json", evaluation_envelope)
    validate_phase8_evidence(
        staging / "evaluation_envelope.json",
        required_qualification="offline_koopman_ood_evaluation",
    )
    os.replace(staging, output)
    return output / "evaluation_envelope.json"
