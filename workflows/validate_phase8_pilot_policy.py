"""Validate the operational runtime boundary of the Phase 8 pilot policy."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.protocol_v2 import (
    load_pilot_collection_policy,
    validate_pilot_collection_policy,
)


EXPECTED_SERVER_RUNTIME_CONTRACT = {
    "isaac_sim_version": "5.0",
    "isaac_lab_version": "2.2.1",
    "python_entrypoint": "/root/IsaacLab/isaaclab.sh -p",
}


def validate_operational_pilot_policy(value: Any) -> None:
    """Require the exact server launcher and versions outside the model package."""
    validate_pilot_collection_policy(value)
    runtime = value["runtime_contract"]
    for field, expected in EXPECTED_SERVER_RUNTIME_CONTRACT.items():
        if runtime[field] != expected:
            raise ValueError(f"pilot_runtime_contract_mismatch:{field}")


def load_operational_pilot_policy(path: str | Path) -> dict[str, Any]:
    """Load the bounded scientific protocol, then enforce operational runtime facts."""
    policy = load_pilot_collection_policy(path)
    validate_operational_pilot_policy(policy)
    return policy


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the exact Phase 8 pilot server runtime policy."
    )
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        policy = load_operational_pilot_policy(args.policy)
        result = {
            "validation_gate": "phase8_pilot_operational_policy_valid",
            "policy_sha256": hashlib.sha256(args.policy.read_bytes()).hexdigest(),
            "runtime_contract": policy["runtime_contract"],
        }
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    else:
        print(f"validation_gate={result['validation_gate']}")
        print(f"policy_sha256={result['policy_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
