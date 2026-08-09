from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from koopman.policy_adapter import (
    ACTION_SEMANTICS,
    ADAPTER_MODE,
    ADAPTER_QUAT_CONVENTION,
    VALID_PPO_EVIDENCE_LEVELS,
)
from koopman.phase5_2_profiles import (
    PHASE5_2_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_2_MATCHED_EVIDENCE_LEVEL,
    resolve_phase52_profile,
)
from koopman.phase5_3_profiles import (
    PHASE5_3_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_3_EXTENDED_CHECKPOINT_PROVENANCE,
    PHASE5_3_MATCHED_EVIDENCE_LEVEL,
    resolve_phase53_profile,
)
from koopman.phase5_4_profiles import (
    PHASE5_4_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_4_MATCHED_EVIDENCE_LEVEL,
    PHASE5_4_REFINEMENT_CHECKPOINT_PROVENANCE,
    resolve_phase54_profile,
)
from koopman.ppo_training_adapter import (
    PHASE5_CHECKPOINT_PROVENANCE,
    PHASE5_1_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_1_MATCHED_EVIDENCE_LEVEL,
    PHASE5_CONTROLLER_PATH,
    PHASE5_EVIDENCE_LEVEL,
    PHASE5_REWARD_PROFILE,
    PHASE5_RESULT_BUCKET,
)
from koopman_data import validate_koopman_sample, validate_koopman_sequence


REQUIRED_PPO_FIELDS = (
    "policy_mode",
    "policy_output",
    "policy_output_clipped",
    "base_reference",
    "adapted_reference",
    "adapter_mode",
    "action_semantics",
    "ppo_evidence_level",
    "adapter_quat_convention",
    "base_reference_goal_match_max_error",
    "adapter_diagnostics",
    "policy_action_clip_rate",
    "backend_used",
    "solver_diagnostics",
)


def _join_values(values: list[str]) -> str:
    return ",".join(values) if values else "none"


def _flat_float_list(values: Any, field_name: str) -> list[float]:
    if hasattr(values, "detach"):
        values = values.detach().cpu().reshape(-1).tolist()
    elif hasattr(values, "tolist"):
        values = values.tolist()

    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError(f"{field_name} must be a sequence of numbers")

    result: list[float] = []
    for value in values:
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            result.extend(_flat_float_list(value, field_name))
        else:
            result.append(float(value))
    return result


def _finite_vector(sample: dict[str, Any], field_name: str, expected_length: int) -> None:
    values = _flat_float_list(sample[field_name], field_name)
    if len(values) != expected_length:
        raise ValueError(f"{field_name} must contain exactly {expected_length} values")
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{field_name} values must be finite")
    sample[field_name] = values


def _finite_rate(sample: dict[str, Any], field_name: str) -> None:
    value = float(sample[field_name])
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ValueError(f"{field_name} must be finite and within [0, 1]")
    sample[field_name] = value


def validate_ppo_koopman_sample(sample: dict[str, Any]) -> None:
    validate_koopman_sample(sample)

    missing = [field for field in REQUIRED_PPO_FIELDS if field not in sample]
    if missing:
        raise ValueError(f"Missing PPO/Koopman sample fields: {missing}")

    _finite_vector(sample, "policy_output", 4)
    _finite_vector(sample, "policy_output_clipped", 4)
    _finite_vector(sample, "base_reference", 5)
    _finite_vector(sample, "adapted_reference", 5)
    _finite_rate(sample, "policy_action_clip_rate")

    goal_match_error = float(sample["base_reference_goal_match_max_error"])
    if not math.isfinite(goal_match_error) or goal_match_error < 0.0:
        raise ValueError("base_reference_goal_match_max_error must be finite and non-negative")
    sample["base_reference_goal_match_max_error"] = goal_match_error

    if sample["adapter_mode"] != ADAPTER_MODE:
        raise ValueError(f"adapter_mode must be {ADAPTER_MODE!r}")
    if sample["action_semantics"] != ACTION_SEMANTICS:
        raise ValueError(f"action_semantics must be {ACTION_SEMANTICS!r}")
    if sample["adapter_quat_convention"] != ADAPTER_QUAT_CONVENTION:
        raise ValueError(f"adapter_quat_convention must be {ADAPTER_QUAT_CONVENTION!r}")
    if sample["ppo_evidence_level"] not in VALID_PPO_EVIDENCE_LEVELS:
        raise ValueError(f"ppo_evidence_level must be one of {list(VALID_PPO_EVIDENCE_LEVELS)}")

    for field_name in ("policy_mode", "backend_used"):
        if not isinstance(sample[field_name], str) or not sample[field_name].strip():
            raise ValueError(f"{field_name} must be a non-empty string")
    for field_name in ("adapter_diagnostics", "solver_diagnostics"):
        if not isinstance(sample[field_name], dict):
            raise ValueError(f"{field_name} must be a dictionary")

    guarded_evidence_levels = (
        PHASE5_EVIDENCE_LEVEL,
        PHASE5_1_MATCHED_EVIDENCE_LEVEL,
        PHASE5_2_MATCHED_EVIDENCE_LEVEL,
        PHASE5_3_MATCHED_EVIDENCE_LEVEL,
        PHASE5_4_MATCHED_EVIDENCE_LEVEL,
    )
    if sample["ppo_evidence_level"] in guarded_evidence_levels:
        required_phase5_fields = (
            "result_bucket",
            "checkpoint_provenance",
            "checkpoint_provenance_valid",
            "source_training_summary_path",
            "controller_path",
            "reward_profile",
        )
        if sample["ppo_evidence_level"] in (
            PHASE5_2_MATCHED_EVIDENCE_LEVEL,
            PHASE5_3_MATCHED_EVIDENCE_LEVEL,
            PHASE5_4_MATCHED_EVIDENCE_LEVEL,
        ):
            required_phase5_fields = required_phase5_fields + (
                "profile_id",
                "adapter_profile",
                "mpc_profile",
                "changed_axis",
            )
        if sample["ppo_evidence_level"] == PHASE5_4_MATCHED_EVIDENCE_LEVEL:
            required_phase5_fields = required_phase5_fields + (
                "phase5_4_track",
                "sweep_round",
                "parent_profile_id",
                "parameter_distance_from_parent",
                "changed_parameter_count",
                "parameter_step_count",
            )
        missing = [field for field in required_phase5_fields if field not in sample]
        if missing:
            raise ValueError(f"Missing Phase 5 retrained-policy provenance fields: {missing}")
        if sample["ppo_evidence_level"] == PHASE5_1_MATCHED_EVIDENCE_LEVEL:
            expected_provenance = PHASE5_1_CANDIDATE_CHECKPOINT_PROVENANCE
            expected_reward_profile = PHASE5_REWARD_PROFILE
        elif sample["ppo_evidence_level"] == PHASE5_2_MATCHED_EVIDENCE_LEVEL:
            expected_provenance = PHASE5_2_CANDIDATE_CHECKPOINT_PROVENANCE
            profile = resolve_phase52_profile(
                profile_id=str(sample["profile_id"]),
                reward_profile=str(sample["reward_profile"]),
                adapter_profile=str(sample["adapter_profile"]),
                mpc_profile=str(sample["mpc_profile"]),
                changed_axis=str(sample["changed_axis"]),
            )
            expected_reward_profile = profile.reward_profile
        elif sample["ppo_evidence_level"] == PHASE5_3_MATCHED_EVIDENCE_LEVEL:
            expected_provenance = (
                PHASE5_3_CANDIDATE_CHECKPOINT_PROVENANCE,
                PHASE5_3_EXTENDED_CHECKPOINT_PROVENANCE,
            )
            profile = resolve_phase53_profile(
                profile_id=str(sample["profile_id"]),
                reward_profile=str(sample["reward_profile"]),
                adapter_profile=str(sample["adapter_profile"]),
                mpc_profile=str(sample["mpc_profile"]),
                changed_axis=str(sample["changed_axis"]),
            )
            expected_reward_profile = profile.reward_profile
        elif sample["ppo_evidence_level"] == PHASE5_4_MATCHED_EVIDENCE_LEVEL:
            expected_provenance = (
                PHASE5_4_CANDIDATE_CHECKPOINT_PROVENANCE,
                PHASE5_4_REFINEMENT_CHECKPOINT_PROVENANCE,
            )
            profile = resolve_phase54_profile(
                profile_id=str(sample["profile_id"]),
                reward_profile=str(sample["reward_profile"]),
                adapter_profile=str(sample["adapter_profile"]),
                mpc_profile=str(sample["mpc_profile"]),
                changed_axis=str(sample["changed_axis"]),
            )
            expected_reward_profile = profile.reward_profile
            if sample["phase5_4_track"] != profile.track:
                raise ValueError("phase5_4_track does not match the Phase 5.4 profile contract")
            if sample["sweep_round"] != profile.sweep_round:
                raise ValueError("sweep_round does not match the Phase 5.4 profile contract")
            if sample["parent_profile_id"] != profile.parent_profile_id:
                raise ValueError("parent_profile_id does not match the Phase 5.4 profile contract")
        else:
            expected_provenance = PHASE5_CHECKPOINT_PROVENANCE
            expected_reward_profile = PHASE5_REWARD_PROFILE
        expected_values = {
            "result_bucket": PHASE5_RESULT_BUCKET,
            "checkpoint_provenance": expected_provenance,
            "checkpoint_provenance_valid": True,
            "controller_path": PHASE5_CONTROLLER_PATH,
            "reward_profile": expected_reward_profile,
        }
        for field_name, expected in expected_values.items():
            if isinstance(expected, tuple):
                if sample[field_name] not in expected:
                    raise ValueError(f"{field_name} must be one of {list(expected)!r} for {sample['ppo_evidence_level']}")
            elif sample[field_name] != expected:
                raise ValueError(f"{field_name} must be {expected!r} for {PHASE5_EVIDENCE_LEVEL}")
        if not isinstance(sample["source_training_summary_path"], str) or not sample[
            "source_training_summary_path"
        ].strip():
            raise ValueError("source_training_summary_path must be a non-empty string")


def load_ppo_koopman_samples(path: str | Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line)
            validate_ppo_koopman_sample(sample)
            samples.append(sample)
    validate_koopman_sequence(samples)
    return samples


def summarize_ppo_koopman_samples(samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    sample_list = list(samples)
    validate_koopman_sequence(sample_list)
    for sample in sample_list:
        validate_ppo_koopman_sample(sample)
    first = sample_list[0]
    last = sample_list[-1]
    return {
        "count": len(sample_list),
        "t_start": first["t"],
        "t_end": last["t"],
        "adapter_modes": sorted({sample["adapter_mode"] for sample in sample_list}),
        "ppo_evidence_levels": sorted({sample["ppo_evidence_level"] for sample in sample_list}),
        "policy_modes": sorted({sample["policy_mode"] for sample in sample_list}),
        "backend_used": sorted({sample["backend_used"] for sample in sample_list}),
        "controller_modes": sorted({sample["controller_mode"] for sample in sample_list}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize a PPO-driven EasyUUV Koopman JSONL log.")
    parser.add_argument("path", type=Path, help="Path to a PPO/Koopman JSONL log.")
    args = parser.parse_args(argv)

    try:
        samples = load_ppo_koopman_samples(args.path)
        summary = summarize_ppo_koopman_samples(samples)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"OK: {summary['count']} PPO/Koopman samples")
    print(f"t_start={summary['t_start']:.9f} t_end={summary['t_end']:.9f}")
    print(f"adapter_modes={_join_values(summary['adapter_modes'])}")
    print(f"ppo_evidence_levels={_join_values(summary['ppo_evidence_levels'])}")
    print(f"policy_modes={_join_values(summary['policy_modes'])}")
    print(f"backend_used={_join_values(summary['backend_used'])}")
    print(f"controller_modes={_join_values(summary['controller_modes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
