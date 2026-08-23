"""Behavior contracts for additive Phase 8 preprocessing, baselines and EDMD."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.baselines_v2 import (
    PersistenceBaselineV2,
    SimpleLinearBaselineV2,
    fit_simple_linear_baseline_v2,
)
from koopman.model_v2 import (
    CONTROL_DIM_V2,
    MODEL_VERSION_V2,
    STATE_DIM_V2,
    ControlledEDMDV2,
    build_controlled_design_v2,
    observable_feature_names_v2,
)
from koopman.platform_features_v2 import (
    build_platform_descriptor_v2,
    declared_platform_context_v2,
    fit_platform_feature_normalizer_v2,
    select_platform_feature_schema_v2,
)
from koopman.preprocessing_v2 import (
    QUATERNION_PREPROCESSOR_VERSION_V2,
    preprocess_quaternion_episode_v2,
)
from koopman.splits_v2 import LOCOFoldManifestV2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "koopman_phase8_synthetic_system"
    / "known_controlled_system_v1.json"
)

EXPECTED_IDENTITY_FEATURES = (
    "bias",
    "depth_z",
    "quat_w",
    "quat_x",
    "quat_y",
    "quat_z",
    "lin_vel_b_x",
    "lin_vel_b_y",
    "lin_vel_b_z",
    "ang_vel_b_x",
    "ang_vel_b_y",
    "ang_vel_b_z",
)
EXPECTED_AUV_KINEMATIC_FEATURES = EXPECTED_IDENTITY_FEATURES + (
    "depth_z_sq",
    "lin_vel_b_x_sq",
    "lin_vel_b_y_sq",
    "lin_vel_b_z_sq",
    "ang_vel_b_x_sq",
    "ang_vel_b_y_sq",
    "ang_vel_b_z_sq",
    "quat_w_x_ang_vel_b_x",
    "quat_w_x_ang_vel_b_y",
    "quat_w_x_ang_vel_b_z",
    "quat_x_x_ang_vel_b_x",
    "quat_x_x_ang_vel_b_y",
    "quat_x_x_ang_vel_b_z",
    "quat_y_x_ang_vel_b_x",
    "quat_y_x_ang_vel_b_y",
    "quat_y_x_ang_vel_b_z",
    "quat_z_x_ang_vel_b_x",
    "quat_z_x_ang_vel_b_y",
    "quat_z_x_ang_vel_b_z",
    "lin_vel_b_x_x_ang_vel_b_x",
    "lin_vel_b_x_x_ang_vel_b_y",
    "lin_vel_b_x_x_ang_vel_b_z",
    "lin_vel_b_y_x_ang_vel_b_x",
    "lin_vel_b_y_x_ang_vel_b_y",
    "lin_vel_b_y_x_ang_vel_b_z",
    "lin_vel_b_z_x_ang_vel_b_x",
    "lin_vel_b_z_x_ang_vel_b_y",
    "lin_vel_b_z_x_ang_vel_b_z",
)


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _fold(holdout: str = "base") -> LOCOFoldManifestV2:
    sources = tuple(item for item in SUPPORTED_EMBODIMENTS if item != holdout)
    source_ids = tuple(f"source-{configuration}" for configuration in sources)
    source_hashes = tuple(
        hashlib.sha256(episode_id.encode("utf-8")).hexdigest()
        for episode_id in source_ids
    )
    return LOCOFoldManifestV2(
        fold_id=f"loco-holdout-{holdout}",
        holdout_configuration=holdout,
        source_configurations=sources,
        primary_source_episode_ids=source_ids,
        primary_heldout_test_episode_ids=(f"test-{holdout}",),
        expert_fit_validation_episode_ids=(f"expert-{holdout}",),
        expert_test_episode_ids=(f"test-{holdout}",),
        source_episode_sha256s=source_hashes,
        sealed_heldout_digest="3" * 64,
        inventory_sha256="1" * 64,
        role_protocol_sha256="2" * 64,
    )


def _known_system(
    *, samples: int = 160, seed_offset: int = 0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    spec = _fixture()
    rng = np.random.default_rng(int(spec["seed"]) + seed_offset)
    states = rng.normal(scale=0.35, size=(samples, STATE_DIM_V2))
    quaternions = rng.normal(size=(samples, 4))
    quaternions[:, 0] = np.abs(quaternions[:, 0]) + 0.25
    states[:, 1:5] = quaternions / np.linalg.norm(quaternions, axis=1, keepdims=True)
    controls = rng.uniform(-0.3, 0.3, size=(samples, CONTROL_DIM_V2))
    diagonal = np.asarray(spec["state_diagonal"], dtype=float)
    control_matrix = np.asarray(spec["control_matrix"], dtype=float)
    targets = states * diagonal + controls @ control_matrix.T
    targets[:, 1:5] = states[:, 1:5]
    return states, controls, targets


def _preprocessed_known_system(
    *, samples: int = 160, seed_offset: int = 0
):
    states, controls, targets = _known_system(samples=samples, seed_offset=seed_offset)
    preprocessed = preprocess_quaternion_episode_v2(
        states, targets, episode_id=f"known-{seed_offset}"
    )
    return preprocessed, controls


def _platform_inputs(fold: LOCOFoldManifestV2):
    schema = select_platform_feature_schema_v2("platform_physical_core_v1")
    descriptors = {
        configuration: build_platform_descriptor_v2(
            [declared_platform_context_v2(configuration)], schema=schema
        )
        for configuration in SUPPORTED_EMBODIMENTS
    }
    normalizer = fit_platform_feature_normalizer_v2(
        {configuration: descriptors[configuration] for configuration in fold.source_configurations},
        fold=fold,
        schema=schema,
    )
    return schema, descriptors, normalizer


def test_fixture_is_versioned_and_known_system_is_exact() -> None:
    spec = _fixture()
    assert spec["version"] == "phase8-known-controlled-system-v1"
    states, controls, targets = _known_system(samples=32)
    assert states.shape == targets.shape == (32, 11)
    assert controls.shape == (32, 4)
    assert np.allclose(targets[:, 1:5], states[:, 1:5])


def test_quaternion_preprocessing_is_episode_continuous_non_mutating_and_hashed() -> None:
    states = np.zeros((4, 11), dtype=float)
    targets = np.zeros((4, 11), dtype=float)
    states[:, 1:5] = np.asarray(
        [
            [-1.0, 0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [-np.sqrt(0.5), 0.0, 0.0, -np.sqrt(0.5)],
            [np.sqrt(0.5), 0.0, 0.0, np.sqrt(0.5)],
        ]
    )
    targets[:, 1:5] = np.roll(states[:, 1:5], -1, axis=0)
    original_states = states.copy()
    original_targets = targets.copy()

    result = preprocess_quaternion_episode_v2(states, targets, episode_id="sign-flips")
    again = preprocess_quaternion_episode_v2(states, targets, episode_id="sign-flips")

    assert result.version == QUATERNION_PREPROCESSOR_VERSION_V2
    assert result.preprocessor_sha256 == again.preprocessor_sha256
    assert len(result.preprocessor_sha256) == 64
    assert np.all(np.sum(result.states[1:, 1:5] * result.states[:-1, 1:5], axis=1) >= 0.0)
    assert result.states[0, 1] >= 0.0
    assert np.all(np.sum(result.targets[:-1, 1:5] * result.states[1:, 1:5], axis=1) >= 0.0)
    assert np.array_equal(states, original_states)
    assert np.array_equal(targets, original_targets)
    assert not result.states.flags.writeable
    assert not result.targets.flags.writeable


@pytest.mark.parametrize(
    ("states", "targets", "reason"),
    [
        (np.zeros((2, 10)), np.zeros((2, 11)), "preprocessing_shape_invalid"),
        (np.zeros((2, 11)), np.zeros((3, 11)), "preprocessing_shape_invalid"),
        (np.full((2, 11), np.nan), np.zeros((2, 11)), "preprocessing_nonfinite"),
    ],
)
def test_quaternion_preprocessing_rejects_invalid_arrays(states, targets, reason) -> None:
    with pytest.raises(ValueError, match=reason):
        preprocess_quaternion_episode_v2(states, targets, episode_id="invalid")


def test_observable_schemas_have_exact_order_dimensions_and_hashes() -> None:
    identity = observable_feature_names_v2("identity_v1")
    kinematic = observable_feature_names_v2("auv_kinematic_v1")

    assert identity == EXPECTED_IDENTITY_FEATURES
    assert kinematic == EXPECTED_AUV_KINEMATIC_FEATURES
    assert len(identity) == 12
    assert len(kinematic) == 40
    assert observable_feature_names_v2("identity_v1") is identity
    with pytest.raises(ValueError, match="observable_schema_unknown"):
        observable_feature_names_v2("reference_conditioned")


def test_conditional_design_is_exact_platform_affine_kronecker_order() -> None:
    states, controls, _ = _known_system(samples=3)
    physical = np.asarray([[1.0, 2.0], [-1.0, 0.5], [0.25, -0.75]])
    pooled = build_controlled_design_v2(
        states,
        controls,
        observable_schema="identity_v1",
        conditioning="none",
    )
    conditional = build_controlled_design_v2(
        states,
        controls,
        observable_schema="identity_v1",
        conditioning="platform_affine",
        normalized_platform_features=physical,
    )
    expected = np.concatenate(
        [
            pooled,
            physical,
            np.einsum("ni,nj->nij", physical, pooled).reshape(3, -1),
        ],
        axis=1,
    )
    assert pooled.shape == (3, 16)
    assert conditional.shape == (3, 50)
    assert np.array_equal(conditional, expected)


def test_v2_baselines_use_only_state11_and_virtual_control4() -> None:
    preprocessed, controls = _preprocessed_known_system()
    persistence = PersistenceBaselineV2()
    linear = fit_simple_linear_baseline_v2(
        preprocessed.states, controls, preprocessed.targets, ridge=0.0
    )

    assert persistence.predict_next(preprocessed.states[0], controls[0]).shape == (11,)
    assert np.array_equal(
        persistence.predict_next(preprocessed.states[:3], controls[:3]),
        preprocessed.states[:3],
    )
    prediction = linear.predict_next(preprocessed.states, controls)
    assert isinstance(linear, SimpleLinearBaselineV2)
    assert linear.coefficient_matrix.shape == (11, 16)
    assert np.max(np.abs(prediction - preprocessed.targets)) < 1.0e-9


def test_controlled_edmd_recovers_known_system_and_predicts_single_or_batch() -> None:
    preprocessed, controls = _preprocessed_known_system()
    model = ControlledEDMDV2.fit(
        preprocessed.states,
        controls,
        preprocessed.targets,
        preprocessing_sha256=preprocessed.preprocessor_sha256,
        observable_schema="identity_v1",
        conditioning="none",
        ridge=0.0,
        normalization="none",
    )

    batch = model.predict_next(preprocessed.states, controls)
    single = model.predict_next(preprocessed.states[0], controls[0])
    assert model.version == MODEL_VERSION_V2
    assert model.observable_dim == 12
    assert model.design_width == 16
    assert model.control_dim == 4
    assert model.state_dim == 11
    assert model.diagnostics["design_rank"] == 16
    assert model.diagnostics["solve_method"] == "solve"
    assert model.diagnostics["condition_finite"] is True
    assert np.max(np.abs(batch - preprocessed.targets)) < 1.0e-9
    assert np.allclose(single, batch[0])


def test_controlled_edmd_uses_deterministic_pinv_for_singular_design() -> None:
    states = np.tile(np.asarray([0.0, 1.0, 0.0, 0.0, 0.0] + [0.0] * 6), (8, 1))
    controls = np.zeros((8, 4), dtype=float)
    targets = states.copy()
    preprocessed = preprocess_quaternion_episode_v2(states, targets, episode_id="rank-deficient")
    first = ControlledEDMDV2.fit(
        preprocessed.states,
        controls,
        preprocessed.targets,
        preprocessing_sha256=preprocessed.preprocessor_sha256,
        observable_schema="identity_v1",
        conditioning="none",
        ridge=0.0,
        normalization="none",
    )
    second = ControlledEDMDV2.fit(
        preprocessed.states,
        controls,
        preprocessed.targets,
        preprocessing_sha256=preprocessed.preprocessor_sha256,
        observable_schema="identity_v1",
        conditioning="none",
        ridge=0.0,
        normalization="none",
    )
    assert first.diagnostics["solve_method"] == "pinv"
    assert first.diagnostics["design_rank"] < first.design_width
    assert np.array_equal(first.coefficient_matrix, second.coefficient_matrix)


def test_platform_affine_model_uses_fold_fitted_physical_descriptor() -> None:
    spec = _fixture()
    fold = _fold("base")
    _, descriptors, normalizer = _platform_inputs(fold)
    rows_per_configuration = int(spec["configuration_samples"])
    all_states: list[np.ndarray] = []
    all_controls: list[np.ndarray] = []
    all_targets: list[np.ndarray] = []
    all_descriptors = []
    effect = np.asarray(spec["platform_interaction_effect"], dtype=float)
    for index, configuration in enumerate(fold.source_configurations):
        states, controls, targets = _known_system(
            samples=rows_per_configuration, seed_offset=100 + index
        )
        normalized = normalizer.transform(descriptors[configuration])
        targets = targets + normalized[0] * controls[:, [0]] * effect
        targets[:, 1:5] = states[:, 1:5]
        all_states.append(states)
        all_controls.append(controls)
        all_targets.append(targets)
        all_descriptors.extend([descriptors[configuration]] * rows_per_configuration)
    states = np.concatenate(all_states)
    controls = np.concatenate(all_controls)
    targets = np.concatenate(all_targets)
    preprocessed = preprocess_quaternion_episode_v2(
        states, targets, episode_id="seven-source-conditional"
    )

    model = ControlledEDMDV2.fit(
        preprocessed.states,
        controls,
        preprocessed.targets,
        preprocessing_sha256=preprocessed.preprocessor_sha256,
        observable_schema="identity_v1",
        conditioning="platform_affine",
        ridge=0.0,
        normalization="none",
        platform_descriptors=tuple(all_descriptors),
        platform_normalizer=normalizer,
        fold=fold,
    )
    prediction = model.predict_next(
        preprocessed.states,
        controls,
        platform_descriptor=tuple(all_descriptors),
    )
    assert model.platform_feature_dimension == normalizer.mean.size
    assert model.platform_normalizer_sha256 == normalizer.normalizer_sha256
    assert model.fold_id == fold.fold_id
    assert np.max(np.abs(prediction - preprocessed.targets)) < 1.0e-8


def test_model_round_trip_binds_schema_preprocessor_normalizers_and_model_hash(tmp_path) -> None:
    preprocessed, controls = _preprocessed_known_system(samples=96)
    model = ControlledEDMDV2.fit(
        preprocessed.states,
        controls,
        preprocessed.targets,
        preprocessing_sha256=preprocessed.preprocessor_sha256,
        observable_schema="auv_kinematic_v1",
        conditioning="none",
        ridge=1.0e-8,
        normalization="standard_v1",
    )
    path = tmp_path / "nested" / "model.json"
    model.save(path)
    loaded = ControlledEDMDV2.load(path)

    assert loaded.model_sha256 == model.model_sha256
    assert loaded.observable_schema_sha256 == model.observable_schema_sha256
    assert loaded.preprocessing_sha256 == preprocessed.preprocessor_sha256
    assert loaded.input_normalizer_sha256 == model.input_normalizer_sha256
    assert loaded.target_normalizer_sha256 == model.target_normalizer_sha256
    assert loaded.to_dict() == model.to_dict()
    assert np.allclose(
        loaded.predict_next(preprocessed.states[:5], controls[:5]),
        model.predict_next(preprocessed.states[:5], controls[:5]),
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda payload: payload.update(version="koopman-edmd-v1"), "model_version_unsupported"),
        (
            lambda payload: payload.update(observable_schema_sha256="0" * 64),
            "observable_schema_hash_mismatch",
        ),
        (lambda payload: payload.update(model_sha256="0" * 64), "model_hash_mismatch"),
    ],
)
def test_model_loading_rejects_v1_stale_schema_or_stale_hash(mutation, reason) -> None:
    preprocessed, controls = _preprocessed_known_system(samples=64)
    model = ControlledEDMDV2.fit(
        preprocessed.states,
        controls,
        preprocessed.targets,
        preprocessing_sha256=preprocessed.preprocessor_sha256,
        observable_schema="identity_v1",
        conditioning="none",
        ridge=1.0e-8,
        normalization="none",
    )
    payload = deepcopy(model.to_dict())
    mutation(payload)
    with pytest.raises(ValueError, match=reason):
        ControlledEDMDV2.from_dict(payload)


def test_conditional_fit_rejects_wrong_fold_or_heldout_descriptor() -> None:
    fold = _fold("base")
    _, descriptors, normalizer = _platform_inputs(fold)
    preprocessed, controls = _preprocessed_known_system(samples=32)
    wrong = replace(normalizer, fold_id="loco-holdout-other")

    with pytest.raises(ValueError, match="normalizer_fold_mismatch"):
        ControlledEDMDV2.fit(
            preprocessed.states,
            controls,
            preprocessed.targets,
            preprocessing_sha256=preprocessed.preprocessor_sha256,
            observable_schema="identity_v1",
            conditioning="platform_affine",
            ridge=0.0,
            normalization="none",
            platform_descriptors=(descriptors[fold.source_configurations[0]],) * 32,
            platform_normalizer=wrong,
            fold=fold,
        )
    with pytest.raises(ValueError, match="heldout_design_leakage"):
        ControlledEDMDV2.fit(
            preprocessed.states,
            controls,
            preprocessed.targets,
            preprocessing_sha256=preprocessed.preprocessor_sha256,
            observable_schema="identity_v1",
            conditioning="platform_affine",
            ridge=0.0,
            normalization="none",
            platform_descriptors=(descriptors[fold.holdout_configuration],) * 32,
            platform_normalizer=normalizer,
            fold=fold,
        )


@pytest.mark.parametrize(
    ("states", "controls", "targets", "reason"),
    [
        (np.zeros((3, 10)), np.zeros((3, 4)), np.zeros((3, 11)), "model_shape_invalid"),
        (np.zeros((3, 11)), np.zeros((3, 5)), np.zeros((3, 11)), "model_shape_invalid"),
        (np.zeros((3, 11)), np.zeros((2, 4)), np.zeros((3, 11)), "model_shape_invalid"),
        (np.full((3, 11), np.nan), np.zeros((3, 4)), np.zeros((3, 11)), "model_nonfinite"),
    ],
)
def test_model_fit_rejects_shape_drift_and_nonfinite(states, controls, targets, reason) -> None:
    with pytest.raises(ValueError, match=reason):
        ControlledEDMDV2.fit(
            states,
            controls,
            targets,
            preprocessing_sha256="a" * 64,
            observable_schema="identity_v1",
            conditioning="none",
            ridge=0.0,
            normalization="none",
        )


def test_model_and_baseline_public_signatures_have_no_forbidden_input_route() -> None:
    forbidden = (
        "reference",
        "pwm",
        "wrench",
        "environment",
        "oracle",
        "configuration_identity",
        "one_hot",
    )
    callables = (
        PersistenceBaselineV2.predict_next,
        SimpleLinearBaselineV2.predict_next,
        fit_simple_linear_baseline_v2,
        ControlledEDMDV2.fit,
        ControlledEDMDV2.predict_next,
    )
    for function in callables:
        parameter_names = tuple(inspect.signature(function).parameters)
        assert not any(
            token in parameter.lower()
            for parameter in parameter_names
            for token in forbidden
        ), (function.__qualname__, parameter_names)
