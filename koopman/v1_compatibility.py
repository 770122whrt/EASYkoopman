"""Explicit read-only access to legacy Koopman v1 evidence.

This module deliberately has no v2 builder, writer, migration, inference or
promotion API.  The existing v1 loader remains the sole validation authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from koopman_data import load_koopman_samples


V1_UNAVAILABLE_FIELDS = frozenset(
    {
        "virtual_control_4",
        "thruster_mask_8",
        "applied_wrench_6",
        "platform_context",
        "environment_context_oracle",
        "environment_context_estimated",
        "configuration",
        "episode_provenance",
    }
)


class _FrozenList(tuple):
    """Tuple storage that compares by sequence value to its source v1 list."""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (list, tuple)):
            return tuple(self) == tuple(other)
        return False

    __hash__ = tuple.__hash__


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(nested) for key, nested in value.items()})
    if isinstance(value, (list, tuple)):
        return _FrozenList(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class V1CompatibilityView:
    """Auditable v1 records with explicit missing-v2 and ineligibility facts."""

    samples: tuple[Mapping[str, Any], ...]
    source_schema: str = "v1"
    eligible_for_v2_cross_configuration_training: bool = False
    unavailable_fields: frozenset[str] = V1_UNAVAILABLE_FIELDS
    source_path: str = ""

    def __post_init__(self) -> None:
        if self.source_schema != "v1":
            raise ValueError("v1_source_schema_required")
        if self.eligible_for_v2_cross_configuration_training is not False:
            raise ValueError("v1_not_v2_training_eligible")
        if frozenset(self.unavailable_fields) != V1_UNAVAILABLE_FIELDS:
            raise ValueError("v1_unavailable_fields_mismatch")
        object.__setattr__(self, "samples", tuple(_freeze(sample) for sample in self.samples))
        object.__setattr__(self, "unavailable_fields", V1_UNAVAILABLE_FIELDS)
        object.__setattr__(self, "source_path", str(self.source_path))


def load_v1_compatibility(path: str | Path) -> V1CompatibilityView:
    """Validate with the existing v1 loader, then return a frozen copied view."""
    samples = load_koopman_samples(path)
    return V1CompatibilityView(samples=tuple(samples), source_path=str(path))


def require_v2_training_eligibility(view: V1CompatibilityView) -> None:
    """Fail closed because a v1 view can never satisfy schema-v2 eligibility."""
    if not isinstance(view, V1CompatibilityView):
        raise ValueError("v1_compatibility_view_required")
    raise ValueError("v1_not_v2_training_eligible")
