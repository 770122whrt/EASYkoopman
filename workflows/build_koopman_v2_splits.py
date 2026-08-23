"""Build exact-eight LOCO manifests from a validated actual-byte inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.collection_v2 import load_dataset_inventory_v2
from koopman.evidence_v2 import load_bounded_json
from koopman.protocol_v2 import main_role_intents_v2, validate_main_role_protocol_v1
from koopman.splits_v2 import (
    build_loco_split_manifest_v2,
    validate_loco_split_manifest_v2,
    write_loco_split_manifest_v2,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build exact-eight Phase 8 LOCO split manifests."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        protocol = load_bounded_json(args.protocol)
        validate_main_role_protocol_v1(protocol)
        intents = main_role_intents_v2(protocol)
        inventory = load_dataset_inventory_v2(
            args.inventory,
            root=args.root,
            intents=intents,
        )
        split = build_loco_split_manifest_v2(
            inventory,
            protocol,
            created_at=args.created_at,
        )
        validate_loco_split_manifest_v2(split, inventory, protocol)
        write_loco_split_manifest_v2(split, args.output)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "fold_count": len(split.folds),
                "inventory_sha256": split.inventory_sha256,
                "split_sha256": split.split_sha256,
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
