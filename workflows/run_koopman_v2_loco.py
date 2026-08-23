"""Validate and bind a local Phase 8 LOCO run contract.

The numerical fold engine is exposed by ``koopman.loco_v2.FoldExecutionV2``;
this entry point confines a requested run to a fresh output root and records
the immutable inventory, split, policy and fold hashes that a runner consumes.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.collection_v2 import DatasetInventoryV2
from koopman.evidence_v2 import canonical_json_bytes, canonical_sha256
from koopman.protocol_v2 import load_analysis_policy_v1
from koopman.splits_v2 import LOCOSplitManifestV2


_MAX_INPUT_BYTES = 16 * 1024 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bind a fresh local Phase 8 v2 LOCO run contract."
    )
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--analysis-policy", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--fold",
        default="all",
        help="A fold id or holdout configuration; default: all.",
    )
    return parser


def _load_json(path: Path) -> Any:
    if path.is_symlink() or not path.exists() or not path.is_file():
        raise ValueError(f"input_artifact_invalid:{path}")
    raw = path.read_bytes()
    if len(raw) > _MAX_INPUT_BYTES:
        raise ValueError(f"input_artifact_too_large:{path}")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate_json_key:{key}")
            result[key] = value
        return result

    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"nonfinite_json:{value}")
        ),
    )


def _requested_folds(split: LOCOSplitManifestV2, requested: str):
    if requested == "all":
        return split.folds
    matches = tuple(
        fold
        for fold in split.folds
        if fold.fold_id == requested or fold.holdout_configuration == requested
    )
    if len(matches) != 1:
        raise ValueError(f"fold_not_found:{requested}")
    return matches


def _write_fresh_contract(output_root: Path, payload: dict[str, Any]) -> Path:
    if output_root.exists() or output_root.is_symlink():
        raise ValueError(f"output_root_exists:{output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    target = output_root / "run_contract.json"
    part = output_root / "run_contract.json.part"
    try:
        with part.open("xb") as stream:
            stream.write(canonical_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(part, target)
    finally:
        if part.exists():
            part.unlink()
    return target


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inventory = DatasetInventoryV2.from_dict(_load_json(args.inventory))
    split = LOCOSplitManifestV2.from_dict(_load_json(args.split))
    policy = load_analysis_policy_v1(args.analysis_policy)
    if split.inventory_sha256 != inventory.inventory_sha256:
        raise ValueError("inventory_split_hash_mismatch")
    folds = _requested_folds(split, args.fold)
    for fold in folds:
        if fold.inventory_sha256 != inventory.inventory_sha256:
            raise ValueError(f"fold_inventory_hash_mismatch:{fold.fold_id}")
        if len(fold.source_configurations) != 7:
            raise ValueError(f"source_configuration_count_invalid:{fold.fold_id}")
    payload = {
        "analysis_policy_sha256": policy.policy_sha256,
        "folds": [
            {
                "fold_id": fold.fold_id,
                "holdout_configuration": fold.holdout_configuration,
                "source_episode_sha256s": list(fold.source_episode_sha256s),
            }
            for fold in folds
        ],
        "inventory_sha256": inventory.inventory_sha256,
        "qualification_level": policy.qualification_level,
        "split_sha256": split.split_sha256,
    }
    payload["run_contract_sha256"] = canonical_sha256(payload)
    target = _write_fresh_contract(args.output_root, payload)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
