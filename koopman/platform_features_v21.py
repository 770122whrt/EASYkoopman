"""Frozen physical-core descriptor and source-only PCA2 for Phase 8.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from koopman.contracts_v21 import FINAL_REFIT_ALL8_SCOPE_V21, LOCO_SOURCE7_SCOPE_V21
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.evidence_v2 import canonical_sha256
from koopman.platform_features_v2 import (
    build_platform_descriptor_v2,
    declared_platform_context_v2,
    select_platform_feature_schema_v2,
)


PHYSICAL_CORE_SCHEMA_NAME_V21 = "platform_physical_core_v1"
PCA_VERSION_V21 = "phase8.1-source-pca2-v1"
PCA_COMPONENT_COUNT_V21 = 2
PHYSICAL_CORE_FEATURE_NAMES_V21 = (
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
PHYSICAL_CORE_DIM_V21 = len(PHYSICAL_CORE_FEATURE_NAMES_V21)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _readonly(value: Any, shape: tuple[int, ...], reason: str) -> np.ndarray:
    array = np.array(value, dtype=np.float64, copy=True)
    if array.shape != shape or not np.isfinite(array).all():
        _fail(reason)
    array.setflags(write=False)
    return array


def _readonly_indices(value: Any) -> np.ndarray:
    array = np.array(value, dtype=np.int64, copy=True)
    if array.ndim != 1 or len(set(map(int, array))) != array.size:
        _fail("pca_retained_features_invalid")
    if np.any(array < 0) or np.any(array >= PHYSICAL_CORE_DIM_V21):
        _fail("pca_retained_features_invalid")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class PhysicalCoreDescriptorV21:
    configuration: str
    values: np.ndarray

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, str) or not self.configuration:
            _fail("configuration_unknown")
        object.__setattr__(
            self,
            "values",
            _readonly(
                self.values,
                (PHYSICAL_CORE_DIM_V21,),
                "physical_value_invalid",
            ),
        )


def declared_platform_context_v21(configuration: str) -> dict[str, Any]:
    """Return the exact catalog-declared facts used by the physical core."""

    return declared_platform_context_v2(configuration)


def build_physical_core_descriptor_v21(
    platform_contexts: Sequence[Mapping[str, Any]],
) -> PhysicalCoreDescriptorV21:
    """Extract the frozen 19D descriptor without adding identity columns."""

    schema = select_platform_feature_schema_v2(PHYSICAL_CORE_SCHEMA_NAME_V21)
    if schema.feature_names != PHYSICAL_CORE_FEATURE_NAMES_V21:
        _fail("physical_feature_schema_drift")
    try:
        descriptor = build_platform_descriptor_v2(platform_contexts, schema=schema)
    except ValueError as exc:
        message = str(exc)
        if "configuration_identity_forbidden" in message:
            raise
        if "physical_" in message or "allocation_mode" in message:
            raise
        raise
    return PhysicalCoreDescriptorV21(descriptor.configuration, descriptor.values)


def _canonical_tied_components(
    covariance: np.ndarray,
    *,
    component_count: int,
    population_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(-eigenvalues, kind="stable")
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    width = covariance.shape[0]
    lambda_max = float(eigenvalues[0]) if eigenvalues.size else 0.0
    epsilon = np.finfo(np.float64).eps
    tie_tolerance = (
        epsilon * max(population_count, width) * max(1.0, abs(lambda_max))
    )
    basis_tolerance = epsilon * max(1, width)

    selected_components: list[np.ndarray] = []
    selected_eigenvalues: list[float] = []
    group_start = 0
    while group_start < eigenvalues.size and len(selected_components) < component_count:
        group_end = group_start + 1
        while (
            group_end < eigenvalues.size
            and abs(float(eigenvalues[group_end] - eigenvalues[group_start]))
            <= tie_tolerance
        ):
            group_end += 1
        group_vectors = eigenvectors[:, group_start:group_end]
        projector = group_vectors @ group_vectors.T
        group_basis: list[np.ndarray] = []
        for axis_index in range(width):
            residual = np.array(projector[:, axis_index], dtype=np.float64, copy=True)
            for existing in group_basis:
                residual -= float(np.dot(existing, residual)) * existing
            residual_norm = float(np.linalg.norm(residual))
            if residual_norm <= basis_tolerance:
                continue
            component = residual / residual_norm
            pivot = int(
                np.flatnonzero(
                    np.abs(component) == np.max(np.abs(component))
                )[0]
            )
            if component[pivot] < 0.0:
                component = -component
            group_basis.append(component)
            selected_components.append(component)
            selected_eigenvalues.append(float(eigenvalues[group_start]))
            if len(selected_components) == component_count:
                break
        group_start = group_end
    if len(selected_components) != component_count:
        _fail("descriptor_affine_rank_below_required")
    return (
        np.asarray(selected_components, dtype=np.float64),
        np.asarray(selected_eigenvalues, dtype=np.float64),
    )


@dataclass(frozen=True)
class SourcePCAProjectorV21:
    source_configurations: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    retained_feature_indices: np.ndarray
    components: np.ndarray
    eigenvalues: np.ndarray
    normalized_source_matrix: np.ndarray
    affine_rank: int
    population_scope: str = LOCO_SOURCE7_SCOPE_V21
    whitening: bool = False
    version: str = PCA_VERSION_V21
    projector_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        sources = tuple(self.source_configurations)
        expected_count = {
            LOCO_SOURCE7_SCOPE_V21: 7,
            FINAL_REFIT_ALL8_SCOPE_V21: 8,
        }.get(self.population_scope)
        if expected_count is None:
            _fail("pca_population_scope_invalid")
        if len(sources) != expected_count or len(set(sources)) != expected_count:
            _fail("pca_population_scope_invalid")
        if (
            self.population_scope == FINAL_REFIT_ALL8_SCOPE_V21
            and sources != tuple(SUPPORTED_EMBODIMENTS)
        ):
            _fail("final_refit_configuration_set_mismatch")
        indices = _readonly_indices(self.retained_feature_indices)
        retained_width = int(indices.size)
        mean = _readonly(
            self.mean, (PHYSICAL_CORE_DIM_V21,), "pca_statistics_invalid"
        )
        scale = _readonly(
            self.scale, (PHYSICAL_CORE_DIM_V21,), "pca_statistics_invalid"
        )
        if np.any(scale < 0.0) or np.any(scale[indices] <= 0.0):
            _fail("pca_statistics_invalid")
        components = _readonly(
            self.components,
            (PCA_COMPONENT_COUNT_V21, retained_width),
            "pca_components_invalid",
        )
        eigenvalues = _readonly(
            self.eigenvalues,
            (PCA_COMPONENT_COUNT_V21,),
            "pca_components_invalid",
        )
        source_matrix = _readonly(
            self.normalized_source_matrix,
            (expected_count, retained_width),
            "pca_statistics_invalid",
        )
        if (
            isinstance(self.affine_rank, bool)
            or not isinstance(self.affine_rank, int)
            or self.affine_rank < PCA_COMPONENT_COUNT_V21
            or self.whitening is not False
            or self.version != PCA_VERSION_V21
        ):
            _fail("pca_contract_invalid")
        object.__setattr__(self, "source_configurations", sources)
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "scale", scale)
        object.__setattr__(self, "retained_feature_indices", indices)
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "eigenvalues", eigenvalues)
        object.__setattr__(self, "normalized_source_matrix", source_matrix)
        object.__setattr__(
            self, "projector_sha256", canonical_sha256(self.payload_without_hash())
        )

    @property
    def component_count(self) -> int:
        return PCA_COMPONENT_COUNT_V21

    def normalized_retained(self, descriptor: PhysicalCoreDescriptorV21) -> np.ndarray:
        if not isinstance(descriptor, PhysicalCoreDescriptorV21):
            _fail("physical_descriptor_required")
        indices = self.retained_feature_indices
        normalized = (descriptor.values[indices] - self.mean[indices]) / self.scale[indices]
        if not np.isfinite(normalized).all():
            _fail("physical_value_invalid")
        return normalized

    def transform(self, descriptor: PhysicalCoreDescriptorV21) -> np.ndarray:
        scores = self.components @ self.normalized_retained(descriptor)
        scores.setflags(write=False)
        return scores

    def payload_without_hash(self) -> dict[str, Any]:
        return {
            "affine_rank": self.affine_rank,
            "components": self.components.tolist(),
            "eigenvalues": self.eigenvalues.tolist(),
            "feature_names": list(PHYSICAL_CORE_FEATURE_NAMES_V21),
            "mean": self.mean.tolist(),
            "normalized_source_matrix": self.normalized_source_matrix.tolist(),
            "population_scope": self.population_scope,
            "retained_feature_indices": self.retained_feature_indices.tolist(),
            "scale": self.scale.tolist(),
            "source_configurations": list(self.source_configurations),
            "version": self.version,
            "whitening": self.whitening,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.payload_without_hash(),
            "projector_sha256": self.projector_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourcePCAProjectorV21":
        expected = {
            "affine_rank",
            "components",
            "eigenvalues",
            "feature_names",
            "mean",
            "normalized_source_matrix",
            "population_scope",
            "projector_sha256",
            "retained_feature_indices",
            "scale",
            "source_configurations",
            "version",
            "whitening",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("pca_serialization_invalid")
        if tuple(value["feature_names"]) != PHYSICAL_CORE_FEATURE_NAMES_V21:
            _fail("physical_feature_schema_drift")
        result = cls(
            source_configurations=tuple(value["source_configurations"]),
            mean=np.asarray(value["mean"], dtype=np.float64),
            scale=np.asarray(value["scale"], dtype=np.float64),
            retained_feature_indices=np.asarray(
                value["retained_feature_indices"], dtype=np.int64
            ),
            components=np.asarray(value["components"], dtype=np.float64),
            eigenvalues=np.asarray(value["eigenvalues"], dtype=np.float64),
            normalized_source_matrix=np.asarray(
                value["normalized_source_matrix"], dtype=np.float64
            ),
            affine_rank=value["affine_rank"],
            population_scope=value["population_scope"],
            whitening=value["whitening"],
            version=value["version"],
        )
        if value["projector_sha256"] != result.projector_sha256:
            _fail("pca_hash_mismatch")
        return result


def _fit_population_pca_v21(
    descriptors: Mapping[str, PhysicalCoreDescriptorV21],
    *,
    configurations: tuple[str, ...],
    population_scope: str,
) -> SourcePCAProjectorV21:
    population_count = len(configurations)
    if not isinstance(descriptors, Mapping) or set(descriptors) != set(configurations):
        _fail("source_descriptor_set_mismatch")
    rows: list[np.ndarray] = []
    for configuration in configurations:
        descriptor = descriptors[configuration]
        if (
            not isinstance(descriptor, PhysicalCoreDescriptorV21)
            or descriptor.configuration != configuration
        ):
            _fail("source_descriptor_set_mismatch")
        rows.append(descriptor.values)
    values = np.asarray(rows, dtype=np.float64)
    mean = np.mean(values, axis=0, dtype=np.float64)
    scale = np.std(values, axis=0, ddof=0, dtype=np.float64)
    retained = np.flatnonzero(scale != 0.0).astype(np.int64)
    if retained.size < PCA_COMPONENT_COUNT_V21:
        _fail("descriptor_affine_rank_below_required")
    normalized = (values[:, retained] - mean[retained]) / scale[retained]
    singular_values = np.linalg.svd(normalized, compute_uv=False)
    largest = float(singular_values[0]) if singular_values.size else 0.0
    tolerance = (
        np.finfo(np.float64).eps
        * max(population_count, int(retained.size))
        * largest
    )
    affine_rank = int(np.count_nonzero(singular_values > tolerance))
    if affine_rank < PCA_COMPONENT_COUNT_V21:
        _fail("descriptor_affine_rank_below_required")
    covariance = (normalized.T @ normalized) / float(population_count)
    components, eigenvalues = _canonical_tied_components(
        covariance,
        component_count=PCA_COMPONENT_COUNT_V21,
        population_count=population_count,
    )
    return SourcePCAProjectorV21(
        source_configurations=configurations,
        mean=mean,
        scale=scale,
        retained_feature_indices=retained,
        components=components,
        eigenvalues=eigenvalues,
        normalized_source_matrix=normalized,
        affine_rank=affine_rank,
        population_scope=population_scope,
    )


def fit_source_pca_v21(
    descriptors: Mapping[str, PhysicalCoreDescriptorV21],
    *,
    source_configurations: Sequence[str],
) -> SourcePCAProjectorV21:
    """Fit equal-configuration population statistics on exactly seven sources."""

    sources = tuple(source_configurations)
    if len(sources) != 7 or len(set(sources)) != 7:
        _fail("source_configuration_set_mismatch")
    return _fit_population_pca_v21(
        descriptors,
        configurations=sources,
        population_scope=LOCO_SOURCE7_SCOPE_V21,
    )


def fit_final_refit_pca_v21(
    descriptors: Mapping[str, PhysicalCoreDescriptorV21],
) -> SourcePCAProjectorV21:
    """Fit the fixed exact-eight, equal-configuration final-refit PCA2."""

    configurations = tuple(SUPPORTED_EMBODIMENTS)
    if not isinstance(descriptors, Mapping) or set(descriptors) != set(configurations):
        _fail("final_refit_configuration_set_mismatch")
    return _fit_population_pca_v21(
        descriptors,
        configurations=configurations,
        population_scope=FINAL_REFIT_ALL8_SCOPE_V21,
    )


def _inside_convex_hull(source_rows: np.ndarray, point: np.ndarray) -> bool:
    """Small exact-seven feasibility check without adding a SciPy dependency."""

    count = source_rows.shape[0]
    augmented_target = np.concatenate((point, [1.0]))
    scale = max(1.0, float(np.linalg.norm(augmented_target)))
    tolerance = 256.0 * np.finfo(np.float64).eps * max(source_rows.shape) * scale
    for subset_size in range(1, count + 1):
        for subset in combinations(range(count), subset_size):
            matrix = np.vstack((source_rows[list(subset)].T, np.ones(subset_size)))
            weights, _, _, _ = np.linalg.lstsq(matrix, augmented_target, rcond=None)
            residual = float(np.linalg.norm(matrix @ weights - augmented_target))
            if residual <= tolerance and np.all(weights >= -tolerance):
                return True
    return False


def heldout_descriptor_diagnostic_v21(
    projector: SourcePCAProjectorV21,
    descriptor: PhysicalCoreDescriptorV21,
) -> Mapping[str, Any]:
    """Generate post-freeze, selection-ineligible descriptor diagnostics."""

    if projector.population_scope != LOCO_SOURCE7_SCOPE_V21:
        _fail("heldout_diagnostic_scope_invalid")
    if descriptor.configuration in projector.source_configurations:
        _fail("heldout_descriptor_required")
    normalized = projector.normalized_retained(descriptor)
    scores = projector.transform(descriptor)
    reconstruction = scores @ projector.components
    source = projector.normalized_source_matrix
    diagnostic = {
        "configuration": descriptor.configuration,
        "inside_source_convex_hull": _inside_convex_hull(source, normalized),
        "pca_residual_norm": float(np.linalg.norm(normalized - reconstruction)),
        "pca_scores_2": scores.tolist(),
        "selection_eligible": False,
        "within_source_feature_ranges": bool(
            np.all(normalized >= np.min(source, axis=0))
            and np.all(normalized <= np.max(source, axis=0))
        ),
    }
    return MappingProxyType(diagnostic)
