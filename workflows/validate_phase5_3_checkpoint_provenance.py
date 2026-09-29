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

from koopman.phase5_3_profiles import (
    PHASE5_3_CANDIDATE_EVIDENCE_LEVEL,
    PHASE5_3_COMPARISON_BASELINE,
    PHASE5_3_EVIDENCE_LEVELS,
    PHASE5_3_EXTENDED_EVIDENCE_LEVEL,
    PHASE5_3_HEALTH_FLOOR,
    PHASE5_3_MATCHED_EVIDENCE_LEVEL,
    PHASE5_3_TRAINING_LADDER_STAGES,
    checkpoint_provenance_for_phase53_evidence,
    resolve_phase53_profile,
)
from koopman.ppo_training_adapter import ADAPTER_MODE, PHASE5_CONTROLLER_PATH, PHASE5_RESULT_BUCKET


REQUIRED_PHASE5_3_SUMMARY_FIELDS = (
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
    "risk_level",
    "sentinel_required",
    "training_ladder_stage",
    "comparison_baseline",
    "health_floor",
    "source_phase5_2_summary_path",
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
    missing = [field for field in REQUIRED_PHASE5_3_SUMMARY_FIELDS if field not in summary]
    if missing:
        raise ValueError(f"Missing Phase 5.3 provenance summary fields: {missing}")


def _training_evidence_for_expected(expected_evidence_level: str, summary: dict[str, Any]) -> str:
    if expected_evidence_level == PHASE5_3_MATCHED_EVIDENCE_LEVEL:
        summary_evidence = str(summary["ppo_evidence_level"])
        if summary_evidence not in (PHASE5_3_CANDIDATE_EVIDENCE_LEVEL, PHASE5_3_EXTENDED_EVIDENCE_LEVEL):
            raise ValueError(
                "checkpoint_provenance/ppo_evidence_level must identify a candidate or extended Phase 5.3 "
                "checkpoint summary for phase5_3_cross_matched_eval"
            )
        return summary_evidence
    return expected_evidence_level


def _require_expected_values(summary: dict[str, Any], expected_evidence_level: str) -> None:
    if expected_evidence_level not in PHASE5_3_EVIDENCE_LEVELS:
        raise ValueError(f"Unsupported Phase 5.3 expected evidence level: {expected_evidence_level!r}")

    summary_evidence_level = _training_evidence_for_expected(expected_evidence_level, summary)
    profile = resolve_phase53_profile(
        profile_id=str(summary["profile_id"]),
        reward_profile=str(summary["reward_profile"]),
        adapter_profile=str(summary["adapter_profile"]),
        mpc_profile=str(summary["mpc_profile"]),
        changed_axis=str(summary["changed_axis"]),
    )
    expected_values = {
        "result_bucket": PHASE5_RESULT_BUCKET,
        "checkpoint_provenance": checkpoint_provenance_for_phase53_evidence(summary_evidence_level),
        "ppo_evidence_level": summary_evidence_level,
        "controller_path": PHASE5_CONTROLLER_PATH,
        "adapter_mode": ADAPTER_MODE,
        "koopman_backend": "direct_state",
        "observation_dim": 9,
        "action_dim": 4,
        "comparison_baseline": PHASE5_3_COMPARISON_BASELINE,
        "health_floor": PHASE5_3_HEALTH_FLOOR,
    }
    for field_name, expected in expected_values.items():
        if summary[field_name] != expected:
            raise ValueError(f"{field_name} must be {expected!r}, got {summary[field_name]!r}")

    if summary["risk_level"] != profile.risk_level:
        raise ValueError(f"risk_level must be {profile.risk_level!r}, got {summary['risk_level']!r}")
    if bool(summary["sentinel_required"]) is not profile.sentinel_required:
        raise ValueError("sentinel_required does not match the Phase 5.3 profile contract")
    if str(summary["training_ladder_stage"]) not in PHASE5_3_TRAINING_LADDER_STAGES:
        raise ValueError(f"training_ladder_stage must be one of {list(PHASE5_3_TRAINING_LADDER_STAGES)}")
    if not str(summary["source_phase5_2_summary_path"]).strip():
        raise ValueError("source_phase5_2_summary_path must be a non-empty string")


def _require_checkpoint_match(checkpoint_path: Path, summary: dict[str, Any]) -> None:
    selected = Path(str(summary["selected_checkpoint"]))
    try:
        selected_resolved = selected.resolve()
    except OSError as exc:
        raise ValueError(f"selected_checkpoint cannot be resolved: {selected}") from exc
    if selected_resolved != checkpoint_path:
        raise ValueError(f"selected_checkpoint must match checkpoint path: {selected_resolved} != {checkpoint_path}")
    if summary["checkpoint_found"] is not True:
        raise ValueError("checkpoint_found must be true for Phase 5.3 provenance")


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


def validate_phase5_3_checkpoint_provenance(
    checkpoint_path: str | Path,
    source_training_summary_path: str | Path,
    *,
    expected_evidence_level: str = PHASE5_3_CANDIDATE_EVIDENCE_LEVEL,
) -> dict[str, Any]:
    if expected_evidence_level not in PHASE5_3_EVIDENCE_LEVELS:
        raise ValueError(f"expected_evidence_level must be one of {list(PHASE5_3_EVIDENCE_LEVELS)}")
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
        "source_risk_level": summary["risk_level"],
        "source_training_ladder_stage": summary["training_ladder_stage"],
        "source_phase5_2_summary_path": summary["source_phase5_2_summary_path"],
        "source_log_dir": summary.get("log_dir"),
        "source_git_commit": summary["source_git_commit"],
        "source_git_dirty": summary["source_git_dirty"],
        "source_checkpoint_mtime": summary["source_checkpoint_mtime"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 5.3 PPO checkpoint provenance.")
    parser.add_argument("--checkpoint", required=True, help="Checkpoint to validate.")
    parser.add_argument("--source_training_summary_path", required=True, help="Phase 5.3 summary JSON.")
    parser.add_argument(
        "--expected_evidence_level",
        choices=PHASE5_3_EVIDENCE_LEVELS,
        default=PHASE5_3_CANDIDATE_EVIDENCE_LEVEL,
        help="Expected Phase 5.3 evidence level.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    try:
        result = validate_phase5_3_checkpoint_provenance(
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
