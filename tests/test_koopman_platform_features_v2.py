"""Contracts for physical-only fold-local Phase 8 platform features."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.platform_features_v2 import (
    PlatformFeatureNormalizerV2,
    PlatformFeatureSchemaV2,
    build_platform_descriptor_v2,
    declared_platform_context_v2,
    fit_platform_feature_normalizer_v2,
    select_platform_feature_schema_v2,
)
from koopman.splits_v2 import LOCOFoldManifestV2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PHYSICAL_CORE_FEATURES = (
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
        sealed_heldout_digest=hashlib.sha256(
            f"sealed-{holdout}".encode("utf-8")
        ).hexdigest(),
        inventory_sha256="1" * 64,
        role_protocol_sha256="2" * 64,
    )


def _descriptors(schema_name: str = "platform_physical_core_v1"):
    schema = select_platform_feature_schema_v2(schema_name)
    return schema, {
        configuration: build_platform_descriptor_v2(
            [declared_platform_context_v2(configuration)], schema=schema
        )
        for configuration in SUPPORTED_EMBODIMENTS
    }


def test_physical_feature_schemas_are_versioned_exact_and_identity_free() -> None:
    core = select_platform_feature_schema_v2("platform_physical_core_v1")
    compact = select_platform_feature_schema_v2("platform_physical_compact_v1")

    assert isinstance(core, PlatformFeatureSchemaV2)
    assert core.feature_names == EXPECTED_PHYSICAL_CORE_FEATURES
    assert core.dimension == 19
    assert compact.dimension < core.dimension
    assert core.schema_sha256 != compact.schema_sha256
    assert all(
        forbidden not in feature.lower()
        for feature in core.feature_names + compact.feature_names
        for forbidden in ("configuration", "identity", "name", "hash")
    )
    with pytest.raises(ValueError, match="configuration_identity_forbidden"):
        PlatformFeatureSchemaV2(
            schema_name="bad_identity_v1",
            feature_names=("configuration_one_hot",),
        )
    with pytest.raises(ValueError, match="feature_schema_unknown"):
        select_platform_feature_schema_v2("unregistered")


def test_all_eight_declared_platforms_transform_under_each_frozen_schema() -> None:
    for schema_name in (
        "platform_physical_core_v1",
        "platform_physical_compact_v1",
    ):
        schema, descriptors = _descriptors(schema_name)
        assert set(descriptors) == set(SUPPORTED_EMBODIMENTS)
        for configuration, descriptor in descriptors.items():
            assert descriptor.configuration == configuration
            assert descriptor.schema_sha256 == schema.schema_sha256
            assert descriptor.values.shape == (schema.dimension,)
            assert descriptor.values.flags.writeable is False
            assert np.isfinite(descriptor.values).all()
            with pytest.raises(ValueError):
                descriptor.values[0] = 0.0


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (lambda c: c.__setitem__("mass_kg", 0.0), "physical_value_invalid"),
        (lambda c: c.__setitem__("volume_m3", float("nan")), "physical_value_invalid"),
        (lambda c: c.__setitem__("allocation_mode", "learned-name"), "allocation_mode_unknown"),
        (lambda c: c.pop("drag_multiplier"), "physical_field_set_mismatch"),
        (lambda c: c.__setitem__("configuration_sha256", "0" * 64), "configuration_identity_forbidden"),
    ),
)
def test_descriptor_rejects_invalid_unknown_or_identity_derived_facts(
    mutation, reason: str
) -> None:
    context = declared_platform_context_v2("base")
    mutation(context)
    with pytest.raises(ValueError, match=reason):
        build_platform_descriptor_v2(
            [context], schema=select_platform_feature_schema_v2("platform_physical_core_v1")
        )


def test_descriptor_rejects_per_row_platform_drift() -> None:
    first = declared_platform_context_v2("base")
    second = deepcopy(first)
    second["mass_kg"] *= 1.01
    with pytest.raises(ValueError, match="platform_context_drift"):
        build_platform_descriptor_v2(
            [first, second],
            schema=select_platform_feature_schema_v2("platform_physical_core_v1"),
        )


def test_descriptor_accepts_dataset_frozen_mapping_context() -> None:
    """Model-facing datasets expose read-only mappings, not mutable dicts."""

    def freeze(value):
        if isinstance(value, dict):
            return MappingProxyType({key: freeze(item) for key, item in value.items()})
        if isinstance(value, list):
            return tuple(freeze(item) for item in value)
        return value

    schema = select_platform_feature_schema_v2("platform_physical_compact_v1")
    context = freeze(declared_platform_context_v2("base"))

    descriptor = build_platform_descriptor_v2([context], schema=schema)

    assert descriptor.configuration == "base"
    assert descriptor.values.shape == (schema.dimension,)


def test_normalizer_fits_exact_seven_sources_and_binds_fold_provenance() -> None:
    schema, descriptors = _descriptors()
    fold = _fold("base")
    source_descriptors = {
        configuration: descriptors[configuration]
        for configuration in fold.source_configurations
    }
    normalizer = fit_platform_feature_normalizer_v2(
        source_descriptors,
        fold=fold,
        schema=schema,
    )

    assert isinstance(normalizer, PlatformFeatureNormalizerV2)
    assert normalizer.fold_id == fold.fold_id
    assert normalizer.holdout_configuration == "base"
    assert normalizer.source_configurations == fold.source_configurations
    assert normalizer.source_episode_sha256s == fold.source_episode_sha256s
    assert normalizer.feature_schema_sha256 == schema.schema_sha256
    assert normalizer.mean.flags.writeable is False
    assert normalizer.scale.flags.writeable is False
    assert np.all(normalizer.scale > 0.0)
    assert normalizer.zero_scale_rule == "unit_scale"
    assert normalizer.normalizer_sha256 == hashlib.sha256(
        (json.dumps(normalizer.payload_without_hash(), allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()

    for configuration in SUPPORTED_EMBODIMENTS:
        transformed = normalizer.transform(descriptors[configuration])
        assert transformed.shape == (schema.dimension,)
        assert transformed.flags.writeable is False
        assert np.isfinite(transformed).all()


def test_normalizer_rejects_heldout_missing_source_and_different_fold_reuse() -> None:
    schema, descriptors = _descriptors()
    fold = _fold("base")
    exact = {
        configuration: descriptors[configuration]
        for configuration in fold.source_configurations
    }
    with pytest.raises(ValueError, match="heldout_normalization_leakage"):
        fit_platform_feature_normalizer_v2(
            {**exact, "base": descriptors["base"]}, fold=fold, schema=schema
        )
    missing = dict(exact)
    missing.pop(fold.source_configurations[0])
    with pytest.raises(ValueError, match="normalizer_source_set_mismatch"):
        fit_platform_feature_normalizer_v2(missing, fold=fold, schema=schema)

    normalizer = fit_platform_feature_normalizer_v2(exact, fold=fold, schema=schema)
    with pytest.raises(ValueError, match="normalizer_fold_mismatch"):
        normalizer.require_fold(_fold("uuv6"))
    with pytest.raises(ValueError, match="normalizer_fold_mismatch"):
        normalizer.require_fold(
            replace(
                fold,
                source_episode_sha256s=("0" * 64,) + fold.source_episode_sha256s[1:],
            )
        )


def test_platform_features_are_cold_and_protected_v1_phase6_phase7_paths_are_clean() -> None:
    script = """
import json
import sys
import koopman.platform_features_v2
import koopman.splits_v2
blocked = [name for name in sys.modules if name == 'torch' or name.startswith(('gymnasium', 'omni', 'isaaclab'))]
print(json.dumps(blocked))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []

    protected = (
        "koopman/model.py",
        "koopman/mpc.py",
        "koopman/normalization.py",
        "koopman/schema_v2.py",
        "source/results/koopman_phase6",
        "source/results/koopman_phase7",
    )
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--", *protected],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert diff.returncode == 0, diff.stdout + diff.stderr
    for relative_path in ("koopman/model.py", "koopman/mpc.py", "koopman/normalization.py"):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "platform_features_v2" not in source
        assert "PlatformFeatureNormalizerV2" not in source
