"""Source-only physical descriptor and deterministic PCA2 contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.platform_features_v21 import (
    FINAL_REFIT_ALL8_SCOPE_V21,
    LOCO_SOURCE7_SCOPE_V21,
    PHYSICAL_CORE_FEATURE_NAMES_V21,
    PhysicalCoreDescriptorV21,
    SourcePCAProjectorV21,
    build_physical_core_descriptor_v21,
    declared_platform_context_v21,
    fit_source_pca_v21,
    fit_final_refit_pca_v21,
    heldout_descriptor_diagnostic_v21,
)


EXPECTED_NAMES = (
    "log_mass_kg",
    "log_volume_m3",
    "log_inertia_x_kg_m2",
    "log_inertia_y_kg_m2",
    "log_inertia_z_kg_m2",
    "com_to_cob_x_m",
    "com_to_cob_y_m",
    "com_to_cob_z_m",
    "log_drag_multiplier",
    "log_thruster_time_constant_s",
    "thruster_count_fraction",
    "declared_control_rank_fraction",
    "control_mask_roll",
    "control_mask_pitch",
    "control_mask_yaw",
    "control_mask_depth",
    "allocation_mode_legacy",
    "allocation_mode_pinv",
    "allocation_mode_wls",
)


def _synthetic_descriptors() -> tuple[tuple[str, ...], dict[str, PhysicalCoreDescriptorV21]]:
    names = tuple(f"source-{index}" for index in range(7))
    first_two = ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
    descriptors = {}
    for name, pair in zip(names, first_two, strict=True):
        values = np.zeros(19, dtype=np.float64)
        values[:2] = pair
        descriptors[name] = PhysicalCoreDescriptorV21(name, values)
    return names, descriptors


def test_physical_core_names_order_and_formulas_are_exact() -> None:
    context = declared_platform_context_v21("base")
    descriptor = build_physical_core_descriptor_v21([context])
    inertia = context["inertia_diagonal_kg_m2"]
    offset = context["com_to_cob_offset_m"]
    expected = np.asarray(
        [
            math.log(context["mass_kg"]),
            math.log(context["volume_m3"]),
            math.log(inertia[0]),
            math.log(inertia[1]),
            math.log(inertia[2]),
            offset[0],
            offset[1],
            offset[2],
            math.log(context["drag_multiplier"]),
            math.log(context["thruster_dynamics_time_constant_s"]),
            context["thruster_count"] / 8.0,
            context["declared_control_rank"] / 4.0,
            *map(float, context["control_mask"]),
            float(context["allocation_mode"] == "legacy"),
            float(context["allocation_mode"] == "pinv"),
            float(context["allocation_mode"] == "wls"),
        ],
        dtype=np.float64,
    )

    assert PHYSICAL_CORE_FEATURE_NAMES_V21 == EXPECTED_NAMES
    assert descriptor.configuration == "base"
    assert descriptor.values.dtype == np.float64
    assert descriptor.values.flags.writeable is False
    assert np.array_equal(descriptor.values, expected)


def test_descriptor_rejects_identity_facts_and_invalid_log_inputs() -> None:
    identity = declared_platform_context_v21("base")
    identity["configuration_hash"] = "0" * 64
    with pytest.raises(ValueError, match="configuration_identity_forbidden"):
        build_physical_core_descriptor_v21([identity])

    invalid = declared_platform_context_v21("base")
    invalid["thruster_dynamics_time_constant_s"] = 0.0
    with pytest.raises(ValueError, match="physical_value_invalid"):
        build_physical_core_descriptor_v21([invalid])


def test_all_exact_eight_catalog_descriptors_are_finite() -> None:
    descriptors = {
        name: build_physical_core_descriptor_v21([declared_platform_context_v21(name)])
        for name in SUPPORTED_EMBODIMENTS
    }
    assert set(descriptors) == set(SUPPORTED_EMBODIMENTS)
    assert all(item.values.shape == (19,) for item in descriptors.values())
    assert all(np.isfinite(item.values).all() for item in descriptors.values())


def test_source_pca_removes_exact_zero_variance_and_canonicalizes_tied_basis() -> None:
    sources, descriptors = _synthetic_descriptors()

    projector = fit_source_pca_v21(descriptors, source_configurations=sources)

    assert projector.source_configurations == sources
    assert np.array_equal(projector.retained_feature_indices, [0, 1])
    assert np.array_equal(projector.mean, np.zeros(19))
    assert np.allclose(projector.scale[:2], math.sqrt(2.0 / 7.0))
    assert np.array_equal(projector.components, np.eye(2))
    assert projector.affine_rank == 2
    assert projector.component_count == 2
    assert projector.whitening is False


def test_source_pca_is_row_order_invariant_and_heldout_cannot_enter_fit() -> None:
    sources, descriptors = _synthetic_descriptors()
    forward = fit_source_pca_v21(descriptors, source_configurations=sources)
    reverse = fit_source_pca_v21(
        descriptors, source_configurations=tuple(reversed(sources))
    )

    assert np.array_equal(forward.mean, reverse.mean)
    assert np.array_equal(forward.scale, reverse.scale)
    assert np.array_equal(forward.components, reverse.components)

    poison = deepcopy(descriptors)
    poison["heldout"] = PhysicalCoreDescriptorV21(
        "heldout", np.full(19, 1.0e300, dtype=np.float64)
    )
    with pytest.raises(ValueError, match="source_descriptor_set_mismatch"):
        fit_source_pca_v21(poison, source_configurations=sources)


def test_source_pca_rejects_affine_rank_below_two() -> None:
    sources, descriptors = _synthetic_descriptors()
    one_dimensional = {
        name: PhysicalCoreDescriptorV21(
            name, np.asarray([float(index)] + [0.0] * 18, dtype=np.float64)
        )
        for index, name in enumerate(sources)
    }

    with pytest.raises(ValueError, match="descriptor_affine_rank_below_required"):
        fit_source_pca_v21(one_dimensional, source_configurations=sources)


def test_heldout_diagnostic_is_selection_ineligible_and_does_not_mutate_projector() -> None:
    sources, descriptors = _synthetic_descriptors()
    projector = fit_source_pca_v21(descriptors, source_configurations=sources)
    before = projector.to_dict()
    heldout = PhysicalCoreDescriptorV21(
        "heldout", np.asarray([0.25, -0.25] + [0.0] * 17, dtype=np.float64)
    )

    diagnostic = heldout_descriptor_diagnostic_v21(projector, heldout)

    assert diagnostic["selection_eligible"] is False
    assert diagnostic["configuration"] == "heldout"
    assert len(diagnostic["pca_scores_2"]) == 2
    assert isinstance(diagnostic["within_source_feature_ranges"], bool)
    assert isinstance(diagnostic["inside_source_convex_hull"], bool)
    assert diagnostic["pca_residual_norm"] >= 0.0
    assert projector.to_dict() == before


def test_final_refit_pca_is_exact_all_eight_equal_configuration_and_round_trips() -> None:
    descriptors = {
        configuration: build_physical_core_descriptor_v21(
            [declared_platform_context_v21(configuration)]
        )
        for configuration in SUPPORTED_EMBODIMENTS
    }

    projector = fit_final_refit_pca_v21(descriptors)
    loaded = SourcePCAProjectorV21.from_dict(projector.to_dict())

    assert projector.population_scope == FINAL_REFIT_ALL8_SCOPE_V21
    assert projector.source_configurations == tuple(SUPPORTED_EMBODIMENTS)
    assert projector.normalized_source_matrix.shape[0] == 8
    assert projector.component_count == 2
    assert projector.whitening is False
    assert loaded.to_dict() == projector.to_dict()


def test_fold_and_final_refit_pca_population_sizes_cannot_be_substituted() -> None:
    descriptors = {
        configuration: build_physical_core_descriptor_v21(
            [declared_platform_context_v21(configuration)]
        )
        for configuration in SUPPORTED_EMBODIMENTS
    }
    source_seven = tuple(SUPPORTED_EMBODIMENTS[:-1])

    with pytest.raises(ValueError, match="source_descriptor_set_mismatch"):
        fit_source_pca_v21(
            descriptors,
            source_configurations=source_seven,
        )
    with pytest.raises(ValueError, match="final_refit_configuration_set_mismatch"):
        fit_final_refit_pca_v21(
            {
                configuration: descriptors[configuration]
                for configuration in source_seven
            }
        )

    fold = fit_source_pca_v21(
        {
            configuration: descriptors[configuration]
            for configuration in source_seven
        },
        source_configurations=source_seven,
    )
    assert fold.population_scope == LOCO_SOURCE7_SCOPE_V21
    with pytest.raises(ValueError, match="pca_population_scope_invalid"):
        replace(fold, population_scope=FINAL_REFIT_ALL8_SCOPE_V21)


@pytest.mark.parametrize("heldout", SUPPORTED_EMBODIMENTS)
def test_exact_eight_catalog_all_loco_folds_have_valid_source_only_pca2(
    heldout: str,
) -> None:
    descriptors = {
        configuration: build_physical_core_descriptor_v21(
            [declared_platform_context_v21(configuration)]
        )
        for configuration in SUPPORTED_EMBODIMENTS
    }
    sources = tuple(
        configuration
        for configuration in SUPPORTED_EMBODIMENTS
        if configuration != heldout
    )

    projector = fit_source_pca_v21(
        {configuration: descriptors[configuration] for configuration in sources},
        source_configurations=sources,
    )

    assert projector.population_scope == LOCO_SOURCE7_SCOPE_V21
    assert projector.source_configurations == sources
    assert heldout not in projector.source_configurations
    assert projector.normalized_source_matrix.shape[0] == 7
    assert projector.affine_rank >= 2
    assert projector.component_count == 2
