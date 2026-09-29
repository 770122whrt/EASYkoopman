from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.phase5_2_profiles import (
    PHASE5_2_CANDIDATE_EVIDENCE_LEVEL,
    PHASE5_2_EVIDENCE_LEVELS,
    PHASE5_2_MATCHED_EVIDENCE_LEVEL,
    checkpoint_provenance_for_phase52_evidence,
    resolve_phase52_profile,
)
from koopman.ppo_training_adapter import ADAPTER_MODE, PHASE5_CONTROLLER_PATH, PHASE5_RESULT_BUCKET


REQUIRED_PHASE5_2_SUMMARY_FIELDS = (
    "checkpoint_found",
    "selected_checkpoint",
    "selected_rule",
    "checkpoint_provenance",
    "result_bucket",
    "ppo_evidence_level",
    "controller_path",
    "adapter_mode",
    "koopman_backend",
    "profile_id",
    "reward_profile",
    "adapter_profile",
    "mpc_profile",
    "changed_axis",
    "source_baseline_manifest",
    "observation_dim",
    "action_dim",
    "source_git_commit",
    "source_git_dirty",
    "source_checkpoint_mtime",
    "adapter_refresh_count",
    "adapter_refresh_before_env_step",
    "nonfinite_observation_count",
    "nonfinite_action_count",
    "completion_status",
)


def _load_summary(path: str | Path) -> dict[str, Any]:
    summary_path = Path(path)
    if not summary_path.exists():
        raise ValueError(f"source_training_summary_path does not exist: {summary_path}")
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"source_training_summary_path is not valid JSON: {summary_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("source training summary must be a JSON object")
    return payload


def _resolve_existing_checkpoint(checkpoint_path: str | Path) -> Path:
    path = Path(checkpoint_path)
    if not path.exists():
        raise ValueError(f"checkpoint_path does not exist: {path}")
    return path.resolve()


def _require_fields(summary: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_PHASE5_2_SUMMARY_FIELDS if field not in summary]
    if missing:
        raise ValueError(f"Missing Phase 5.2 provenance summary fields: {missing}")


def _require_expected_values(summary: dict[str, Any], expected_evidence_level: str) -> None:
    if expected_evidence_level == PHASE5_2_MATCHED_EVIDENCE_LEVEL:
        expected_evidence_level = PHASE5_2_CANDIDATE_EVIDENCE_LEVEL
    if expected_evidence_level not in PHASE5_2_EVIDENCE_LEVELS:
        raise ValueError(f"Unsupported Phase 5.2 expected evidence level: {expected_evidence_level!r}")

    profile = resolve_phase52_profile(
        profile_id=str(summary["profile_id"]),
        reward_profile=str(summary["reward_profile"]),
        adapter_profile=str(summary["adapter_profile"]),
        mpc_profile=str(summary["mpc_profile"]),
        changed_axis=str(summary["changed_axis"]),
    )
    expected_values = {
        "result_bucket": PHASE5_RESULT_BUCKET,
        "checkpoint_provenance": checkpoint_provenance_for_phase52_evidence(expected_evidence_level),
        "ppo_evidence_level": expected_evidence_level,
        "controller_path": PHASE5_CONTROLLER_PATH,
        "adapter_mode": ADAPTER_MODE,
        "koopman_backend": "direct_state",
        "observation_dim": 9,
        "action_dim": 4,
    }
    for field_name, expected in expected_values.items():
        if summary[field_name] != expected:
            raise ValueError(f"{field_name} must be {expected!r}, got {summary[field_name]!r}")
    if not str(summary["source_baseline_manifest"]).strip():
        raise ValueError("source_baseline_manifest must be a non-empty string")
    if not profile.initial_ablation and profile.profile_id != "mpc_delta_limit_probe_v1":
        raise ValueError(f"Unsupported non-initial Phase 5.2 profile: {profile.profile_id}")


def _require_checkpoint_match(checkpoint_path: Path, summary: dict[str, Any]) -> None:
    selected = Path(str(summary["selected_checkpoint"]))
    try:
        selected_resolved = selected.resolve()
    except OSError as exc:
        raise ValueError(f"selected_checkpoint cannot be resolved: {selected}") from exc
    if selected_resolved != checkpoint_path:
        raise ValueError(f"selected_checkpoint must match checkpoint path: {selected_resolved} != {checkpoint_path}")
    if summary["checkpoint_found"] is not True:
        raise ValueError("checkpoint_found must be true for Phase 5.2 provenance")


def _require_health_fields(summary: dict[str, Any]) -> None:
    if int(summary["adapter_refresh_count"]) <= 0:
        raise ValueError("adapter_refresh_count must be greater than zero")
    if summary["adapter_refresh_before_env_step"] is not True:
        raise ValueError("adapter_refresh_before_env_step must be true")
    for field_name in ("nonfinite_observation_count", "nonfinite_action_count"):
        if int(summary[field_name]) != 0:
            raise ValueError(f"{field_name} must be zero")
    if not isinstance(summary["source_git_dirty"], bool):
        raise ValueError("source_git_dirty must be a boolean")
    source_checkpoint_mtime = float(summary["source_checkpoint_mtime"])
    if not math.isfinite(source_checkpoint_mtime) or source_checkpoint_mtime <= 0.0:
        raise ValueError("source_checkpoint_mtime must be positive and finite")
    if not str(summary["completion_status"]).strip():
        raise ValueError("completion_status must be non-empty")


def validate_phase5_2_checkpoint_provenance(
    checkpoint_path: str | Path,
    source_training_summary_path: str | Path,
    *,
    expected_evidence_level: str = PHASE5_2_CANDIDATE_EVIDENCE_LEVEL,
) -> dict[str, Any]:
    if expected_evidence_level not in PHASE5_2_EVIDENCE_LEVELS:
        raise ValueError(f"expected_evidence_level must be one of {list(PHASE5_2_EVIDENCE_LEVELS)}")
    checkpoint = _resolve_existing_checkpoint(checkpoint_path)
    summary_path = Path(source_training_summary_path)
    summary = _load_summary(summary_path)
    _require_fields(summary)
    _require_expected_values(summary, expected_evidence_level)
    _require_checkpoint_match(checkpoint, summary)
    _require_health_fields(summary)

    return {
        "checkpoint_provenance_valid": True,
        "checkpoint_provenance": summary["checkpoint_provenance"],
        "source_training_summary_path": str(summary_path),
        "source_result_bucket": summary["result_bucket"],
        "source_ppo_evidence_level": summary["ppo_evidence_level"],
        "source_controller_path": summary["controller_path"],
        "source_adapter_mode": summary["adapter_mode"],
        "source_koopman_backend": summary["koopman_backend"],
        "source_profile_id": summary["profile_id"],
        "source_reward_profile": summary["reward_profile"],
        "source_adapter_profile": summary["adapter_profile"],
        "source_mpc_profile": summary["mpc_profile"],
        "source_changed_axis": summary["changed_axis"],
        "source_baseline_manifest": summary["source_baseline_manifest"],
        "source_log_dir": summary.get("log_dir"),
        "source_git_commit": summary["source_git_commit"],
        "source_git_dirty": summary["source_git_dirty"],
        "source_checkpoint_mtime": summary["source_checkpoint_mtime"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 5.2 PPO checkpoint provenance.")
    parser.add_argument("--checkpoint", required=True, help="Checkpoint to validate.")
    parser.add_argument("--source_training_summary_path", required=True, help="Phase 5.2 summary JSON.")
    parser.add_argument(
        "--expected_evidence_level",
        choices=PHASE5_2_EVIDENCE_LEVELS,
        default=PHASE5_2_CANDIDATE_EVIDENCE_LEVEL,
        help="Expected Phase 5.2 evidence level.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        result = validate_phase5_2_checkpoint_provenance(
            args.checkpoint,
            args.source_training_summary_path,
            expected_evidence_level=args.expected_evidence_level,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("checkpoint_provenance_valid=true")
        print(f"checkpoint_provenance={result['checkpoint_provenance']}")
        print(f"source_profile_id={result['source_profile_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
