"""Exact-eight whole-episode LOCO manifests and opened-artifact audits."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, TypeVar

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.collection_v2 import (
    DatasetInventoryV2,
    EpisodeInventoryEntryV2,
    dataset_inventory_sha256_v2,
)
from koopman.evidence_v2 import (
    canonical_json_bytes,
    canonical_sha256,
    load_bounded_json,
)
from koopman.protocol_v2 import (
    main_role_intents_v2,
    validate_main_role_protocol_v1,
)


LOCO_SPLIT_MANIFEST_VERSION_V2 = "phase8-loco-split-manifest-v2"
_FOLD_FIELDS = frozenset(
    {
        "expert_fit_validation_episode_ids",
        "expert_test_episode_ids",
        "fold_id",
        "holdout_configuration",
        "inventory_sha256",
        "primary_heldout_test_episode_ids",
        "primary_source_episode_ids",
        "role_protocol_sha256",
        "sealed_heldout_digest",
        "source_configurations",
        "source_episode_sha256s",
    }
)
_SPLIT_FIELDS = frozenset(
    {
        "created_at",
        "folds",
        "inventory_sha256",
        "protocol_frozen_at",
        "role_protocol_sha256",
        "split_sha256",
        "split_version",
    }
)
_MAX_SPLIT_BYTES = 8 * 1024 * 1024
T = TypeVar("T")


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _exact_mapping(value: Any, fields: frozenset[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("type_invalid", path)
    if set(value) != fields:
        _fail("field_set_mismatch", path)
    return value


def _strings(value: Any, path: str) -> tuple[str, ...]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or any(not isinstance(item, str) or not item for item in value)
    ):
        _fail("type_invalid", path)
    return tuple(value)


def _timestamp(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("timestamp_invalid", path)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"timestamp_invalid:{path}") from exc
    if parsed.tzinfo != timezone.utc or parsed.microsecond != 0:
        _fail("timestamp_invalid", path)
    return parsed


@dataclass(frozen=True)
class LOCOFoldManifestV2:
    fold_id: str
    holdout_configuration: str
    source_configurations: tuple[str, ...]
    primary_source_episode_ids: tuple[str, ...]
    primary_heldout_test_episode_ids: tuple[str, ...]
    expert_fit_validation_episode_ids: tuple[str, ...]
    expert_test_episode_ids: tuple[str, ...]
    source_episode_sha256s: tuple[str, ...]
    sealed_heldout_digest: str
    inventory_sha256: str
    role_protocol_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "source_configurations",
            "primary_source_episode_ids",
            "primary_heldout_test_episode_ids",
            "expert_fit_validation_episode_ids",
            "expert_test_episode_ids",
            "source_episode_sha256s",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_fit_validation_episode_ids": list(
                self.expert_fit_validation_episode_ids
            ),
            "expert_test_episode_ids": list(self.expert_test_episode_ids),
            "fold_id": self.fold_id,
            "holdout_configuration": self.holdout_configuration,
            "inventory_sha256": self.inventory_sha256,
            "primary_heldout_test_episode_ids": list(
                self.primary_heldout_test_episode_ids
            ),
            "primary_source_episode_ids": list(self.primary_source_episode_ids),
            "role_protocol_sha256": self.role_protocol_sha256,
            "sealed_heldout_digest": self.sealed_heldout_digest,
            "source_configurations": list(self.source_configurations),
            "source_episode_sha256s": list(self.source_episode_sha256s),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LOCOFoldManifestV2":
        payload = _exact_mapping(value, _FOLD_FIELDS, "fold")
        return cls(
            fold_id=payload["fold_id"],
            holdout_configuration=payload["holdout_configuration"],
            source_configurations=_strings(
                payload["source_configurations"], "source_configurations"
            ),
            primary_source_episode_ids=_strings(
                payload["primary_source_episode_ids"],
                "primary_source_episode_ids",
            ),
            primary_heldout_test_episode_ids=_strings(
                payload["primary_heldout_test_episode_ids"],
                "primary_heldout_test_episode_ids",
            ),
            expert_fit_validation_episode_ids=_strings(
                payload["expert_fit_validation_episode_ids"],
                "expert_fit_validation_episode_ids",
            ),
            expert_test_episode_ids=_strings(
                payload["expert_test_episode_ids"], "expert_test_episode_ids"
            ),
            source_episode_sha256s=_strings(
                payload["source_episode_sha256s"], "source_episode_sha256s"
            ),
            sealed_heldout_digest=payload["sealed_heldout_digest"],
            inventory_sha256=payload["inventory_sha256"],
            role_protocol_sha256=payload["role_protocol_sha256"],
        )


def loco_split_sha256_v2(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("split_sha256", None)
    return canonical_sha256(payload)


@dataclass(frozen=True)
class LOCOSplitManifestV2:
    folds: tuple[LOCOFoldManifestV2, ...]
    inventory_sha256: str
    role_protocol_sha256: str
    protocol_frozen_at: str
    created_at: str
    split_sha256: str
    split_version: str = LOCO_SPLIT_MANIFEST_VERSION_V2

    def __post_init__(self) -> None:
        object.__setattr__(self, "folds", tuple(self.folds))

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "folds": [fold.to_dict() for fold in self.folds],
            "inventory_sha256": self.inventory_sha256,
            "protocol_frozen_at": self.protocol_frozen_at,
            "role_protocol_sha256": self.role_protocol_sha256,
            "split_sha256": self.split_sha256,
            "split_version": self.split_version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LOCOSplitManifestV2":
        payload = _exact_mapping(value, _SPLIT_FIELDS, "split_manifest")
        folds = payload["folds"]
        if isinstance(folds, (str, bytes)) or not isinstance(folds, Sequence):
            _fail("type_invalid", "folds")
        split = cls(
            folds=tuple(LOCOFoldManifestV2.from_dict(item) for item in folds),
            inventory_sha256=payload["inventory_sha256"],
            role_protocol_sha256=payload["role_protocol_sha256"],
            protocol_frozen_at=payload["protocol_frozen_at"],
            created_at=payload["created_at"],
            split_sha256=payload["split_sha256"],
            split_version=payload["split_version"],
        )
        if split.split_version != LOCO_SPLIT_MANIFEST_VERSION_V2:
            _fail("split_version_mismatch")
        if loco_split_sha256_v2(split.to_dict()) != split.split_sha256:
            _fail("split_hash_mismatch")
        return split


def _validate_inventory_protocol(
    inventory: DatasetInventoryV2, protocol: Mapping[str, Any]
) -> tuple[EpisodeInventoryEntryV2, ...]:
    validate_main_role_protocol_v1(protocol)
    protocol_sha256 = canonical_sha256(protocol)
    if inventory.role_protocol_sha256 != protocol_sha256:
        _fail("role_protocol_hash_mismatch")
    if dataset_inventory_sha256_v2(inventory.to_dict()) != inventory.inventory_sha256:
        _fail("inventory_hash_mismatch")
    intents = main_role_intents_v2(protocol)
    if tuple(entry.episode_id for entry in inventory.entries) != tuple(
        intent.episode_id for intent in intents
    ):
        if {entry.episode_id for entry in inventory.entries} == {
            intent.episode_id for intent in intents
        }:
            _fail("inventory_protocol_order_drift")
        _fail("inventory_set_mismatch")
    for entry, intent in zip(inventory.entries, intents, strict=True):
        for field_name in (
            "configuration",
            "episode_id",
            "role",
            "scenario",
            "seed",
            "transition_count",
            "transition_path",
            "manifest_path",
        ):
            if getattr(entry, field_name) != getattr(intent, field_name):
                _fail("role_assignment_drift", f"{entry.episode_id}:{field_name}")
        if entry.record_count != intent.transition_count:
            _fail("inventory_invariant_mismatch", f"{entry.episode_id}:record_count")
    return inventory.entries


def _derive_folds(
    inventory: DatasetInventoryV2, protocol: Mapping[str, Any]
) -> tuple[LOCOFoldManifestV2, ...]:
    entries = _validate_inventory_protocol(inventory, protocol)
    folds: list[LOCOFoldManifestV2] = []
    for holdout in SUPPORTED_EMBODIMENTS:
        sources = tuple(
            configuration
            for configuration in SUPPORTED_EMBODIMENTS
            if configuration != holdout
        )
        primary_source = tuple(
            entry
            for entry in entries
            if entry.configuration in sources
            and entry.role in {"fit", "validation"}
        )
        heldout_test = tuple(
            entry
            for entry in entries
            if entry.configuration == holdout and entry.role == "test"
        )
        expert_decision = tuple(
            entry
            for entry in entries
            if entry.configuration == holdout
            and entry.role in {"fit", "validation"}
        )
        heldout_all = tuple(
            entry for entry in entries if entry.configuration == holdout
        )
        sealed_digest = canonical_sha256(
            {
                "heldout_configuration": holdout,
                "sealed_entries": [
                    {
                        "episode_id": entry.episode_id,
                        "manifest_sha256": entry.manifest_sha256,
                        "role": entry.role,
                        "transition_sha256": entry.transition_sha256,
                    }
                    for entry in heldout_all
                ],
            }
        )
        folds.append(
            LOCOFoldManifestV2(
                fold_id=f"loco-holdout-{holdout}",
                holdout_configuration=holdout,
                source_configurations=sources,
                primary_source_episode_ids=tuple(
                    entry.episode_id for entry in primary_source
                ),
                primary_heldout_test_episode_ids=tuple(
                    entry.episode_id for entry in heldout_test
                ),
                expert_fit_validation_episode_ids=tuple(
                    entry.episode_id for entry in expert_decision
                ),
                expert_test_episode_ids=tuple(
                    entry.episode_id for entry in heldout_test
                ),
                source_episode_sha256s=tuple(
                    entry.transition_sha256 for entry in primary_source
                ),
                sealed_heldout_digest=sealed_digest,
                inventory_sha256=inventory.inventory_sha256,
                role_protocol_sha256=inventory.role_protocol_sha256,
            )
        )
    return tuple(folds)


def _validate_fold(
    fold: LOCOFoldManifestV2,
    inventory: DatasetInventoryV2,
    protocol: Mapping[str, Any],
) -> None:
    expected_folds = _derive_folds(inventory, protocol)
    expected = next(
        (
            item
            for item in expected_folds
            if item.holdout_configuration == fold.holdout_configuration
        ),
        None,
    )
    if expected is None:
        _fail("configuration_set_mismatch", fold.holdout_configuration)
    assert expected is not None
    if fold != expected:
        heldout_ids = {
            entry.episode_id
            for entry in inventory.entries
            if entry.configuration == fold.holdout_configuration
        }
        if set(fold.primary_source_episode_ids) & heldout_ids:
            _fail("heldout_design_leakage", fold.holdout_configuration)
        _fail("fold_manifest_drift", fold.fold_id)


def build_loco_split_manifest_v2(
    inventory: DatasetInventoryV2,
    protocol: Mapping[str, Any],
    *,
    created_at: str,
) -> LOCOSplitManifestV2:
    folds = _derive_folds(inventory, protocol)
    frozen_at = protocol["frozen_at"]
    if _timestamp(created_at, "created_at") < _timestamp(
        frozen_at, "protocol_frozen_at"
    ):
        _fail("timestamp_order_invalid")
    payload: dict[str, Any] = {
        "created_at": created_at,
        "folds": [fold.to_dict() for fold in folds],
        "inventory_sha256": inventory.inventory_sha256,
        "protocol_frozen_at": frozen_at,
        "role_protocol_sha256": inventory.role_protocol_sha256,
        "split_version": LOCO_SPLIT_MANIFEST_VERSION_V2,
    }
    payload["split_sha256"] = loco_split_sha256_v2(payload)
    split = LOCOSplitManifestV2.from_dict(payload)
    validate_loco_split_manifest_v2(split, inventory, protocol)
    return split


def validate_loco_split_manifest_v2(
    split: LOCOSplitManifestV2,
    inventory: DatasetInventoryV2,
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    if split.inventory_sha256 != inventory.inventory_sha256:
        _fail("inventory_hash_mismatch")
    protocol_sha256 = canonical_sha256(protocol)
    if split.role_protocol_sha256 != protocol_sha256:
        _fail("role_protocol_hash_mismatch")
    if split.protocol_frozen_at != protocol["frozen_at"]:
        _fail("timestamp_order_invalid", "protocol_frozen_at")
    if _timestamp(split.created_at, "created_at") < _timestamp(
        split.protocol_frozen_at, "protocol_frozen_at"
    ):
        _fail("timestamp_order_invalid")
    if loco_split_sha256_v2(split.to_dict()) != split.split_sha256:
        _fail("split_hash_mismatch")
    expected = _derive_folds(inventory, protocol)
    if len(split.folds) != len(SUPPORTED_EMBODIMENTS):
        _fail("fold_count_mismatch")
    if tuple(item.holdout_configuration for item in split.folds) != tuple(
        SUPPORTED_EMBODIMENTS
    ):
        _fail("configuration_set_mismatch")
    for actual, expected_fold in zip(split.folds, expected, strict=True):
        if actual != expected_fold:
            _validate_fold(actual, inventory, protocol)
    return {
        "validation_gate": "phase8_exact_eight_loco_valid",
        "fold_count": len(split.folds),
        "inventory_sha256": split.inventory_sha256,
        "split_sha256": split.split_sha256,
        "warnings": [],
    }


@dataclass(frozen=True)
class PrimaryLOCOViewV2:
    fold_id: str
    holdout_configuration: str
    source_configurations: tuple[str, ...]
    decision_episode_ids: tuple[str, ...]
    outer_test_episode_ids: tuple[str, ...]
    inventory_sha256: str
    selection_eligible: bool = True


@dataclass(frozen=True)
class ExpertLOCOViewV2:
    fold_id: str
    holdout_configuration: str
    decision_episode_ids: tuple[str, ...]
    test_episode_ids: tuple[str, ...]
    inventory_sha256: str
    selection_eligible: bool = False


def primary_view_for_fold_v2(
    fold: LOCOFoldManifestV2,
    inventory: DatasetInventoryV2,
    protocol: Mapping[str, Any],
) -> PrimaryLOCOViewV2:
    _validate_fold(fold, inventory, protocol)
    return PrimaryLOCOViewV2(
        fold_id=fold.fold_id,
        holdout_configuration=fold.holdout_configuration,
        source_configurations=fold.source_configurations,
        decision_episode_ids=fold.primary_source_episode_ids,
        outer_test_episode_ids=fold.primary_heldout_test_episode_ids,
        inventory_sha256=fold.inventory_sha256,
    )


def expert_view_for_fold_v2(
    fold: LOCOFoldManifestV2,
    inventory: DatasetInventoryV2,
    protocol: Mapping[str, Any],
) -> ExpertLOCOViewV2:
    _validate_fold(fold, inventory, protocol)
    return ExpertLOCOViewV2(
        fold_id=fold.fold_id,
        holdout_configuration=fold.holdout_configuration,
        decision_episode_ids=fold.expert_fit_validation_episode_ids,
        test_episode_ids=fold.expert_test_episode_ids,
        inventory_sha256=fold.inventory_sha256,
    )


def require_primary_view_v2(value: Any) -> PrimaryLOCOViewV2:
    if isinstance(value, ExpertLOCOViewV2):
        _fail("expert_promotion_forbidden")
    if not isinstance(value, PrimaryLOCOViewV2):
        _fail("primary_view_required")
    return value


@dataclass(frozen=True)
class OpenedArtifactRecordV2:
    episode_id: str
    configuration: str
    role: str
    transition_sha256: str
    access_kind: str = "episode_bytes"


@dataclass(frozen=True)
class PrimaryAccessAuditV2:
    fold_id: str
    holdout_configuration: str
    source_configurations: tuple[str, ...]
    inventory_sha256: str
    opened_artifacts: tuple[OpenedArtifactRecordV2, ...]


def load_primary_decision_view_v2(
    view: PrimaryLOCOViewV2,
    inventory: DatasetInventoryV2,
    opener: Callable[[EpisodeInventoryEntryV2], T],
) -> tuple[tuple[T, ...], PrimaryAccessAuditV2]:
    primary = require_primary_view_v2(view)
    if primary.inventory_sha256 != inventory.inventory_sha256:
        _fail("inventory_hash_mismatch")
    entries = {entry.episode_id: entry for entry in inventory.entries}
    loaded: list[T] = []
    records: list[OpenedArtifactRecordV2] = []
    for episode_id in primary.decision_episode_ids:
        entry = entries.get(episode_id)
        if entry is None:
            _fail("inventory_set_mismatch", episode_id)
        if (
            entry.configuration not in primary.source_configurations
            or entry.configuration == primary.holdout_configuration
            or entry.role not in {"fit", "validation"}
        ):
            _fail("heldout_design_leakage", episode_id)
        loaded.append(opener(entry))
        records.append(
            OpenedArtifactRecordV2(
                episode_id=entry.episode_id,
                configuration=entry.configuration,
                role=entry.role,
                transition_sha256=entry.transition_sha256,
            )
        )
    return tuple(loaded), PrimaryAccessAuditV2(
        fold_id=primary.fold_id,
        holdout_configuration=primary.holdout_configuration,
        source_configurations=primary.source_configurations,
        inventory_sha256=primary.inventory_sha256,
        opened_artifacts=tuple(records),
    )


def validate_primary_access_audit_v2(
    fold: LOCOFoldManifestV2, audit: PrimaryAccessAuditV2
) -> dict[str, Any]:
    if audit.fold_id != fold.fold_id or audit.inventory_sha256 != fold.inventory_sha256:
        _fail("fold_manifest_drift", "audit_binding")
    if audit.holdout_configuration != fold.holdout_configuration:
        _fail("heldout_design_leakage", "audit_holdout")
    if audit.source_configurations != fold.source_configurations:
        _fail("fold_manifest_drift", "audit_sources")
    if tuple(item.episode_id for item in audit.opened_artifacts) != (
        fold.primary_source_episode_ids
    ):
        _fail("heldout_design_leakage", "opened_episode_set")
    if tuple(item.transition_sha256 for item in audit.opened_artifacts) != (
        fold.source_episode_sha256s
    ):
        _fail("artifact_hash_mismatch", "opened_episode_hashes")
    if any(
        item.configuration == fold.holdout_configuration
        or item.configuration not in fold.source_configurations
        or item.role not in {"fit", "validation"}
        or item.access_kind != "episode_bytes"
        for item in audit.opened_artifacts
    ):
        _fail("heldout_design_leakage", "opened_artifacts")
    return {
        "validation_gate": "phase8_primary_access_audit_valid",
        "opened_count": len(audit.opened_artifacts),
        "source_configuration_count": len(fold.source_configurations),
        "warnings": [],
    }


def write_loco_split_manifest_v2(
    split: LOCOSplitManifestV2, path: str | Path
) -> None:
    target = Path(path)
    part = target.with_name(f"{target.name}.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or part.exists():
        _fail("artifact_exists", str(target if target.exists() else part))
    try:
        with part.open("xb") as stream:
            stream.write(canonical_json_bytes(split.to_dict()))
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            _fail("artifact_exists", str(target))
        os.replace(part, target)
    finally:
        if part.exists():
            part.unlink()


def read_loco_split_manifest_v2(
    path: str | Path,
    inventory: DatasetInventoryV2,
    protocol: Mapping[str, Any],
) -> LOCOSplitManifestV2:
    split = LOCOSplitManifestV2.from_dict(
        load_bounded_json(path, max_bytes=_MAX_SPLIT_BYTES)
    )
    validate_loco_split_manifest_v2(split, inventory, protocol)
    return split

