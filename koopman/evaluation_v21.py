"""Phase 8.1 post-freeze diagnostic, expert and test-access state machine."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Protocol

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.evidence_v2 import canonical_json_bytes, canonical_sha256
from koopman.loco_v21 import (
    PRIMARY_METRICS_V21,
    FrozenPrimaryV21,
    SourceCandidateLedgerV21,
)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


def _metric_map(value: Mapping[str, float]) -> Mapping[str, float]:
    if set(value) != set(PRIMARY_METRICS_V21):
        _fail("expert_metric_set_mismatch")
    result: dict[str, float] = {}
    for metric in PRIMARY_METRICS_V21:
        item = value[metric]
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            _fail("expert_metric_invalid", metric)
        item = float(item)
        if not math.isfinite(item) or item < 0.0:
            _fail("expert_metric_invalid", metric)
        result[metric] = item
    return MappingProxyType(result)


def _atomic_json(value: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    part = target.with_name(f"{target.name}.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or part.exists():
        _fail("artifact_exists")
    try:
        with part.open("xb") as stream:
            stream.write(canonical_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(part, target)
    finally:
        if part.exists():
            part.unlink()
    return target


def _atomic_bytes(payload: bytes, path: str | Path) -> Path:
    target = Path(path)
    part = target.with_name(f"{target.name}.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or part.exists() or not payload:
        _fail("expert_artifact_invalid")
    try:
        with part.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(part, target)
    finally:
        if part.exists():
            part.unlink()
    return target


_SHA256 = re.compile(r"[0-9a-f]{64}")
_SOURCE_COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class ProtocolEpisodeBindingV21:
    """One immutable protocol/inventory identity; it contains no episode bytes."""

    episode_id: str
    configuration: str
    role: str
    family_repetition: str
    transition_sha256: str
    transition_path: str
    manifest_path: str
    transition_count: int
    role_protocol_sha256: str

    def __post_init__(self) -> None:
        if (
            not self.episode_id
            or not self.configuration
            or self.role not in {"fit", "validation", "test"}
            or not self.family_repetition
            or not _SHA256.fullmatch(self.transition_sha256)
            or not _SHA256.fullmatch(self.role_protocol_sha256)
            or isinstance(self.transition_count, bool)
            or self.transition_count != 512
        ):
            _fail("protocol_episode_binding_invalid")
        for value in (self.transition_path, self.manifest_path):
            path = Path(value)
            if not value or path.is_absolute() or ".." in path.parts:
                _fail("protocol_episode_path_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "configuration": self.configuration,
            "episode_id": self.episode_id,
            "family_repetition": self.family_repetition,
            "manifest_path": self.manifest_path,
            "role": self.role,
            "role_protocol_sha256": self.role_protocol_sha256,
            "transition_count": self.transition_count,
            "transition_path": self.transition_path,
            "transition_sha256": self.transition_sha256,
        }


@dataclass(frozen=True)
class ProtocolEpisodeRegistryV21:
    """Exact 96-episode metadata binding; constructing it opens no episode bytes."""

    experiment_id: str
    role_protocol_sha256: str
    episodes: tuple[ProtocolEpisodeBindingV21, ...]
    artifact_origin_level: str
    inventory_version: str = "phase8.1-protocol-episode-inventory-v1"
    inventory_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        episodes = tuple(self.episodes)
        if (
            self.experiment_id != "phase8.1-main-identification-v1"
            or self.inventory_version != "phase8.1-protocol-episode-inventory-v1"
            or not _SHA256.fullmatch(self.role_protocol_sha256)
            or not isinstance(self.artifact_origin_level, str)
            or not self.artifact_origin_level
            or len(episodes) != 96
            or len({episode.episode_id for episode in episodes}) != 96
            or any(
                not isinstance(episode, ProtocolEpisodeBindingV21)
                or episode.role_protocol_sha256 != self.role_protocol_sha256
                for episode in episodes
            )
        ):
            _fail("protocol_inventory_episode_set_mismatch")
        for configuration in SUPPORTED_EMBODIMENTS:
            for role, expected_count in (("fit", 6), ("validation", 3), ("test", 3)):
                selected = self.for_configuration_role(configuration, role)
                if len(selected) != expected_count:
                    _fail("protocol_inventory_episode_set_mismatch")
        object.__setattr__(self, "episodes", episodes)
        object.__setattr__(
            self,
            "inventory_sha256",
            canonical_sha256(self.to_dict(include_sha256=False)),
        )

    def for_configuration_role(
        self, configuration: str, role: str
    ) -> tuple[ProtocolEpisodeBindingV21, ...]:
        return tuple(
            episode
            for episode in self.episodes
            if episode.configuration == configuration and episode.role == role
        )

    def source_non_test(
        self, heldout_configuration: str
    ) -> tuple[ProtocolEpisodeBindingV21, ...]:
        return tuple(
            episode
            for episode in self.episodes
            if episode.configuration != heldout_configuration
            and episode.role in {"fit", "validation"}
        )

    def all_non_test(self) -> tuple[ProtocolEpisodeBindingV21, ...]:
        return tuple(episode for episode in self.episodes if episode.role != "test")

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, Any]:
        value = {
            "episodes": [episode.to_dict() for episode in self.episodes],
            "experiment_id": self.experiment_id,
            "inventory_version": self.inventory_version,
            "role_protocol_sha256": self.role_protocol_sha256,
        }
        if include_sha256:
            value["inventory_sha256"] = self.inventory_sha256
        return value

    def expected_split_payload(self) -> dict[str, Any]:
        folds = []
        for heldout in SUPPORTED_EMBODIMENTS:
            sources = tuple(value for value in SUPPORTED_EMBODIMENTS if value != heldout)
            folds.append(
                {
                    "heldout_configuration": heldout,
                    "heldout_fit_episode_ids": [
                        value.episode_id
                        for value in self.for_configuration_role(heldout, "fit")
                    ],
                    "heldout_test_episode_ids": [
                        value.episode_id
                        for value in self.for_configuration_role(heldout, "test")
                    ],
                    "heldout_validation_episode_ids": [
                        value.episode_id
                        for value in self.for_configuration_role(heldout, "validation")
                    ],
                    "source_configurations": list(sources),
                    "source_fit_episode_ids": [
                        value.episode_id
                        for value in self.episodes
                        if value.configuration in sources and value.role == "fit"
                    ],
                    "source_validation_episode_ids": [
                        value.episode_id
                        for value in self.episodes
                        if value.configuration in sources and value.role == "validation"
                    ],
                }
            )
        return {
            "experiment_id": self.experiment_id,
            "folds": folds,
            "inventory_sha256": self.inventory_sha256,
            "role_protocol_sha256": self.role_protocol_sha256,
            "split_version": "phase8.1-exact-eight-loco-split-v1",
        }

    def validate_split_path(self, split_path: str | Path) -> None:
        try:
            payload = json.loads(Path(split_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("loco_split_invalid") from exc
        if payload != self.expected_split_payload():
            _fail("loco_split_protocol_binding_mismatch")


def load_protocol_episode_registry_v21(
    *,
    role_protocol_path: str | Path,
    inventory_path: str | Path,
) -> ProtocolEpisodeRegistryV21:
    """Validate protocol/inventory identity without touching transition files."""

    role_path = Path(role_protocol_path)
    inventory_file = Path(inventory_path)
    try:
        role_bytes = role_path.read_bytes()
        role = json.loads(role_bytes)
        inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("protocol_inventory_invalid") from exc
    from koopman.d23_approval_v21 import (
        EXPERIMENT_ID_V21,
        validate_role_protocol_proposal_v21,
    )

    validate_role_protocol_proposal_v21(role)
    role_sha256 = hashlib.sha256(role_bytes).hexdigest()
    if (
        not isinstance(inventory, Mapping)
        or set(inventory)
        != {
            "episodes",
            "experiment_id",
            "inventory_sha256",
            "inventory_version",
            "role_protocol_sha256",
        }
        or inventory.get("experiment_id") != EXPERIMENT_ID_V21
        or inventory.get("inventory_version")
        != "phase8.1-protocol-episode-inventory-v1"
        or inventory.get("role_protocol_sha256") != role_sha256
        or not isinstance(inventory.get("episodes"), list)
    ):
        _fail("protocol_inventory_episode_set_mismatch")
    inventory_without_hash = dict(inventory)
    supplied_inventory_sha256 = inventory_without_hash.pop("inventory_sha256")
    if supplied_inventory_sha256 != canonical_sha256(inventory_without_hash):
        _fail("protocol_inventory_hash_mismatch")
    protocol_entries = role["entries"]
    inventory_entries = inventory["episodes"]
    if len(protocol_entries) != 96 or len(inventory_entries) != 96:
        _fail("protocol_inventory_episode_set_mismatch")
    bindings: list[ProtocolEpisodeBindingV21] = []
    for protocol_entry, inventory_entry in zip(
        protocol_entries, inventory_entries, strict=True
    ):
        if not isinstance(inventory_entry, Mapping):
            _fail("protocol_inventory_episode_set_mismatch")
        expected_nonhash = {
            "configuration": protocol_entry["configuration"],
            "episode_id": protocol_entry["episode_id"],
            "family_repetition": (
                f'{protocol_entry["excitation_family"]}-r{protocol_entry["repetition"]}'
            ),
            "manifest_path": protocol_entry["manifest_path"],
            "role": protocol_entry["role"],
            "role_protocol_sha256": role_sha256,
            "transition_count": protocol_entry["transition_count"],
            "transition_path": protocol_entry["transition_path"],
        }
        if (
            set(inventory_entry) != set(expected_nonhash) | {"transition_sha256"}
            or any(inventory_entry.get(key) != value for key, value in expected_nonhash.items())
        ):
            _fail("protocol_inventory_episode_set_mismatch")
        bindings.append(
            ProtocolEpisodeBindingV21(
                **{key: inventory_entry[key] for key in inventory_entry}
            )
        )
    result = ProtocolEpisodeRegistryV21(
        experiment_id=EXPERIMENT_ID_V21,
        role_protocol_sha256=role_sha256,
        episodes=tuple(bindings),
        artifact_origin_level=str(role["artifact_origin_level"]),
    )
    if result.inventory_sha256 != supplied_inventory_sha256:
        _fail("protocol_inventory_hash_mismatch")
    return result


@dataclass(frozen=True)
class FormalFoldSourceInputsV21:
    """Source-only outputs consumed by the formal state-machine orchestrator."""

    expected_candidates: tuple[Any, ...]
    candidate_evaluations: tuple[Any, ...]
    source_transform: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected_candidates", tuple(self.expected_candidates))
        object.__setattr__(
            self, "candidate_evaluations", tuple(self.candidate_evaluations)
        )
        if (
            not self.expected_candidates
            or len(self.candidate_evaluations) != len(self.expected_candidates)
        ):
            _fail("formal_source_inputs_invalid")


class DescriptorDiagnosticTransformV21(Protocol):
    def diagnose_heldout_descriptor(
        self, descriptor: tuple[float, ...]
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class HeldoutDescriptorDiagnosticV21:
    heldout_configuration: str
    report: Mapping[str, Any]
    source_ledger_sha256: str
    primary_freeze_sha256: str
    selection_eligible: bool = False
    version: str = "phase8.1-heldout-descriptor-diagnostic-v1"
    diagnostic_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.heldout_configuration or self.selection_eligible is not False:
            _fail("heldout_diagnostic_invalid")
        object.__setattr__(self, "report", _deep_freeze(self.report))
        object.__setattr__(
            self, "diagnostic_sha256", canonical_sha256(self.to_dict(False))
        )

    def to_dict(self, include_sha256: bool = True) -> dict[str, Any]:
        value = {
            "heldout_configuration": self.heldout_configuration,
            "primary_freeze_sha256": self.primary_freeze_sha256,
            "report": _deep_thaw(self.report),
            "selection_eligible": self.selection_eligible,
            "source_ledger_sha256": self.source_ledger_sha256,
            "version": self.version,
        }
        if include_sha256:
            value["diagnostic_sha256"] = self.diagnostic_sha256
        return value


@dataclass(frozen=True)
class ExpertCandidateSpecV21:
    label: str
    observable_schema: str
    ridge: float
    normalization: str
    conditioning: str = "none"
    candidate_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.conditioning != "none":
            _fail("expert_conditioning_forbidden")
        if self.observable_schema not in {"so3_identity_v1", "so3_kinematic_v1"}:
            _fail("expert_observable_invalid")
        if self.normalization not in {"none", "standard_v1"}:
            _fail("expert_normalization_invalid")
        if not math.isfinite(float(self.ridge)) or self.ridge < 0.0:
            _fail("expert_ridge_invalid")
        object.__setattr__(self, "ridge", float(self.ridge))
        object.__setattr__(self, "candidate_id", canonical_sha256(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "conditioning": self.conditioning,
            "label": self.label,
            "normalization": self.normalization,
            "observable_schema": self.observable_schema,
            "ridge": self.ridge,
        }


@dataclass(frozen=True)
class ExpertEpisodeV21:
    episode_id: str
    configuration: str
    role: str
    payload: Any

    def __post_init__(self) -> None:
        if self.role not in {"fit", "validation"}:
            _fail("expert_episode_role_invalid")
        if not self.episode_id or not self.configuration:
            _fail("expert_episode_binding_invalid")


@dataclass(frozen=True)
class ExpertLedgerEntryV21:
    candidate: ExpertCandidateSpecV21
    status: str
    reason_code: str | None
    validation_score: float | None
    validation_metrics: Mapping[str, float]
    model_identity: str | None
    normalizer_identity: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "validation_metrics", MappingProxyType(dict(self.validation_metrics))
        )
        if self.status not in {"success", "failed"}:
            _fail("expert_status_invalid")
        if self.status == "success":
            if (
                self.reason_code is not None
                or self.validation_score is None
                or not self.model_identity
                or not self.normalizer_identity
            ):
                _fail("expert_outcome_invalid")
        elif self.reason_code is None or self.validation_score is not None:
            _fail("expert_outcome_invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict()
            | {"candidate_id": self.candidate.candidate_id},
            "model_identity": self.model_identity,
            "normalizer_identity": self.normalizer_identity,
            "reason_code": self.reason_code,
            "status": self.status,
            "validation_metrics": dict(self.validation_metrics),
            "validation_score": self.validation_score,
        }


@dataclass(frozen=True)
class ExpertFreezeV21:
    heldout_configuration: str
    ledger: tuple[ExpertLedgerEntryV21, ...]
    selected_candidate_id: str | None
    model_identity: str | None
    normalizer_identity: str | None
    model_artifact_name: str | None
    model_artifact_sha256: str | None
    validation_metrics: Mapping[str, float]
    status: str
    reason_code: str | None
    selection_eligible: bool = False
    nonpromoting: bool = True
    namespace: str = "diagnostic/heldout_expert_v21"
    version: str = "phase8.1-heldout-expert-freeze-v1"
    expert_freeze_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ledger", tuple(self.ledger))
        object.__setattr__(
            self, "validation_metrics", MappingProxyType(dict(self.validation_metrics))
        )
        if self.selection_eligible is not False or self.nonpromoting is not True:
            _fail("expert_promotion_forbidden")
        if self.status == "success":
            if (
                self.reason_code is not None
                or not self.selected_candidate_id
                or not self.model_identity
                or not self.normalizer_identity
                or self.model_artifact_name != "selected_model.json"
                or not isinstance(self.model_artifact_sha256, str)
                or not _SHA256.fullmatch(self.model_artifact_sha256)
            ):
                _fail("expert_freeze_invalid")
        elif self.status == "failed":
            if (
                not self.reason_code
                or self.selected_candidate_id is not None
                or self.model_identity is not None
                or self.normalizer_identity is not None
                or self.model_artifact_name is not None
                or self.model_artifact_sha256 is not None
            ):
                _fail("expert_freeze_invalid")
        else:
            _fail("expert_freeze_invalid")
        object.__setattr__(
            self, "expert_freeze_sha256", canonical_sha256(self.to_dict(False))
        )

    def to_dict(self, include_sha256: bool = True) -> dict[str, Any]:
        value = {
            "heldout_configuration": self.heldout_configuration,
            "ledger": [entry.to_dict() for entry in self.ledger],
            "model_identity": self.model_identity,
            "model_artifact_name": self.model_artifact_name,
            "model_artifact_sha256": self.model_artifact_sha256,
            "namespace": self.namespace,
            "nonpromoting": self.nonpromoting,
            "normalizer_identity": self.normalizer_identity,
            "reason_code": self.reason_code,
            "selected_candidate_id": self.selected_candidate_id,
            "selection_eligible": self.selection_eligible,
            "status": self.status,
            "validation_metrics": dict(self.validation_metrics),
            "version": self.version,
        }
        if include_sha256:
            value["expert_freeze_sha256"] = self.expert_freeze_sha256
        return value


def validate_expert_artifact_v21(
    freeze: ExpertFreezeV21 | Mapping[str, Any],
    *,
    artifact_path: str | Path,
    loader: Callable[[bytes], Any],
    identity_reader: Callable[[Any], tuple[str, str]],
) -> Any:
    value = freeze.to_dict() if isinstance(freeze, ExpertFreezeV21) else freeze
    if value.get("status") != "success":
        _fail("expert_artifact_status_invalid")
    path = Path(artifact_path)
    if path.name != value.get("model_artifact_name") or not path.is_file():
        _fail("expert_artifact_missing")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != value.get("model_artifact_sha256"):
        _fail("expert_artifact_hash_mismatch")
    try:
        loaded = loader(payload)
        model_identity, normalizer_identity = identity_reader(loaded)
    except Exception as exc:
        raise ValueError("expert_artifact_roundtrip_failed") from exc
    if (
        model_identity != value.get("model_identity")
        or normalizer_identity != value.get("normalizer_identity")
    ):
        _fail("expert_artifact_identity_mismatch")
    return loaded


@dataclass(frozen=True)
class PrimaryTestTokenV21:
    heldout_configuration: str
    test_episode_ids: tuple[str, ...]
    primary_freeze_sha256: str
    diagnostic_sha256: str
    expert_freeze_sha256: str
    test_transition_sha256s: tuple[str, ...]
    test_family_repetitions: tuple[str, ...]
    role_protocol_sha256: str
    token_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "test_episode_ids", tuple(self.test_episode_ids))
        object.__setattr__(
            self, "test_transition_sha256s", tuple(self.test_transition_sha256s)
        )
        object.__setattr__(
            self, "test_family_repetitions", tuple(self.test_family_repetitions)
        )
        if (
            len(self.test_episode_ids) != 3
            or len(set(self.test_episode_ids)) != 3
            or len(self.test_transition_sha256s) != 3
            or any(not _SHA256.fullmatch(value) for value in self.test_transition_sha256s)
            or len(self.test_family_repetitions) != 3
            or len(set(self.test_family_repetitions)) != 3
            or not _SHA256.fullmatch(self.role_protocol_sha256)
        ):
            _fail("test_episode_set_invalid")
        object.__setattr__(
            self,
            "token_sha256",
            canonical_sha256(
                {
                    "diagnostic_sha256": self.diagnostic_sha256,
                    "expert_freeze_sha256": self.expert_freeze_sha256,
                    "heldout_configuration": self.heldout_configuration,
                    "primary_freeze_sha256": self.primary_freeze_sha256,
                    "test_episode_ids": list(self.test_episode_ids),
                    "test_family_repetitions": list(self.test_family_repetitions),
                    "test_transition_sha256s": list(self.test_transition_sha256s),
                    "role_protocol_sha256": self.role_protocol_sha256,
                }
            ),
        )

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, Any]:
        value = {
            "diagnostic_sha256": self.diagnostic_sha256,
            "expert_freeze_sha256": self.expert_freeze_sha256,
            "heldout_configuration": self.heldout_configuration,
            "primary_freeze_sha256": self.primary_freeze_sha256,
            "role_protocol_sha256": self.role_protocol_sha256,
            "test_episode_ids": list(self.test_episode_ids),
            "test_family_repetitions": list(self.test_family_repetitions),
            "test_transition_sha256s": list(self.test_transition_sha256s),
        }
        if include_sha256:
            value["token_sha256"] = self.token_sha256
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PrimaryTestTokenV21":
        expected = {
            "diagnostic_sha256",
            "expert_freeze_sha256",
            "heldout_configuration",
            "primary_freeze_sha256",
            "role_protocol_sha256",
            "test_episode_ids",
            "test_family_repetitions",
            "test_transition_sha256s",
            "token_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            _fail("test_access_token_invalid")
        result = cls(
            heldout_configuration=str(value["heldout_configuration"]),
            test_episode_ids=tuple(value["test_episode_ids"]),
            primary_freeze_sha256=str(value["primary_freeze_sha256"]),
            diagnostic_sha256=str(value["diagnostic_sha256"]),
            expert_freeze_sha256=str(value["expert_freeze_sha256"]),
            test_transition_sha256s=tuple(value["test_transition_sha256s"]),
            test_family_repetitions=tuple(value["test_family_repetitions"]),
            role_protocol_sha256=str(value["role_protocol_sha256"]),
        )
        if value["token_sha256"] != result.token_sha256:
            _fail("test_access_token_invalid")
        return result


class FoldEvaluationSessionV21:
    """Enforce the only approved post-primary-freeze transition order."""

    def __init__(
        self,
        heldout_configuration: str,
        source_ledger: SourceCandidateLedgerV21,
        primary_freeze: FrozenPrimaryV21,
        *,
        test_episode_bindings: Sequence[ProtocolEpisodeBindingV21],
        role_protocol_sha256: str,
    ) -> None:
        bindings = tuple(test_episode_bindings)
        if (
            not heldout_configuration
            or source_ledger.ledger_sha256 != primary_freeze.ledger_sha256
            or dict(source_ledger.selected_candidates)
            != dict(primary_freeze.selected_candidates)
            or not _SHA256.fullmatch(role_protocol_sha256)
            or len(bindings) != 3
            or len({binding.episode_id for binding in bindings}) != 3
            or len({binding.family_repetition for binding in bindings}) != 3
            or any(
                not isinstance(binding, ProtocolEpisodeBindingV21)
                or binding.configuration != heldout_configuration
                or binding.role != "test"
                or binding.role_protocol_sha256 != role_protocol_sha256
                for binding in bindings
            )
        ):
            _fail(
                "registered_test_episode_set_invalid"
                if bindings
                else "evaluation_freeze_binding_invalid"
            )
        self.heldout_configuration = heldout_configuration
        self.source_ledger = source_ledger
        self.primary_freeze = primary_freeze
        self.test_episode_bindings = bindings
        self.role_protocol_sha256 = role_protocol_sha256
        self._state = "PRIMARY_FROZEN"
        self._diagnostic: HeldoutDescriptorDiagnosticV21 | None = None
        self._expert: ExpertFreezeV21 | None = None
        self._token: PrimaryTestTokenV21 | None = None
        self._opened: tuple[Any, ...] = ()

    @property
    def state(self) -> str:
        return self._state

    def generate_heldout_descriptor_diagnostic(
        self,
        *,
        source_transform: Any,
        heldout_descriptor: Any,
        output_path: str | Path | None = None,
    ) -> HeldoutDescriptorDiagnosticV21:
        if self._state != "PRIMARY_FROZEN":
            _fail("diagnostic_order_invalid")
        if hasattr(source_transform, "diagnose_heldout_descriptor"):
            descriptor = tuple(float(value) for value in heldout_descriptor)
            if not descriptor or any(not math.isfinite(value) for value in descriptor):
                _fail("heldout_descriptor_invalid")
            report = source_transform.diagnose_heldout_descriptor(descriptor)
        else:
            from koopman.platform_features_v21 import (
                heldout_descriptor_diagnostic_v21,
            )

            report = heldout_descriptor_diagnostic_v21(
                source_transform, heldout_descriptor
            )
        if not isinstance(report, Mapping):
            _fail("heldout_diagnostic_report_invalid")
        diagnostic = HeldoutDescriptorDiagnosticV21(
            heldout_configuration=self.heldout_configuration,
            report=report,
            source_ledger_sha256=self.source_ledger.ledger_sha256,
            primary_freeze_sha256=self.primary_freeze.freeze_sha256,
        )
        if output_path is not None:
            _atomic_json(diagnostic.to_dict(), output_path)
        self._diagnostic = diagnostic
        self._state = "HELDOUT_DIAGNOSTIC_GENERATED"
        return diagnostic

    def select_and_freeze_expert(
        self,
        *,
        candidates: Sequence[ExpertCandidateSpecV21],
        fit_episodes: Sequence[ExpertEpisodeV21],
        validation_episodes: Sequence[ExpertEpisodeV21],
        fitter: Callable[[ExpertCandidateSpecV21, tuple[Any, ...]], Any],
        evaluator: Callable[[Any, tuple[Any, ...]], tuple[float, Mapping[str, float]]],
        artifact_path: str | Path,
        serializer: Callable[[Any], bytes],
        loader: Callable[[bytes], Any],
        identity_reader: Callable[[Any], tuple[str, str]],
    ) -> ExpertFreezeV21:
        if self._state != "HELDOUT_DIAGNOSTIC_GENERATED":
            _fail("expert_order_invalid")
        candidate_set = tuple(candidates)
        if not candidate_set or len({value.candidate_id for value in candidate_set}) != len(
            candidate_set
        ):
            _fail("expert_candidate_set_invalid")
        fit_set = tuple(fit_episodes)
        validation_set = tuple(validation_episodes)
        if not fit_set or not validation_set:
            _fail("expert_episode_set_invalid")
        for expected_role, episodes in (("fit", fit_set), ("validation", validation_set)):
            if any(
                episode.configuration != self.heldout_configuration
                or episode.role != expected_role
                for episode in episodes
            ):
                _fail("expert_episode_binding_invalid")
        fit_payloads = tuple(episode.payload for episode in fit_set)
        validation_payloads = tuple(episode.payload for episode in validation_set)
        entries: list[ExpertLedgerEntryV21] = []
        fitted_by_id: dict[str, Any] = {}
        for candidate in candidate_set:
            try:
                fitted = fitter(candidate, fit_payloads)
                if not isinstance(fitted, Mapping):
                    _fail("expert_fitted_model_invalid")
                model_identity = fitted.get("model_identity")
                normalizer_identity = fitted.get("normalizer_identity")
                if not isinstance(model_identity, str) or not isinstance(
                    normalizer_identity, str
                ):
                    _fail("expert_fitted_model_invalid")
                score, metrics = evaluator(fitted, validation_payloads)
                score = float(score)
                if not math.isfinite(score):
                    _fail("expert_validation_score_invalid")
                frozen_metrics = _metric_map(metrics)
                entries.append(
                    ExpertLedgerEntryV21(
                        candidate,
                        "success",
                        None,
                        score,
                        frozen_metrics,
                        model_identity,
                        normalizer_identity,
                    )
                )
                fitted_by_id[candidate.candidate_id] = fitted
            except Exception as error:  # each failed candidate remains in the ledger
                entries.append(
                    ExpertLedgerEntryV21(
                        candidate,
                        "failed",
                        f"expert_candidate_failed:{type(error).__name__}",
                        None,
                        {},
                        None,
                        None,
                    )
                )
        successful = [entry for entry in entries if entry.status == "success"]
        if successful:
            selected = min(
                successful,
                key=lambda entry: (
                    float(entry.validation_score),
                    candidate_set.index(entry.candidate),
                    entry.candidate.candidate_id,
                ),
            )
            selected_fitted = fitted_by_id[selected.candidate.candidate_id]
            serialized = serializer(selected_fitted)
            if not isinstance(serialized, bytes):
                _fail("expert_artifact_serialization_invalid")
            artifact = _atomic_bytes(serialized, artifact_path)
            artifact_sha256 = hashlib.sha256(serialized).hexdigest()
            try:
                loaded = loader(serialized)
                roundtrip_model_identity, roundtrip_normalizer_identity = (
                    identity_reader(loaded)
                )
            except Exception as exc:
                raise ValueError("expert_artifact_roundtrip_failed") from exc
            if (
                roundtrip_model_identity != selected.model_identity
                or roundtrip_normalizer_identity != selected.normalizer_identity
            ):
                _fail("expert_artifact_identity_mismatch")
            expert = ExpertFreezeV21(
                heldout_configuration=self.heldout_configuration,
                ledger=tuple(entries),
                selected_candidate_id=selected.candidate.candidate_id,
                model_identity=selected.model_identity,
                normalizer_identity=selected.normalizer_identity,
                model_artifact_name=artifact.name,
                model_artifact_sha256=artifact_sha256,
                validation_metrics=selected.validation_metrics,
                status="success",
                reason_code=None,
            )
            validate_expert_artifact_v21(
                expert,
                artifact_path=artifact,
                loader=loader,
                identity_reader=identity_reader,
            )
        else:
            if Path(artifact_path).exists():
                _fail("expert_artifact_invalid")
            expert = ExpertFreezeV21(
                heldout_configuration=self.heldout_configuration,
                ledger=tuple(entries),
                selected_candidate_id=None,
                model_identity=None,
                normalizer_identity=None,
                model_artifact_name=None,
                model_artifact_sha256=None,
                validation_metrics={},
                status="failed",
                reason_code="expert_candidate_set_failed",
            )
        self._expert = expert
        self._state = "EXPERT_FROZEN"
        return expert

    def authorize_primary_test(self) -> PrimaryTestTokenV21:
        if self._state != "EXPERT_FROZEN" or self._diagnostic is None or self._expert is None:
            _fail("test_authorization_order_invalid")
        token = PrimaryTestTokenV21(
            heldout_configuration=self.heldout_configuration,
            test_episode_ids=tuple(
                binding.episode_id for binding in self.test_episode_bindings
            ),
            primary_freeze_sha256=self.primary_freeze.freeze_sha256,
            diagnostic_sha256=self._diagnostic.diagnostic_sha256,
            expert_freeze_sha256=self._expert.expert_freeze_sha256,
            test_transition_sha256s=tuple(
                binding.transition_sha256 for binding in self.test_episode_bindings
            ),
            test_family_repetitions=tuple(
                binding.family_repetition for binding in self.test_episode_bindings
            ),
            role_protocol_sha256=self.role_protocol_sha256,
        )
        self._token = token
        self._state = "TEST_AUTHORIZED"
        return token

    def open_primary_test(
        self,
        access_token: PrimaryTestTokenV21,
        *,
        opener: Callable[[ProtocolEpisodeBindingV21], Any],
    ) -> tuple[Any, ...]:
        if self._state != "TEST_AUTHORIZED":
            _fail("test_open_order_invalid")
        if (
            not isinstance(access_token, PrimaryTestTokenV21)
            or self._token is None
            or access_token.token_sha256 != self._token.token_sha256
            or access_token.primary_freeze_sha256 != self.primary_freeze.freeze_sha256
            or access_token.test_episode_ids
            != tuple(binding.episode_id for binding in self.test_episode_bindings)
            or access_token.test_transition_sha256s
            != tuple(
                binding.transition_sha256 for binding in self.test_episode_bindings
            )
            or access_token.test_family_repetitions
            != tuple(
                binding.family_repetition for binding in self.test_episode_bindings
            )
            or access_token.role_protocol_sha256 != self.role_protocol_sha256
        ):
            _fail("test_access_token_invalid")
        opened = tuple(opener(binding) for binding in self.test_episode_bindings)
        self._opened = opened
        self._state = "TEST_OPENED"
        return opened


def _metrics_rollout(model: Any, episode: Any, **kwargs: Any) -> Any:
    from koopman.metrics_v21 import rollout_episode_v21

    return rollout_episode_v21(model, episode, **kwargs)


class SharedRolloutEvaluatorV21:
    """One injected rollout seam for source, expert and held-out roles."""

    def __init__(self, rollout: Callable[..., Any] = _metrics_rollout) -> None:
        self._rollout = rollout

    def evaluate(
        self,
        model: Any,
        episodes: Sequence[Any],
        **rollout_kwargs: Any,
    ) -> tuple[Any, ...]:
        return tuple(
            self._rollout(model, episode, **rollout_kwargs) for episode in episodes
        )


class _PersistenceIncrementModelV21:
    def predict_increment(
        self,
        state: Any,
        actuator_memory: Any,
        control: Any,
        *,
        platform_score: Any | None = None,
    ) -> Any:
        import numpy as np

        del actuator_memory, control
        if platform_score is not None:
            _fail("platform_features_forbidden")
        states = np.asarray(state)
        shape = (10,) if states.ndim == 1 else (states.shape[0], 10)
        return np.zeros(shape, dtype=np.float64)


class DatasetFormalLocoBackendV21:
    """First-party filesystem backend for the authorized formal orchestrator.

    The runner owns every role binding and access transition.  This backend only
    receives the exact non-test or post-authorization bindings appropriate to
    the current state.
    """

    def __init__(
        self,
        *,
        dataset_root: str | Path,
        analysis_policy_path: str | Path,
        expected_source_commit: str,
        expected_evidence_level: str,
    ) -> None:
        root = Path(dataset_root).resolve()
        if not root.is_dir():
            _fail("dataset_root_invalid")
        if not _SOURCE_COMMIT.fullmatch(str(expected_source_commit)):
            _fail("expected_source_commit_invalid")
        if not isinstance(expected_evidence_level, str) or not expected_evidence_level:
            _fail("expected_evidence_level_invalid")
        try:
            policy = json.loads(Path(analysis_policy_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("analysis_policy_invalid") from exc
        from koopman.d23_approval_v21 import validate_analysis_policy_proposal_v21

        validate_analysis_policy_proposal_v21(policy)
        self.dataset_root = root
        self.analysis_policy = policy
        self.expected_source_commit = str(expected_source_commit)
        self.expected_evidence_level = expected_evidence_level
        self._cache: dict[str, Any] = {}
        self._fold_contexts: dict[str, dict[str, Any]] = {}

    def _path(self, relative: str) -> Path:
        path = (self.dataset_root / relative).resolve()
        if not path.is_relative_to(self.dataset_root):
            _fail("dataset_path_escape")
        return path

    def open_episode(self, binding: ProtocolEpisodeBindingV21) -> Any:
        from koopman.dataset_v21 import load_koopman_episode_v21
        from koopman.schema_v21 import validate_episode_artifact_v21

        cached = self._cache.get(binding.episode_id)
        if cached is not None:
            return cached
        transition = self._path(binding.transition_path)
        manifest = self._path(binding.manifest_path)
        summary = validate_episode_artifact_v21(transition, manifest)
        if (
            summary["episode_id"] != binding.episode_id
            or summary["configuration"] != binding.configuration
            or summary["record_count"] != binding.transition_count
            or summary["transition_sha256"] != binding.transition_sha256
        ):
            _fail("dataset_protocol_binding_mismatch", binding.episode_id)
        if summary.get("evidence_level") != self.expected_evidence_level:
            _fail("dataset_evidence_level_mismatch", binding.episode_id)
        dataset = load_koopman_episode_v21(transition, manifest)
        observed_source_commits = {
            str(provenance.get("source_commit", ""))
            for provenance in dataset.episode_provenance
        }
        if observed_source_commits != {self.expected_source_commit}:
            _fail("dataset_source_commit_mismatch", binding.episode_id)
        self._cache[binding.episode_id] = dataset
        return dataset

    def _candidate_grid(self) -> tuple[Any, ...]:
        from koopman.loco_v21 import CandidateSpecV21
        from koopman.model_v21 import CONDITIONING_STRUCTURED_PCA2_V21

        result = []
        for family in ("pooled", "conditional"):
            for observable in self.analysis_policy["observable_candidates"]:
                for prefix in self.analysis_policy["data_prefixes"]:
                    for ridge in self.analysis_policy["ridge_grid"]:
                        for normalization in self.analysis_policy[
                            "normalization_candidates"
                        ]:
                            result.append(
                                CandidateSpecV21(
                                    family=family,
                                    observable_schema=observable,
                                    data_prefix=prefix,
                                    ridge=ridge,
                                    normalization=normalization,
                                    conditioning=(
                                        "none"
                                        if family == "pooled"
                                        else CONDITIONING_STRUCTURED_PCA2_V21
                                    ),
                                    label=(
                                        f"{family}:{observable}:p{prefix}:r{ridge}:"
                                        f"{normalization}"
                                    ),
                                )
                            )
        return tuple(result)

    @staticmethod
    def _descriptor(dataset: Any) -> Any:
        from koopman.platform_features_v21 import build_physical_core_descriptor_v21

        return build_physical_core_descriptor_v21(dataset.platform_contexts)

    @staticmethod
    def _selected_fit(
        loaded: Sequence[tuple[ProtocolEpisodeBindingV21, Any]],
        configurations: Sequence[str],
        prefix: int,
    ) -> tuple[tuple[ProtocolEpisodeBindingV21, Any], ...]:
        selected = []
        for configuration in configurations:
            rows = tuple(
                item
                for item in loaded
                if item[0].configuration == configuration and item[0].role == "fit"
            )
            if len(rows) < prefix:
                _fail("fit_prefix_unavailable", configuration)
            selected.extend(rows[:prefix])
        return tuple(selected)

    @staticmethod
    def _fit_model(
        candidate: Any,
        loaded: Sequence[tuple[ProtocolEpisodeBindingV21, Any]],
        configurations: Sequence[str],
        projector: Any,
    ) -> Any:
        import numpy as np

        from koopman.model_v21 import ControlledEDMDV21, build_increment_targets_v21

        selected = DatasetFormalLocoBackendV21._selected_fit(
            loaded, configurations, candidate.data_prefix
        )
        states = np.concatenate([dataset.state_11 for _, dataset in selected])
        memory = np.concatenate([dataset.actuator_memory_4 for _, dataset in selected])
        controls = np.concatenate([dataset.virtual_control_4 for _, dataset in selected])
        targets = np.concatenate(
            [
                build_increment_targets_v21(dataset.state_11, dataset.Y)
                for _, dataset in selected
            ]
        )
        kwargs: dict[str, Any] = {}
        if candidate.family == "conditional":
            scores = {
                configuration: projector.transform(
                    DatasetFormalLocoBackendV21._descriptor(
                        next(
                            dataset
                            for binding, dataset in selected
                            if binding.configuration == configuration
                        )
                    )
                )
                for configuration in configurations
            }
            kwargs = {
                "platform_scores": np.concatenate(
                    [
                        np.repeat(
                            scores[binding.configuration][None, :],
                            dataset.sample_count,
                            axis=0,
                        )
                        for binding, dataset in selected
                    ]
                ),
                "row_configurations": tuple(
                    configuration
                    for binding, dataset in selected
                    for configuration in [binding.configuration] * dataset.sample_count
                ),
                "source_configurations": tuple(configurations),
            }
        return ControlledEDMDV21.fit(
            states,
            memory,
            controls,
            targets,
            observable_schema=candidate.observable_schema,
            conditioning=candidate.conditioning,
            ridge=candidate.ridge,
            normalization=candidate.normalization,
            **kwargs,
        )

    @staticmethod
    def _rollout_policy() -> Any:
        from koopman.metrics_v21 import OFFICIAL_ROLLOUT_POLICY_V21

        return OFFICIAL_ROLLOUT_POLICY_V21

    @staticmethod
    def _artifact(model: Any, dataset: Any, *, projector: Any | None) -> Any:
        from koopman.metrics_v21 import (
            RolloutEpisodeV21,
            evaluate_episode_metrics_v21,
        )

        score = None
        if projector is not None:
            score = projector.transform(DatasetFormalLocoBackendV21._descriptor(dataset))
        return evaluate_episode_metrics_v21(
            model,
            RolloutEpisodeV21.from_dataset(dataset),
            policy=DatasetFormalLocoBackendV21._rollout_policy(),
            platform_score=score,
        )

    @staticmethod
    def _configuration_errors(
        model: Any,
        loaded: Sequence[tuple[ProtocolEpisodeBindingV21, Any]],
        configurations: Sequence[str],
        *,
        projector: Any | None,
    ) -> dict[str, dict[str, float] | None]:
        result: dict[str, dict[str, float] | None] = {}
        for configuration in configurations:
            artifacts = []
            for binding, dataset in loaded:
                if binding.configuration == configuration and binding.role == "validation":
                    artifacts.append(
                        DatasetFormalLocoBackendV21._artifact(
                            model, dataset, projector=projector
                        )
                    )
            full = [artifact.horizons["full"] for artifact in artifacts]
            if not full or any(item.status != "success" for item in full):
                result[configuration] = None
            else:
                result[configuration] = {
                    metric: sum(float(item.values[metric]) for item in full) / len(full)
                    for metric in PRIMARY_METRICS_V21
                }
        return result

    @staticmethod
    def _normalizer_identity(model: Any) -> str:
        return canonical_sha256(
            {
                "design": (
                    None
                    if model.design_normalizer is None
                    else model.design_normalizer.to_dict()
                ),
                "target": (
                    None
                    if model.target_normalizer is None
                    else model.target_normalizer.to_dict()
                ),
            }
        )

    def prepare_source_fold(
        self,
        *,
        heldout_configuration: str,
        source_configurations: Sequence[str],
        source_bindings: Sequence[ProtocolEpisodeBindingV21],
    ) -> FormalFoldSourceInputsV21:
        import sys

        from koopman.loco_v21 import (
            CandidateEvaluationV21,
            NumericalDiagnosticsV21,
            SourceMetricRecordV21,
        )
        from koopman.model_v21 import CandidateAdmissionErrorV21
        from koopman.platform_features_v21 import fit_source_pca_v21

        sources = tuple(source_configurations)
        bindings = tuple(source_bindings)
        if (
            len(bindings) != 63
            or any(
                binding.configuration not in sources
                or binding.role not in {"fit", "validation"}
                for binding in bindings
            )
        ):
            _fail("formal_source_binding_set_invalid")
        loaded = tuple((binding, self.open_episode(binding)) for binding in bindings)
        descriptors = {
            configuration: self._descriptor(
                next(
                    dataset
                    for binding, dataset in loaded
                    if binding.configuration == configuration
                )
            )
            for configuration in sources
        }
        projector = fit_source_pca_v21(
            descriptors, source_configurations=sources
        )
        persistence = self._configuration_errors(
            _PersistenceIncrementModelV21(), loaded, sources, projector=None
        )
        if any(value is None for value in persistence.values()):
            _fail("persistence_validation_failed")
        candidates = self._candidate_grid()
        simple_cache: dict[tuple[int, float, str], tuple[Any, dict[str, Any]]] = {}
        models: dict[str, Any] = {}
        evaluations = []
        for candidate in candidates:
            simple_key = (
                candidate.data_prefix,
                candidate.ridge,
                candidate.normalization,
            )
            if simple_key not in simple_cache:
                from koopman.loco_v21 import CandidateSpecV21

                simple_spec = CandidateSpecV21(
                    family="pooled",
                    observable_schema="so3_identity_v1",
                    data_prefix=candidate.data_prefix,
                    ridge=candidate.ridge,
                    normalization=candidate.normalization,
                    conditioning="none",
                    label=f"simple:{simple_key}",
                )
                try:
                    simple_model = self._fit_model(
                        simple_spec, loaded, sources, projector
                    )
                    simple_errors = self._configuration_errors(
                        simple_model, loaded, sources, projector=None
                    )
                except Exception:
                    simple_model = None
                    simple_errors = dict.fromkeys(sources, None)
                simple_cache[simple_key] = simple_model, simple_errors
            simple_model, simple_errors = simple_cache[simple_key]
            model = None
            errors: dict[str, dict[str, float] | None] = dict.fromkeys(sources, None)
            diagnostics = {
                "design_rank": 0,
                "effective_rank": 0.0,
                "design_width": (
                    (66 if candidate.observable_schema == "so3_identity_v1" else 100)
                    if candidate.family == "conditional"
                    else (22 if candidate.observable_schema == "so3_identity_v1" else 56)
                ),
                "regularized_condition": sys.float_info.max,
            }
            rejection: str | None = None
            try:
                model = self._fit_model(candidate, loaded, sources, projector)
                diagnostics = dict(model.diagnostics)
                errors = self._configuration_errors(
                    model,
                    loaded,
                    sources,
                    projector=(projector if candidate.family == "conditional" else None),
                )
                if any(value is None for value in errors.values()):
                    rejection = "source_validation_rollout_failed"
                    model = None
            except CandidateAdmissionErrorV21 as exc:
                diagnostics = dict(exc.diagnostics)
                rejection = str(exc)
            except Exception as exc:
                rejection = str(exc) or "candidate_fit_failed"
            records = tuple(
                SourceMetricRecordV21(
                    configuration=configuration,
                    candidate_errors=(
                        dict.fromkeys(PRIMARY_METRICS_V21, None)
                        if errors[configuration] is None
                        else errors[configuration]
                    ),
                    persistence_errors=persistence[configuration],
                    simple_linear_errors=(
                        dict.fromkeys(PRIMARY_METRICS_V21, sys.float_info.max)
                        if simple_errors[configuration] is None
                        else simple_errors[configuration]
                    ),
                )
                for configuration in sources
            )
            width = int(diagnostics.get("design_width", 1))
            condition = float(
                diagnostics.get("regularized_condition", sys.float_info.max)
            )
            if not math.isfinite(condition):
                condition = sys.float_info.max
            numerics = NumericalDiagnosticsV21(
                int(diagnostics.get("design_rank", 0)),
                float(diagnostics.get("effective_rank", 0.0)),
                width,
                condition,
            )
            converged = model is not None
            if converged:
                models[candidate.candidate_id] = model
            evaluations.append(
                CandidateEvaluationV21(
                    candidate=candidate,
                    source_records=records,
                    numerics=numerics,
                    converged=converged,
                    rejection_reason=None if converged else (rejection or "candidate_failed"),
                    model_identity=None if model is None else model.model_sha256,
                    normalizer_identity=(
                        "unavailable"
                        if model is None
                        else self._normalizer_identity(model)
                    ),
                    pca_identity=(
                        projector.projector_sha256
                        if model is not None and candidate.family == "conditional"
                        else None
                    ),
                )
            )
        self._fold_contexts[heldout_configuration] = {
            "candidate_by_id": {candidate.candidate_id: candidate for candidate in candidates},
            "models": models,
            "projector": projector,
            "simple_cache": simple_cache,
        }
        return FormalFoldSourceInputsV21(
            expected_candidates=candidates,
            candidate_evaluations=tuple(evaluations),
            source_transform=projector,
        )

    def bind_primary(self, *, heldout_configuration: str, primary: Any) -> None:
        self._fold_contexts[heldout_configuration]["primary"] = primary

    def build_heldout_descriptor(self, *, heldout_configuration: str) -> Any:
        context = self._fold_contexts.get(heldout_configuration)
        if context is None or context.get("primary") is None:
            _fail("heldout_descriptor_before_primary_freeze")
        from koopman.platform_features_v21 import (
            build_physical_core_descriptor_v21,
            declared_platform_context_v21,
        )

        return build_physical_core_descriptor_v21(
            (declared_platform_context_v21(heldout_configuration),)
        )

    def expert_candidates(self, *, heldout_configuration: str) -> tuple[Any, ...]:
        del heldout_configuration
        result = []
        for observable in self.analysis_policy["observable_candidates"]:
            for ridge in self.analysis_policy["ridge_grid"]:
                for normalization in self.analysis_policy["normalization_candidates"]:
                    result.append(
                        ExpertCandidateSpecV21(
                            f"expert:{observable}:r{ridge}:{normalization}",
                            observable,
                            ridge,
                            normalization,
                        )
                    )
        return tuple(result)

    def fit_expert(self, candidate: ExpertCandidateSpecV21, payloads: tuple[Any, ...]) -> Any:
        import numpy as np

        from koopman.model_v21 import ControlledEDMDV21, build_increment_targets_v21

        states = np.concatenate([dataset.state_11 for dataset in payloads])
        memory = np.concatenate([dataset.actuator_memory_4 for dataset in payloads])
        controls = np.concatenate([dataset.virtual_control_4 for dataset in payloads])
        targets = np.concatenate(
            [build_increment_targets_v21(dataset.state_11, dataset.Y) for dataset in payloads]
        )
        model = ControlledEDMDV21.fit(
            states,
            memory,
            controls,
            targets,
            observable_schema=candidate.observable_schema,
            conditioning="none",
            ridge=candidate.ridge,
            normalization=candidate.normalization,
        )
        return {
            "candidate_id": candidate.candidate_id,
            "model": model,
            "model_identity": model.model_sha256,
            "normalizer_identity": self._normalizer_identity(model),
        }

    def evaluate_expert(
        self, model: Mapping[str, Any], payloads: tuple[Any, ...]
    ) -> tuple[float, Mapping[str, float]]:
        artifacts = [
            self._artifact(model["model"], dataset, projector=None)
            for dataset in payloads
        ]
        full = [artifact.horizons["full"] for artifact in artifacts]
        if any(item.status != "success" for item in full):
            _fail("expert_validation_rollout_failed")
        metrics = {
            metric: sum(float(item.values[metric]) for item in full) / len(full)
            for metric in PRIMARY_METRICS_V21
        }
        return max(metrics.values()), metrics

    @staticmethod
    def serialize_expert(model: Mapping[str, Any]) -> bytes:
        return canonical_json_bytes(
            {
                "candidate_id": model["candidate_id"],
                "model": model["model"].to_dict(),
                "version": "phase8.1-heldout-expert-model-v1",
            }
        )

    @staticmethod
    def load_expert(payload: bytes) -> Mapping[str, Any]:
        from koopman.model_v21 import ControlledEDMDV21

        try:
            value = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("expert_artifact_roundtrip_failed") from exc
        if not isinstance(value, Mapping) or set(value) != {
            "candidate_id",
            "model",
            "version",
        } or value.get("version") != "phase8.1-heldout-expert-model-v1":
            _fail("expert_artifact_roundtrip_failed")
        model = ControlledEDMDV21.from_dict(value["model"])
        return MappingProxyType(
            {"candidate_id": str(value["candidate_id"]), "model": model}
        )

    @staticmethod
    def expert_identities(model: Mapping[str, Any]) -> tuple[str, str]:
        fitted = model.get("model")
        if fitted is None:
            _fail("expert_artifact_roundtrip_failed")
        return (
            fitted.model_sha256,
            DatasetFormalLocoBackendV21._normalizer_identity(fitted),
        )

    def evaluate_test_horizons(
        self,
        *,
        heldout_configuration: str,
        role: str,
        model_identity: str | None,
        opened_episodes: Sequence[Any],
    ) -> tuple[Mapping[str, Any], ...]:
        from koopman.selection_v21 import HorizonOuterEvidenceV21

        context = self._fold_contexts[heldout_configuration]
        projector = None
        if role == "persistence":
            model = _PersistenceIncrementModelV21()
        elif role in {"pooled", "conditional"}:
            model = next(
                value
                for value in context["models"].values()
                if value.model_sha256 == model_identity
            )
            projector = context["projector"] if role == "conditional" else None
        elif role == "simple_linear":
            primary = context.get("primary")
            if primary is None:
                _fail("primary_backend_binding_missing")
            selected_id = primary.selected_candidates.get("pooled") or primary.selected_candidates.get(
                "conditional"
            )
            candidate = context["candidate_by_id"][selected_id]
            key = (candidate.data_prefix, candidate.ridge, candidate.normalization)
            model = context["simple_cache"][key][0]
            if model is None:
                _fail("simple_linear_unavailable")
        else:
            _fail("formal_test_role_invalid")
        result = []
        for dataset in opened_episodes:
            artifact = self._artifact(model, dataset, projector=projector)
            horizons = {}
            for name in ("5", "20", "60", "full"):
                value = artifact.horizons[name]
                horizons[name] = HorizonOuterEvidenceV21(
                    metrics=dict(value.values),
                    status=value.status,
                    reason_code=value.reason_code,
                    transition_count=value.transition_count,
                    window_count=value.window_count,
                    nonfinite_count=value.nonfinite_count,
                    invalid_quaternion_count=value.invalid_quaternion_count,
                    quaternion_unit_norm_drift_count=(
                        value.quaternion_unit_norm_drift_count
                    ),
                    quaternion_projection_count=value.quaternion_projection_count,
                    divergence_count=value.divergence_count,
                )
            result.append(horizons)
        return tuple(result)
