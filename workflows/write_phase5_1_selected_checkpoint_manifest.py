from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.ppo_training_adapter import (
    ADAPTER_MODE,
    PHASE5_1_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_1_CANDIDATE_EVIDENCE_LEVEL,
    PHASE5_REWARD_PROFILE,
)


def _load_summary(path: str | Path) -> dict[str, Any]:
    summary_path = Path(path)
    if not summary_path.exists():
        raise ValueError(f"summary path does not exist: {summary_path}")
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("summary must be a JSON object")
    return payload


def write_selected_checkpoint_manifest(
    source_training_summary_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    summary_path = Path(source_training_summary_path)
    summary = _load_summary(summary_path)
    expected_values = {
        "checkpoint_provenance": PHASE5_1_CANDIDATE_CHECKPOINT_PROVENANCE,
        "ppo_evidence_level": PHASE5_1_CANDIDATE_EVIDENCE_LEVEL,
        "reward_profile": PHASE5_REWARD_PROFILE,
        "adapter_mode": ADAPTER_MODE,
        "koopman_backend": "direct_state",
        "observation_dim": 9,
        "action_dim": 4,
    }
    for field_name, expected in expected_values.items():
        if summary.get(field_name) != expected:
            raise ValueError(f"{field_name} must be {expected!r}, got {summary.get(field_name)!r}")
    selected_checkpoint = summary.get("selected_checkpoint")
    if not selected_checkpoint:
        raise ValueError("selected_checkpoint is required")

    manifest = {
        "phase": "05.1",
        "selected_checkpoint": selected_checkpoint,
        "selected_rule": summary.get("selected_rule", "latest_valid_after_stability_validator"),
        "source_training_summary_path": str(summary_path),
        "ppo_evidence_level": PHASE5_1_CANDIDATE_EVIDENCE_LEVEL,
        "checkpoint_provenance": PHASE5_1_CANDIDATE_CHECKPOINT_PROVENANCE,
        "reward_profile": PHASE5_REWARD_PROFILE,
        "adapter_mode": ADAPTER_MODE,
        "koopman_backend": "direct_state",
        "observation_dim": 9,
        "action_dim": 4,
        "selected_weight_status": summary.get("selected_weight_status", "candidate_only"),
        "matched_eval_status": summary.get("matched_eval_status", "pending"),
        "allowed_claims": summary.get("allowed_claims", []),
        "disallowed_claims": summary.get("disallowed_claims", []),
    }
    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the selected Phase 5.1 PPO checkpoint manifest.")
    parser.add_argument("--source_training_summary_path", required=True, help="Phase 5.1 stability summary JSON.")
    parser.add_argument("--output_path", required=True, help="Output selected checkpoint manifest path.")
    args = parser.parse_args(argv)

    try:
        manifest = write_selected_checkpoint_manifest(args.source_training_summary_path, args.output_path)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
