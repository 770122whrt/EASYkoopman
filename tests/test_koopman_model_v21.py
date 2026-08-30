"""Frozen observable, structured-conditional and ridge contracts for Phase 8.1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.model_v21 import (
    CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21,
    CONDITIONAL_POPULATION_LOCO_SOURCE7_V21,
    CONDITIONAL_POPULATION_NOT_APPLICABLE_V21,
    CONDITIONING_NONE_V21,
    CONDITIONING_STRUCTURED_PCA2_V21,
    ESTIMATOR_EQUIVALENCE_CLASS_V21,
    ControlledEDMDV21,
    CandidateAdmissionErrorV21,
    DesignNormalizerV21,
    build_conditional_design_v21,
    build_increment_targets_v21,
    build_observable_features_v21,
    diagnose_solve_design_v21,
    observable_feature_names_v21,
    ridge_solve_v21,
)
from koopman.so3_v21 import so3_exp_v21


EXPECTED_LINEAR_NONBIAS = (
    "depth_m",
    "R00",
    "R10",
    "R20",
    "R01",
    "R11",
    "R21",
    "linear_velocity_body_x",
    "linear_velocity_body_y",
    "linear_velocity_body_z",
    "angular_velocity_body_x",
    "angular_velocity_body_y",
    "angular_velocity_body_z",
    "actuator_memory_roll",
    "actuator_memory_pitch",
    "actuator_memory_yaw",
    "actuator_memory_depth",
    "virtual_control_roll",
    "virtual_control_pitch",
    "virtual_control_yaw",
    "virtual_control_depth",
)


def _random_primary_rows(count: int, seed: int = 123) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    states = np.empty((count, 11), dtype=np.float64)
    states[:, 0] = rng.normal(size=count)
    raw_quaternions = rng.normal(size=(count, 4))
    raw_quaternions /= np.linalg.norm(raw_quaternions, axis=1, keepdims=True)
    states[:, 1:5] = raw_quaternions
    states[:, 5:] = rng.normal(size=(count, 6))
    memories = rng.uniform(-0.8, 0.8, size=(count, 4))
    controls = rng.uniform(-1.0, 1.0, size=(count, 4))
    return states, memories, controls


def _fitted_identity_model() -> ControlledEDMDV21:
    states, memories, controls = _random_primary_rows(160, seed=987)
    design = build_observable_features_v21(
        states, memories, controls, "so3_identity_v1"
    )
    coefficients = np.arange(10 * 22, dtype=np.float64).reshape(10, 22) * 1.0e-5
    return ControlledEDMDV21.fit(
        states,
        memories,
        controls,
        design @ coefficients.T,
        observable_schema="so3_identity_v1",
        conditioning=CONDITIONING_NONE_V21,
        ridge=1.0e-6,
        normalization="standard_v1",
    )


def test_identity_feature_names_values_and_width_are_exact() -> None:
    state = np.asarray(
        [2.0, 1.0, 0.0, 0.0, 0.0, 0.1, -0.2, 0.3, -0.4, 0.5, -0.6],
        dtype=np.float64,
    )
    memory = np.asarray([0.11, 0.12, 0.13, 0.14])
    control = np.asarray([0.21, 0.22, 0.23, 0.24])

    names = observable_feature_names_v21("so3_identity_v1")
    features = build_observable_features_v21(state, memory, control, "so3_identity_v1")

    assert names == ("bias",) + EXPECTED_LINEAR_NONBIAS
    assert len(names) == 22
    assert np.array_equal(
        features,
        np.asarray(
            [
                1.0,
                2.0,
                1.0,
                0.0,
                0.0,
                0.0,
                1.0,
                0.0,
                0.1,
                -0.2,
                0.3,
                -0.4,
                0.5,
                -0.6,
                0.11,
                0.12,
                0.13,
                0.14,
                0.21,
                0.22,
                0.23,
                0.24,
            ]
        ),
    )


def test_kinematic_lift_has_frozen_34_feature_order_and_values() -> None:
    state = np.asarray(
        [2.0, 1.0, 0.0, 0.0, 0.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        dtype=np.float64,
    )
    features = build_observable_features_v21(
        state, np.zeros(4), np.zeros(4), "so3_kinematic_v1"
    )
    names = observable_feature_names_v21("so3_kinematic_v1")
    expected_lift = np.asarray(
        [
            4.0,
            4.0,
            9.0,
            16.0,
            25.0,
            36.0,
            49.0,
            5.0,
            6.0,
            7.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            5.0,
            6.0,
            7.0,
            0.0,
            0.0,
            0.0,
            10.0,
            12.0,
            14.0,
            15.0,
            18.0,
            21.0,
            20.0,
            24.0,
            28.0,
        ]
    )

    assert len(names) == 56
    assert names[22:29] == (
        "depth_m_squared",
        "linear_velocity_body_x_squared",
        "linear_velocity_body_y_squared",
        "linear_velocity_body_z_squared",
        "angular_velocity_body_x_squared",
        "angular_velocity_body_y_squared",
        "angular_velocity_body_z_squared",
    )
    assert np.array_equal(features[22:], expected_lift)


@pytest.mark.parametrize(
    ("observable", "expected_width"),
    (("so3_identity_v1", 66), ("so3_kinematic_v1", 100)),
)
def test_structured_conditional_has_exact_width_without_duplicate_bias_interactions(
    observable: str, expected_width: int
) -> None:
    states, memories, controls = _random_primary_rows(4)
    phi = build_observable_features_v21(states, memories, controls, observable)
    scores = np.asarray([[1.0, 2.0], [-1.0, 1.0], [0.5, -0.5], [0.0, 0.0]])

    design = build_conditional_design_v21(phi, scores)

    assert design.shape == (4, expected_width)
    assert np.array_equal(design[:, : phi.shape[1]], phi)
    assert np.array_equal(design[:, phi.shape[1] : phi.shape[1] + 2], scores)
    assert np.array_equal(design[:, phi.shape[1] + 2 : phi.shape[1] + 23], scores[:, [0]] * phi[:, 1:22])


def test_conditioning_identifiers_are_single_frozen_values() -> None:
    assert CONDITIONING_NONE_V21 == "none"
    assert CONDITIONING_STRUCTURED_PCA2_V21 == "structured_pca2"
    states, memories, controls = _random_primary_rows(32)
    targets = np.zeros((32, 10))
    with pytest.raises(ValueError, match="conditioning_unknown"):
        ControlledEDMDV21.fit(
            states,
            memories,
            controls,
            targets,
            observable_schema="so3_identity_v1",
            conditioning="structured_pca_r2_v1",
            ridge=1e-6,
            normalization="none",
        )


def test_standard_normalizer_preserves_bias_and_uses_population_statistics() -> None:
    design = np.asarray([[1.0, 1.0, 10.0], [1.0, 3.0, 14.0], [1.0, 5.0, 18.0]])
    normalizer = DesignNormalizerV21.fit(design)
    transformed = normalizer.transform(design)

    assert np.array_equal(transformed[:, 0], np.ones(3))
    assert normalizer.mean[0] == 0.0
    assert normalizer.scale[0] == 1.0
    assert np.allclose(normalizer.mean[1:], [3.0, 14.0])
    assert np.allclose(normalizer.scale[1:], np.std(design[:, 1:], axis=0, ddof=0))


def test_rank_effective_rank_and_regularized_condition_use_actual_design() -> None:
    full = np.diag([4.0, 2.0, 1.0])
    diagnostics = diagnose_solve_design_v21(full, ridge=1.0)

    assert diagnostics.design_width == 3
    assert diagnostics.design_rank == 3
    assert diagnostics.effective_rank > 1.0
    assert diagnostics.regularized_condition == pytest.approx((16.0 + 1.0) / (1.0 + 1.0))
    assert diagnostics.admitted is True
    assert diagnostics.rejection_reason is None

    deficient = diagnose_solve_design_v21(np.ones((8, 3)), ridge=1.0e-4)
    assert deficient.design_rank < deficient.design_width
    assert deficient.admitted is False
    assert deficient.rejection_reason == "design_rank_below_width"


def test_ridge_penalty_includes_bias_column() -> None:
    design = np.eye(3, dtype=np.float64)
    target = np.eye(3, dtype=np.float64)

    coefficients = ridge_solve_v21(design, target, ridge=1.0)

    assert np.allclose(coefficients, 0.5 * np.eye(3), atol=1e-15)


def test_controlled_edmd_fits_increment_targets_and_round_trips(tmp_path) -> None:
    states, memories, controls = _random_primary_rows(160)
    design = build_observable_features_v21(states, memories, controls, "so3_identity_v1")
    rng = np.random.default_rng(22)
    truth_coefficients = rng.normal(scale=0.01, size=(10, design.shape[1]))
    targets = design @ truth_coefficients.T

    model = ControlledEDMDV21.fit(
        states,
        memories,
        controls,
        targets,
        observable_schema="so3_identity_v1",
        conditioning="none",
        ridge=1.0e-8,
        normalization="standard_v1",
    )
    predictions = model.predict_increment(states[:8], memories[:8], controls[:8])
    path = tmp_path / "model.json"
    model.save(path)
    loaded = ControlledEDMDV21.load(path)

    assert model.design_width == 22
    assert model.diagnostics["admitted"] is True
    assert model.estimator_equivalence_class == ESTIMATOR_EQUIVALENCE_CLASS_V21
    assert model.simple_linear_equivalent is True
    assert np.max(np.abs(predictions - targets[:8])) < 1.0e-7
    assert loaded.to_dict() == model.to_dict()
    assert np.array_equal(
        loaded.predict_increment(states[:8], memories[:8], controls[:8]), predictions
    )


def test_ridge_bool_is_rejected_by_constructor_and_loader() -> None:
    model = _fitted_identity_model()
    with pytest.raises(ValueError, match="ridge_invalid|model_contract_invalid"):
        replace(model, ridge=True)

    payload = deepcopy(model.to_dict())
    payload["ridge"] = True
    with pytest.raises(ValueError, match="ridge_invalid|model_contract_invalid"):
        ControlledEDMDV21.from_dict(payload)


def test_controlled_edmd_rejects_rank_deficient_candidate_with_diagnostics() -> None:
    state = np.asarray([[0.0, 1.0, 0.0, 0.0, 0.0] + [0.0] * 6] * 32)
    memory = np.zeros((32, 4))
    control = np.zeros((32, 4))
    targets = np.zeros((32, 10))

    with pytest.raises(CandidateAdmissionErrorV21) as captured:
        ControlledEDMDV21.fit(
            state,
            memory,
            control,
            targets,
            observable_schema="so3_identity_v1",
            conditioning="none",
            ridge=1.0e-4,
            normalization="none",
        )

    assert captured.value.diagnostics["rejection_reason"] == "design_rank_below_width"


@pytest.mark.parametrize(
    "mutation",
    (
        lambda diagnostics: {},
        lambda diagnostics: {key: value for key, value in diagnostics.items() if key != "effective_rank"},
        lambda diagnostics: diagnostics | {"unexpected": 1},
        lambda diagnostics: diagnostics | {"admitted": False},
        lambda diagnostics: diagnostics | {"design_rank": diagnostics["design_width"] - 1},
        lambda diagnostics: diagnostics | {"design_width": diagnostics["design_width"] + 1, "design_rank": diagnostics["design_width"] + 1},
        lambda diagnostics: diagnostics | {"regularized_condition": -1.0},
        lambda diagnostics: diagnostics | {"regularized_condition": 1.0e8 + 1.0},
        lambda diagnostics: diagnostics | {"effective_rank": float("nan")},
        lambda diagnostics: diagnostics | {"rank_tolerance": float("inf")},
    ),
)
def test_model_constructor_rejects_unbound_or_invalid_solve_diagnostics(mutation) -> None:
    model = _fitted_identity_model()
    diagnostics = mutation(dict(model.diagnostics))

    with pytest.raises(ValueError, match="model_diagnostics_invalid"):
        replace(model, diagnostics=diagnostics)


def test_model_load_rejects_empty_diagnostics_before_hash_check() -> None:
    model = _fitted_identity_model()
    payload = deepcopy(model.to_dict())
    payload["diagnostics"] = {}

    with pytest.raises(ValueError, match="model_diagnostics_invalid"):
        ControlledEDMDV21.from_dict(payload)


@pytest.mark.parametrize(
    ("observable", "conditioning", "width"),
    (
        ("so3_identity_v1", CONDITIONING_NONE_V21, 22),
        ("so3_kinematic_v1", CONDITIONING_NONE_V21, 56),
        ("so3_identity_v1", CONDITIONING_STRUCTURED_PCA2_V21, 66),
        ("so3_kinematic_v1", CONDITIONING_STRUCTURED_PCA2_V21, 100),
    ),
)
def test_model_artifact_binds_diagnostics_and_coefficients_to_family_width(
    observable: str, conditioning: str, width: int
) -> None:
    diagnostics = {
        "admitted": True,
        "design_rank": width,
        "design_width": width,
        "effective_rank": float(width),
        "rank_tolerance": 1.0e-12,
        "regularized_condition": 2.0,
        "rejection_reason": None,
    }
    sources = tuple(f"source-{index}" for index in range(7))

    model = ControlledEDMDV21(
        coefficient_matrix=np.zeros((10, width)),
        observable_schema=observable,
        conditioning=conditioning,
        ridge=1.0e-6,
        normalization="none",
        diagnostics=diagnostics,
        source_configurations=(
            sources if conditioning == CONDITIONING_STRUCTURED_PCA2_V21 else ()
        ),
        population_scope=(
            CONDITIONAL_POPULATION_LOCO_SOURCE7_V21
            if conditioning == CONDITIONING_STRUCTURED_PCA2_V21
            else CONDITIONAL_POPULATION_NOT_APPLICABLE_V21
        ),
    )
    assert model.design_width == width
    assert model.diagnostics["design_width"] == width

    with pytest.raises(ValueError, match="model_shape_invalid|model_diagnostics_invalid"):
        replace(
            model,
            coefficient_matrix=np.zeros((10, width + 1)),
            diagnostics=diagnostics
            | {"design_rank": width + 1, "design_width": width + 1},
        )


def test_conditional_model_final_refit_scope_requires_exact_all_eight_and_round_trips(
    tmp_path,
) -> None:
    configurations = tuple(SUPPORTED_EMBODIMENTS)
    states, memories, controls = _random_primary_rows(240, seed=414)
    labels = tuple(configurations[index % 8] for index in range(240))
    score_by_configuration = {
        configuration: np.asarray(
            [math.cos(index * 0.7), math.sin(index * 0.7)], dtype=np.float64
        )
        for index, configuration in enumerate(configurations)
    }
    scores = np.asarray([score_by_configuration[label] for label in labels])
    phi = build_observable_features_v21(
        states, memories, controls, "so3_identity_v1"
    )
    design = build_conditional_design_v21(phi, scores)
    target_coefficients = (
        np.arange(10 * 66, dtype=np.float64).reshape(10, 66) * 1.0e-6
    )

    model = ControlledEDMDV21.fit(
        states,
        memories,
        controls,
        design @ target_coefficients.T,
        observable_schema="so3_identity_v1",
        conditioning=CONDITIONING_STRUCTURED_PCA2_V21,
        ridge=1.0e-6,
        normalization="standard_v1",
        platform_scores=scores,
        row_configurations=labels,
        source_configurations=configurations,
        population_scope=CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21,
    )
    path = tmp_path / "final-refit-conditional.json"
    model.save(path)
    loaded = ControlledEDMDV21.load(path)

    assert model.population_scope == CONDITIONAL_POPULATION_FINAL_REFIT_ALL8_V21
    assert len(model.source_configurations) == 8
    assert loaded.to_dict() == model.to_dict()

    with pytest.raises(ValueError, match="conditional_population_scope_invalid"):
        replace(
            model,
            source_configurations=configurations[:-1],
        )
    with pytest.raises(ValueError, match="conditional_population_scope_invalid"):
        replace(
            model,
            population_scope=CONDITIONAL_POPULATION_LOCO_SOURCE7_V21,
        )
    with pytest.raises(ValueError, match="conditional_population_scope_invalid"):
        replace(
            model,
            source_configurations=configurations[:-1] + ("foreign-configuration",),
        )


def test_increment_targets_are_10d_body_right_deltas() -> None:
    current = np.asarray([[1.0, 1.0, 0.0, 0.0, 0.0] + [0.0] * 6])
    next_state = current.copy()
    next_state[0, 0] += 0.2
    next_state[0, 1:5] = so3_exp_v21(np.asarray([0.1, -0.2, 0.3]))
    next_state[0, 5:] += np.asarray([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    target = build_increment_targets_v21(current, next_state)

    assert target.shape == (1, 10)
    assert np.allclose(target[0], [0.2, 1, 2, 3, 4, 5, 6, 0.1, -0.2, 0.3])
