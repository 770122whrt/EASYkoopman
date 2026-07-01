from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class DataInsufficientError(ValueError):
    """Raised when a split cannot support the final model gate."""


def _string_paths(paths: Iterable[str | Path]) -> tuple[str, ...]:
    return tuple(str(Path(path)) for path in paths)


@dataclass(frozen=True)
class SplitManifest:
    train_logs: tuple[str, ...]
    validation_logs: tuple[str, ...]
    test_logs: tuple[str, ...]
    split_rule: str
    seed: int | None = None
    notes: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "train_logs": list(self.train_logs),
            "validation_logs": list(self.validation_logs),
            "test_logs": list(self.test_logs),
            "split_rule": self.split_rule,
            "seed": self.seed,
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SplitManifest":
        return cls(
            train_logs=tuple(data.get("train_logs", ())),
            validation_logs=tuple(data.get("validation_logs", ())),
            test_logs=tuple(data.get("test_logs", ())),
            split_rule=str(data.get("split_rule", "")),
            seed=data.get("seed"),
            notes=str(data.get("notes", "")),
            created_at=str(data.get("created_at", "")),
        )


def create_explicit_split(
    *,
    train_logs: Iterable[str | Path],
    validation_logs: Iterable[str | Path],
    test_logs: Iterable[str | Path],
    seed: int | None = None,
    notes: str = "",
) -> SplitManifest:
    manifest = SplitManifest(
        train_logs=_string_paths(train_logs),
        validation_logs=_string_paths(validation_logs),
        test_logs=_string_paths(test_logs),
        split_rule="explicit",
        seed=seed,
        notes=notes,
    )
    validate_split_manifest(manifest)
    return manifest


def _resolved(paths: Iterable[str]) -> list[Path]:
    return [Path(path).expanduser().resolve() for path in paths]


def validate_split_manifest(manifest: SplitManifest, *, final_gate: bool = False) -> None:
    if not manifest.split_rule.strip():
        raise ValueError("split_rule must be non-empty")
    if not manifest.train_logs:
        raise DataInsufficientError("train_logs must contain at least one log")
    if final_gate and (not manifest.validation_logs or not manifest.test_logs):
        raise DataInsufficientError("final gate requires non-empty validation_logs and test_logs")

    groups = {
        "train_logs": manifest.train_logs,
        "validation_logs": manifest.validation_logs,
        "test_logs": manifest.test_logs,
    }
    seen: dict[Path, str] = {}
    for group_name, paths in groups.items():
        for path in _resolved(paths):
            if not path.exists():
                raise FileNotFoundError(f"{group_name} path does not exist: {path}")
            previous = seen.get(path)
            if previous is not None:
                raise ValueError(f"split overlap: {path} appears in both {previous} and {group_name}")
            seen[path] = group_name


def write_split_manifest(manifest: SplitManifest, path: str | Path) -> None:
    validate_split_manifest(manifest)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def read_split_manifest(path: str | Path) -> SplitManifest:
    manifest = SplitManifest.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    validate_split_manifest(manifest)
    return manifest
