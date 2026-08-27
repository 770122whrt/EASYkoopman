"""Build a strict post-collection Phase 8 inventory from actual bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.collection_v2 import (
    build_dataset_inventory_v2,
    load_episode_role_intents_v2,
    validate_dataset_inventory_v2,
    write_dataset_inventory_v2,
)
from koopman.evidence_v2 import load_bounded_json
from koopman.protocol_v2 import (
    MAIN_ROLE_PROTOCOL_VERSION,
    main_role_intents_v2,
    validate_main_role_protocol_v1,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an actual-byte Phase 8 dataset inventory."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument("--runtime-sha256", required=True)
    parser.add_argument("--envelope-sha256")
    parser.add_argument("--qualification", default="local_contract")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        intent_payload = load_bounded_json(args.intent)
        if intent_payload.get("protocol_version") == MAIN_ROLE_PROTOCOL_VERSION:
            validate_main_role_protocol_v1(intent_payload)
            intents = main_role_intents_v2(intent_payload)
        else:
            intents = load_episode_role_intents_v2(args.intent)
        inventory = build_dataset_inventory_v2(
            args.root,
            intents,
            role_protocol_sha256=hashlib.sha256(args.intent.read_bytes()).hexdigest(),
            runtime_sha256=args.runtime_sha256,
            envelope_sha256=args.envelope_sha256,
            qualification_level=args.qualification,
        )
        validate_dataset_inventory_v2(
            inventory,
            root=args.root,
            intents=intents,
        )
        write_dataset_inventory_v2(inventory, args.output)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "episode_count": len(inventory.entries),
                "inventory_sha256": inventory.inventory_sha256,
                "qualification_level": inventory.qualification_level,
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
