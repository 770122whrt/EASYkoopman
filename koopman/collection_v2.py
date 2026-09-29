"""Immutable multi-episode collections and actual-byte Phase 8 inventories."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any

import numpy as np

from koopman.dataset_v2 import KoopmanDatasetV2, load_koopman_episode_v2
from koopman.evidence_v2 import canonical_json_bytes, canonical_sha256, load_bounded_json
from koopman.schema_v2 import validate_episode_artifact_v2


DATASET_INVENTORY_VERSION_V1 = "phase8-dataset-inventory-v1"
LOCAL_ROLE_INTENT_VERSION_V1 = "phase8-local-role-intent-v1"
EPISODE_ROLES = ("fit", "validation", "test")
MAIN_DATASET_QUALIFICATION = "server_isaac_identification_dataset"
MAX_INVENTORY_BYTES = 8 * 1024 * 1024
MAX_INVENTORY_ENTRIES = 100_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_INTENT_FIELDS = frozenset(
    {
        "configuration",
        "episode_id",
        "manifest_path",
        "role",
        "scenario",
        "seed",
        "transition_count",
        "transition_path",
    }
)
_LOCAL_INTENT_FIELDS = frozenset(
    {"entries", "intent_version", "qualification_level"}
)
_ENTRY_FIELDS = frozenset(
    {
        "configuration",
        "episode_id",
        "evidence_level",
        "manifest_path",
        "manifest_sha256",
        "manifest_size_bytes",
        "platform_context_sha256",
        "record_count",
        "role",
        "scenario",
        "seed",
        "transition_count",
        "transition_path",
        "transition_sha256",
        "transition_size_bytes",
    }
)
_INVENTORY_FIELDS = frozenset(
    {
        "entries",
        "envelope_sha256",
        "inventory_sha256",
        "inventory_version",
        "qualification_level",
        "role_protocol_sha256",
        "runtime_sha256",
        "source_commit",
    }
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _exact_mapping(value: Any, fields: frozenset[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("type_invalid", path)
    actual = set(value)
    if actual != fields:
        missing = ",".join(sorted(fields - actual)) or "none"
        extra = ",".join(sorted(actual - fields)) or "none"
        _fail("field_set_mismatch", f"{path}:missing={missing};extra={extra}")
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("type_invalid", path)
    return value


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("type_invalid", path)
    if minimum is not None and value < minimum:
        _fail("value_invalid", path)
    return value


def _sha256(value: Any, path: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail("hash_invalid", path)
    return value


def _relative_path(value: Any, path: str) -> str:
    relative = _nonempty_string(value, path)
    pure = PurePosixPath(relative)
    if (
        "\\" in relative
        or pure.is_absolute()
        or pure.as_posix() != relative
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        _fail("reference_path_invalid", relative)
    return relative


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen: dict[str, Any] = {}
    for key, nested in value.items():
        if isinstance(nested, Mapping):
            frozen[str(key)] = _freeze_mapping(nested)
        elif isinstance(nested, list):
            frozen[str(key)] = tuple(nested)
        else:
            frozen[str(key)] = nested
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class EpisodeRoleIntentV2:
    configuration: str
    episode_id: str
    role: str
    scenario: str
    seed: int
    transition_count: int
    transition_path: str
    manifest_path: str

    def __post_init__(self) -> None:
        for name in ("configuration", "episode_id", "scenario"):
            object.__setattr__(self, name, _nonempty_string(getattr(self, name), name))
        if self.role not in EPISODE_ROLES:
            _fail("role_invalid", str(self.role))
        _integer(self.seed, "seed")
        _integer(self.transition_count, "transition_count", minimum=2)
        object.__setattr__(
            self,
            "transition_path",
            _relative_path(self.transition_path, "transition_path"),
        )
        object.__setattr__(
            self,
            "manifest_path",
            _relative_path(self.manifest_path, "manifest_path"),
        )
        if self.transition_path == self.manifest_path:
            _fail("duplicate_reference", self.transition_path)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EpisodeRoleIntentV2":
        payload = _exact_mapping(value, _INTENT_FIELDS, "intent_entry")
        return cls(**dict(payload))


def _validate_intents(
    values: Iterable[EpisodeRoleIntentV2],
) -> tuple[EpisodeRoleIntentV2, ...]:
    intents = tuple(values)
    if not intents:
        _fail("inventory_set_mismatch", "expected_episode_set_empty")
    episode_ids: set[str] = set()
    paths: set[str] = set()
    identities: set[tuple[str, str, str, int]] = set()
    for intent in intents:
        if not isinstance(intent, EpisodeRoleIntentV2):
            _fail("type_invalid", "intents")
        if intent.episode_id in episode_ids:
            _fail("duplicate_episode_id", intent.episode_id)
        episode_ids.add(intent.episode_id)
        identity = (intent.configuration, intent.role, intent.scenario, intent.seed)
        if identity in identities:
            _fail("duplicate_episode_identity", intent.episode_id)
        identities.add(identity)
        for relative in (intent.transition_path, intent.manifest_path):
            if relative in paths:
                _fail("duplicate_reference", relative)
            paths.add(relative)
    return intents


def load_episode_role_intents_v2(path: str | Path) -> tuple[EpisodeRoleIntentV2, ...]:
    """Load bounded local role intent used by contract fixtures and inventory tests."""
    payload = _exact_mapping(
        load_bounded_json(path, max_bytes=MAX_INVENTORY_BYTES),
        _LOCAL_INTENT_FIELDS,
        "role_intent",
    )
    if payload["intent_version"] != LOCAL_ROLE_INTENT_VERSION_V1:
        _fail("intent_version_mismatch")
    if payload["qualification_level"] != "local_contract":
        _fail("evidence_level_mismatch", "local_intent")
    entries = payload["entries"]
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        _fail("type_invalid", "entries")
    return _validate_intents(EpisodeRoleIntentV2.from_dict(item) for item in entries)


@dataclass(frozen=True)
class EpisodeInventoryEntryV2:
    configuration: str
    episode_id: str
    role: str
    scenario: str
    seed: int
    transition_count: int
    transition_path: str
    manifest_path: str
    transition_sha256: str
    manifest_sha256: str
    transition_size_bytes: int
    manifest_size_bytes: int
    record_count: int
    platform_context_sha256: str
    evidence_level: str

    def __post_init__(self) -> None:
        intent = EpisodeRoleIntentV2(
            configuration=self.configuration,
            episode_id=self.episode_id,
            role=self.role,
            scenario=self.scenario,
            seed=self.seed,
            transition_count=self.transition_count,
            transition_path=self.transition_path,
            manifest_path=self.manifest_path,
        )
        for name in (
            "configuration",
            "episode_id",
            "role",
            "scenario",
            "seed",
            "transition_count",
            "transition_path",
            "manifest_path",
        ):
            object.__setattr__(self, name, getattr(intent, name))
        _sha256(self.transition_sha256, "transition_sha256")
        _sha256(self.manifest_sha256, "manifest_sha256")
        _sha256(self.platform_context_sha256, "platform_context_sha256")
        _integer(self.transition_size_bytes, "transition_size_bytes", minimum=1)
        _integer(self.manifest_size_bytes, "manifest_size_bytes", minimum=1)
        _integer(self.record_count, "record_count", minimum=2)
        if self.evidence_level not in {"local_contract", "server_isaac_smoke"}:
            _fail("evidence_level_mismatch", self.evidence_level)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in sorted(_ENTRY_FIELDS)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EpisodeInventoryEntryV2":
        payload = _exact_mapping(value, _ENTRY_FIELDS, "inventory_entry")
        return cls(**dict(payload))


def dataset_inventory_sha256_v2(value: Mapping[str, Any]) -> str:
    """Hash an inventory payload without its self-referential digest field."""
    payload = dict(value)
    payload.pop("inventory_sha256", None)
    return canonical_sha256(payload)


@dataclass(frozen=True)
class DatasetInventoryV2:
    entries: tuple[EpisodeInventoryEntryV2, ...]
    role_protocol_sha256: str
    source_commit: str
    runtime_sha256: str
    envelope_sha256: str | None
    qualification_level: str
    inventory_sha256: str
    inventory_version: str = DATASET_INVENTORY_VERSION_V1

    def __post_init__(self) -> None:
        if self.inventory_version != DATASET_INVENTORY_VERSION_V1:
            _fail("inventory_version_mismatch")
        entries = tuple(self.entries)
        if not entries or any(not isinstance(item, EpisodeInventoryEntryV2) for item in entries):
            _fail("inventory_set_mismatch", "entries")
        _validate_intents(
            EpisodeRoleIntentV2(
                configuration=item.configuration,
                episode_id=item.episode_id,
                role=item.role,
                scenario=item.scenario,
                seed=item.seed,
                transition_count=item.transition_count,
                transition_path=item.transition_path,
                manifest_path=item.manifest_path,
            )
            for item in entries
        )
        object.__setattr__(self, "entries", entries)
        _sha256(self.role_protocol_sha256, "role_protocol_sha256")
        _sha256(self.runtime_sha256, "runtime_sha256")
        _sha256(self.envelope_sha256, "envelope_sha256", optional=True)
        _sha256(self.inventory_sha256, "inventory_sha256")
        if not isinstance(self.source_commit, str) or not _COMMIT_RE.fullmatch(
            self.source_commit
        ):
            _fail("source_commit_invalid")
        if self.qualification_level not in {
            "local_contract",
            MAIN_DATASET_QUALIFICATION,
        }:
            _fail("evidence_level_mismatch", self.qualification_level)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "envelope_sha256": self.envelope_sha256,
            "inventory_sha256": self.inventory_sha256,
            "inventory_version": self.inventory_version,
            "qualification_level": self.qualification_level,
            "role_protocol_sha256": self.role_protocol_sha256,
            "runtime_sha256": self.runtime_sha256,
            "source_commit": self.source_commit,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DatasetInventoryV2":
        payload = _exact_mapping(value, _INVENTORY_FIELDS, "dataset_inventory")
        entries = payload["entries"]
        if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
            _fail("type_invalid", "entries")
        inventory = cls(
            entries=tuple(EpisodeInventoryEntryV2.from_dict(item) for item in entries),
            role_protocol_sha256=payload["role_protocol_sha256"],
            source_commit=payload["source_commit"],
            runtime_sha256=payload["runtime_sha256"],
            envelope_sha256=payload["envelope_sha256"],
            qualification_level=payload["qualification_level"],
            inventory_sha256=payload["inventory_sha256"],
            inventory_version=payload["inventory_version"],
        )
        if dataset_inventory_sha256_v2(inventory.to_dict()) != inventory.inventory_sha256:
            _fail("inventory_hash_mismatch")
        return inventory


def _resolve_regular_file(root: Path, relative: str) -> Path:
    normalized = _relative_path(relative, "reference")
    resolved_root = root.resolve()
    candidate = root / PurePosixPath(normalized)
    if candidate.is_symlink() or not candidate.exists() or not candidate.is_file():
        _fail("artifact_not_regular_file", normalized)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        _fail("reference_path_invalid", normalized)
    return resolved


def _actual_artifact_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    resolved_root = root.resolve()
    for directory_name in ("episodes", "manifests"):
        directory = root / directory_name
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            _fail("artifact_not_regular_file", directory_name)
        for candidate in directory.rglob("*"):
            if candidate.is_file() or candidate.is_symlink():
                paths.add(candidate.absolute().relative_to(resolved_root).as_posix())
    return paths


def _assert_exact_artifact_set(
    root: Path, intents: Sequence[EpisodeRoleIntentV2]
) -> None:
    expected = {
        path
        for intent in intents
        for path in (intent.transition_path, intent.manifest_path)
    }
    actual = _actual_artifact_paths(root)
    if actual != expected:
        missing = ",".join(sorted(expected - actual)) or "none"
        extra = ",".join(sorted(actual - expected)) or "none"
        _fail("inventory_set_mismatch", f"missing={missing};extra={extra}")


def _manifest_payload(path: Path) -> Mapping[str, Any]:
    return load_bounded_json(path, max_bytes=1024 * 1024)


def _entry_from_bytes(root: Path, intent: EpisodeRoleIntentV2) -> EpisodeInventoryEntryV2:
    transition_path = _resolve_regular_file(root, intent.transition_path)
    manifest_path = _resolve_regular_file(root, intent.manifest_path)
    result = validate_episode_artifact_v2(transition_path, manifest_path)
    manifest = _manifest_payload(manifest_path)
    invariants = manifest["episode_invariants"]
    comparisons = {
        "configuration": (intent.configuration, result["configuration"]),
        "episode_id": (intent.episode_id, result["episode_id"]),
        "scenario": (intent.scenario, invariants.get("scenario")),
        "seed": (intent.seed, invariants.get("seed")),
        "transition_count": (intent.transition_count, result["record_count"]),
    }
    for field_name, (expected, actual) in comparisons.items():
        if expected != actual:
            reason = "role_assignment_drift" if field_name in {"scenario", "seed"} else "inventory_invariant_mismatch"
            _fail(reason, f"{intent.episode_id}:{field_name}")
    return EpisodeInventoryEntryV2(
        configuration=intent.configuration,
        episode_id=intent.episode_id,
        role=intent.role,
        scenario=intent.scenario,
        seed=intent.seed,
        transition_count=intent.transition_count,
        transition_path=intent.transition_path,
        manifest_path=intent.manifest_path,
        transition_sha256=hashlib.sha256(transition_path.read_bytes()).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        transition_size_bytes=transition_path.stat().st_size,
        manifest_size_bytes=manifest_path.stat().st_size,
        record_count=result["record_count"],
        platform_context_sha256=manifest["platform_context_sha256"],
        evidence_level=result["evidence_level"],
    )


def build_dataset_inventory_v2(
    root: str | Path,
    intents: Iterable[EpisodeRoleIntentV2],
    *,
    role_protocol_sha256: str,
    runtime_sha256: str,
    envelope_sha256: str | None,
    qualification_level: str,
    max_entries: int = MAX_INVENTORY_ENTRIES,
) -> DatasetInventoryV2:
    """Build post-collection facts from the exact expected artifact set."""
    collection_root = Path(root)
    if collection_root.is_symlink() or not collection_root.exists() or not collection_root.is_dir():
        _fail("artifact_not_regular_file", str(collection_root))
    _sha256(role_protocol_sha256, "role_protocol_sha256")
    _sha256(runtime_sha256, "runtime_sha256")
    _sha256(envelope_sha256, "envelope_sha256", optional=True)
    _integer(max_entries, "max_entries", minimum=1)
    expected = _validate_intents(intents)
    if len(expected) > max_entries:
        _fail("inventory_too_large", str(len(expected)))
    _assert_exact_artifact_set(collection_root, expected)
    entries = tuple(_entry_from_bytes(collection_root, intent) for intent in expected)
    source_commits = {
        str(_manifest_payload(_resolve_regular_file(collection_root, entry.manifest_path))["episode_invariants"]["source_commit"])
        for entry in entries
    }
    if len(source_commits) != 1:
        _fail("inventory_invariant_mismatch", "source_commit")
    if qualification_level == "local_contract":
        if any(entry.evidence_level != "local_contract" for entry in entries):
            _fail("evidence_level_mismatch", "local_contract")
    elif qualification_level == MAIN_DATASET_QUALIFICATION:
        if any(entry.evidence_level != "server_isaac_smoke" for entry in entries):
            _fail("evidence_level_mismatch", MAIN_DATASET_QUALIFICATION)
    else:
        _fail("evidence_level_mismatch", qualification_level)
    payload: dict[str, Any] = {
        "entries": [entry.to_dict() for entry in entries],
        "envelope_sha256": envelope_sha256,
        "inventory_version": DATASET_INVENTORY_VERSION_V1,
        "qualification_level": qualification_level,
        "role_protocol_sha256": role_protocol_sha256,
        "runtime_sha256": runtime_sha256,
        "source_commit": source_commits.pop(),
    }
    payload["inventory_sha256"] = dataset_inventory_sha256_v2(payload)
    return DatasetInventoryV2.from_dict(payload)


def validate_dataset_inventory_v2(
    inventory: DatasetInventoryV2,
    *,
    root: str | Path,
    intents: Iterable[EpisodeRoleIntentV2],
) -> dict[str, Any]:
    if not isinstance(inventory, DatasetInventoryV2):
        _fail("type_invalid", "inventory")
    if dataset_inventory_sha256_v2(inventory.to_dict()) != inventory.inventory_sha256:
        _fail("inventory_hash_mismatch")
    expected = _validate_intents(intents)
    actual_entries = {entry.episode_id: entry for entry in inventory.entries}
    if set(actual_entries) != {intent.episode_id for intent in expected}:
        _fail("inventory_set_mismatch", "episode_ids")
    collection_root = Path(root)
    _assert_exact_artifact_set(collection_root, expected)
    for intent in expected:
        entry = actual_entries[intent.episode_id]
        for field_name in (
            "configuration",
            "role",
            "scenario",
            "seed",
            "transition_count",
            "transition_path",
            "manifest_path",
        ):
            if getattr(entry, field_name) != getattr(intent, field_name):
                _fail("role_assignment_drift", f"{intent.episode_id}:{field_name}")
        transition_path = _resolve_regular_file(collection_root, entry.transition_path)
        manifest_path = _resolve_regular_file(collection_root, entry.manifest_path)
        if hashlib.sha256(transition_path.read_bytes()).hexdigest() != entry.transition_sha256:
            _fail("artifact_hash_mismatch", entry.transition_path)
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != entry.manifest_sha256:
            _fail("artifact_hash_mismatch", entry.manifest_path)
        if transition_path.stat().st_size != entry.transition_size_bytes:
            _fail("artifact_size_mismatch", entry.transition_path)
        if manifest_path.stat().st_size != entry.manifest_size_bytes:
            _fail("artifact_size_mismatch", entry.manifest_path)
        observed = _entry_from_bytes(collection_root, intent)
        for field_name in (
            "configuration",
            "episode_id",
            "scenario",
            "seed",
            "record_count",
            "platform_context_sha256",
            "evidence_level",
        ):
            if getattr(entry, field_name) != getattr(observed, field_name):
                _fail("inventory_invariant_mismatch", f"{intent.episode_id}:{field_name}")
        manifest_source = str(
            _manifest_payload(manifest_path)["episode_invariants"]["source_commit"]
        )
        if manifest_source != inventory.source_commit:
            _fail("inventory_invariant_mismatch", "source_commit")
    if inventory.qualification_level == "local_contract":
        if any(entry.evidence_level != "local_contract" for entry in inventory.entries):
            _fail("evidence_level_mismatch", "local_contract")
    elif inventory.qualification_level == MAIN_DATASET_QUALIFICATION:
        if any(entry.evidence_level != "server_isaac_smoke" for entry in inventory.entries):
            _fail("evidence_level_mismatch", MAIN_DATASET_QUALIFICATION)
    return {
        "validation_gate": "phase8_dataset_inventory_valid",
        "episode_count": len(inventory.entries),
        "inventory_sha256": inventory.inventory_sha256,
        "qualification_level": inventory.qualification_level,
        "warnings": [],
    }


def write_dataset_inventory_v2(
    inventory: DatasetInventoryV2, path: str | Path
) -> None:
    """Fsync a retained ``.part`` and atomically promote to a fresh target."""
    if not isinstance(inventory, DatasetInventoryV2):
        _fail("type_invalid", "inventory")
    target = Path(path)
    part = target.with_name(f"{target.name}.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or part.exists():
        _fail("artifact_exists", str(target if target.exists() else part))
    try:
        with part.open("xb") as stream:
            stream.write(canonical_json_bytes(inventory.to_dict()))
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            _fail("artifact_exists", str(target))
        os.replace(part, target)
    finally:
        if part.exists():
            part.unlink()


def load_dataset_inventory_v2(
    path: str | Path,
    *,
    root: str | Path,
    intents: Iterable[EpisodeRoleIntentV2],
    max_bytes: int = MAX_INVENTORY_BYTES,
) -> DatasetInventoryV2:
    inventory = DatasetInventoryV2.from_dict(
        load_bounded_json(path, max_bytes=max_bytes)
    )
    validate_dataset_inventory_v2(inventory, root=root, intents=intents)
    return inventory


@dataclass(frozen=True)
class CollectionEpisodeV2:
    episode_id: str
    configuration: str
    role: str
    scenario: str
    seed: int
    transition_sha256: str
    manifest_sha256: str
    dataset: KoopmanDatasetV2

    def __post_init__(self) -> None:
        if not isinstance(self.dataset, KoopmanDatasetV2):
            _fail("type_invalid", "dataset")
        if set(self.dataset.episode_ids) != {self.episode_id}:
            _fail("inventory_invariant_mismatch", "episode_id")
        if set(self.dataset.configurations) != {self.configuration}:
            _fail("inventory_invariant_mismatch", "configuration")
        if self.role not in EPISODE_ROLES:
            _fail("role_invalid", self.role)
        _sha256(self.transition_sha256, "transition_sha256")
        _sha256(self.manifest_sha256, "manifest_sha256")


@dataclass(frozen=True)
class EpisodeBoundaryV2:
    episode_id: str
    configuration: str
    role: str
    start: int
    stop: int


def _readonly_concat(values: Sequence[np.ndarray], width: int, name: str) -> np.ndarray:
    if not values:
        _fail("collection_selection_empty", name)
    result = np.concatenate(values, axis=0).astype(np.float64, copy=False)
    if result.ndim != 2 or result.shape[1] != width or not np.isfinite(result).all():
        _fail("dataset_shape_invalid", name)
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class CollectionRowViewV2:
    X: np.ndarray
    U: np.ndarray
    R: np.ndarray
    Y: np.ndarray
    boundaries: tuple[EpisodeBoundaryV2, ...]


@dataclass(frozen=True)
class KoopmanDatasetCollectionV2:
    episodes: tuple[CollectionEpisodeV2, ...]
    episode_ids: tuple[str, ...] = field(init=False)
    by_configuration: Mapping[str, tuple[str, ...]] = field(init=False)
    by_role: Mapping[str, tuple[str, ...]] = field(init=False)

    def __post_init__(self) -> None:
        episodes = tuple(self.episodes)
        if not episodes or any(not isinstance(item, CollectionEpisodeV2) for item in episodes):
            _fail("collection_empty")
        ids = tuple(item.episode_id for item in episodes)
        if len(set(ids)) != len(ids):
            _fail("duplicate_episode_id")
        configurations: dict[str, list[str]] = {}
        roles: dict[str, list[str]] = {}
        for episode in episodes:
            configurations.setdefault(episode.configuration, []).append(episode.episode_id)
            roles.setdefault(episode.role, []).append(episode.episode_id)
        object.__setattr__(self, "episodes", episodes)
        object.__setattr__(self, "episode_ids", ids)
        object.__setattr__(
            self,
            "by_configuration",
            MappingProxyType({key: tuple(value) for key, value in configurations.items()}),
        )
        object.__setattr__(
            self,
            "by_role",
            MappingProxyType({key: tuple(value) for key, value in roles.items()}),
        )

    def select_episodes(
        self,
        *,
        configurations: set[str] | frozenset[str] | None = None,
        roles: set[str] | frozenset[str] | None = None,
    ) -> tuple[CollectionEpisodeV2, ...]:
        if configurations is not None:
            unknown = set(configurations) - set(self.by_configuration)
            if unknown:
                _fail("configuration_unknown", ",".join(sorted(unknown)))
        if roles is not None:
            unknown_roles = set(roles) - set(EPISODE_ROLES)
            if unknown_roles:
                _fail("role_invalid", ",".join(sorted(unknown_roles)))
        selected = tuple(
            episode
            for episode in self.episodes
            if (configurations is None or episode.configuration in configurations)
            and (roles is None or episode.role in roles)
        )
        if not selected:
            _fail("collection_selection_empty")
        return selected

    def row_view(
        self,
        *,
        configurations: set[str] | frozenset[str] | None = None,
        roles: set[str] | frozenset[str] | None = None,
    ) -> CollectionRowViewV2:
        selected = self.select_episodes(configurations=configurations, roles=roles)
        boundaries: list[EpisodeBoundaryV2] = []
        cursor = 0
        for episode in selected:
            stop = cursor + episode.dataset.sample_count
            boundaries.append(
                EpisodeBoundaryV2(
                    episode_id=episode.episode_id,
                    configuration=episode.configuration,
                    role=episode.role,
                    start=cursor,
                    stop=stop,
                )
            )
            cursor = stop
        return CollectionRowViewV2(
            X=_readonly_concat([item.dataset.X for item in selected], 11, "X"),
            U=_readonly_concat([item.dataset.U for item in selected], 4, "U"),
            R=_readonly_concat([item.dataset.R for item in selected], 5, "R"),
            Y=_readonly_concat([item.dataset.Y for item in selected], 11, "Y"),
            boundaries=tuple(boundaries),
        )


def load_koopman_collection_v2(
    root: str | Path,
    inventory: DatasetInventoryV2,
    *,
    intents: Iterable[EpisodeRoleIntentV2],
) -> KoopmanDatasetCollectionV2:
    expected = _validate_intents(intents)
    validate_dataset_inventory_v2(inventory, root=root, intents=expected)
    collection_root = Path(root)
    episodes = tuple(
        CollectionEpisodeV2(
            episode_id=entry.episode_id,
            configuration=entry.configuration,
            role=entry.role,
            scenario=entry.scenario,
            seed=entry.seed,
            transition_sha256=entry.transition_sha256,
            manifest_sha256=entry.manifest_sha256,
            dataset=load_koopman_episode_v2(
                _resolve_regular_file(collection_root, entry.transition_path),
                _resolve_regular_file(collection_root, entry.manifest_path),
            ),
        )
        for entry in inventory.entries
    )
    return KoopmanDatasetCollectionV2(episodes=episodes)


def require_main_dataset_qualification_v2(
    *, artifact_origin_level: str, qualification_level: str
) -> None:
    """Reject Phase 7 smoke, Phase 8 pilot and local fixtures as main data."""
    if (
        artifact_origin_level != "server_isaac_smoke"
        or qualification_level != MAIN_DATASET_QUALIFICATION
    ):
        _fail(
            "evidence_level_mismatch",
            f"origin={artifact_origin_level};qualification={qualification_level}",
        )
