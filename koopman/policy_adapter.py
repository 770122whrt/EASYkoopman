from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any


ADAPTER_MODE = "heuristic_reference_delta_v0"
ACTION_SEMANTICS = "heuristic_reference_delta_v0_legacy_4d_as_reference_delta"
ADAPTER_QUAT_CONVENTION = "reference_frame_right_multiply"
VALID_PPO_EVIDENCE_LEVELS = (
    "stub_only",
    "checkpoint_smoke",
    "training_entrypoint_only",
    "retrained_policy_smoke",
    "stability_sentinel",
    "stability_candidate",
    "matched_stability_eval",
    "phase5_2_health_sentinel",
    "phase5_2_health_candidate",
    "phase5_2_matched_eval",
    "phase5_3_cross_sentinel",
    "phase5_3_cross_candidate",
    "phase5_3_cross_extended",
    "phase5_3_cross_matched_eval",
    "phase5_4_pareto_sentinel",
    "phase5_4_pareto_candidate",
    "phase5_4_pareto_refinement",
    "phase5_4_pareto_matched_eval",
)


@dataclass(frozen=True)
class PolicyAdapterConfig:
    policy_action_limit: float = 1.0
    rpy_delta_scale: tuple[float, float, float] = (0.35, 0.35, 0.35)
    depth_delta_scale: float = 0.5
    depth_bounds: tuple[float, float] = (-3.0, 3.0)


@dataclass(frozen=True)
class PolicyAdapterOutput:
    adapted_reference_5d: list[float]
    policy_output_4d_clipped: list[float]
    adapter_mode: str = ADAPTER_MODE
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _flat_float_list(values: Any, field_name: str) -> list[float]:
    if hasattr(values, "detach"):
        values = values.detach().cpu().reshape(-1).tolist()
    elif hasattr(values, "tolist"):
        values = values.tolist()

    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError(f"{field_name} must be a sequence of numbers")

    flattened: list[float] = []
    for value in values:
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            flattened.extend(_flat_float_list(value, field_name))
        else:
            flattened.append(float(value))
    return flattened


def _finite_vector(values: Any, field_name: str, expected_length: int) -> list[float]:
    vector = _flat_float_list(values, field_name)
    if len(vector) != expected_length:
        raise ValueError(f"{field_name} must contain exactly {expected_length} values")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError(f"{field_name} values must be finite")
    return vector


def _normalize_quat(quat: Sequence[float], field_name: str) -> list[float]:
    norm = math.sqrt(sum(value * value for value in quat))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError(f"{field_name} quaternion norm must be positive and finite")
    return [float(value / norm) for value in quat]


def _quat_from_euler_xyz(roll: float, pitch: float, yaw: float) -> list[float]:
    cr = math.cos(roll / 2.0)
    sr = math.sin(roll / 2.0)
    cp = math.cos(pitch / 2.0)
    sp = math.sin(pitch / 2.0)
    cy = math.cos(yaw / 2.0)
    sy = math.sin(yaw / 2.0)
    return [
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]


def _quat_mul(left: Sequence[float], right: Sequence[float]) -> list[float]:
    lw, lx, ly, lz = left
    rw, rx, ry, rz = right
    return [
        lw * rw - lx * rx - ly * ry - lz * rz,
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
    ]


def quaternion_sign_equivalent_max_error(left: Any, right: Any) -> float:
    left_quat = _normalize_quat(_finite_vector(left, "left", 4), "left")
    right_quat = _normalize_quat(_finite_vector(right, "right", 4), "right")
    same_sign = max(abs(a - b) for a, b in zip(left_quat, right_quat))
    opposite_sign = max(abs(a + b) for a, b in zip(left_quat, right_quat))
    return min(same_sign, opposite_sign)


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def adapt_policy_reference(
    policy_output_4d: Any,
    base_reference_5d: Any,
    *,
    observation_goal_quat: Any | None = None,
    config: PolicyAdapterConfig | None = None,
    ppo_evidence_level: str = "stub_only",
) -> PolicyAdapterOutput:
    if ppo_evidence_level not in VALID_PPO_EVIDENCE_LEVELS:
        raise ValueError(
            f"ppo_evidence_level must be one of {list(VALID_PPO_EVIDENCE_LEVELS)}, got {ppo_evidence_level!r}"
        )

    config = config or PolicyAdapterConfig()
    if config.policy_action_limit <= 0.0 or not math.isfinite(config.policy_action_limit):
        raise ValueError("policy_action_limit must be positive and finite")
    depth_min, depth_max = config.depth_bounds
    if depth_min > depth_max:
        raise ValueError("depth_bounds must be ordered as (min, max)")

    policy_output = _finite_vector(policy_output_4d, "policy_output_4d", 4)
    base_reference = _finite_vector(base_reference_5d, "base_reference_5d", 5)
    base_depth = base_reference[0]
    base_quat = _normalize_quat(base_reference[1:5], "base_reference_5d")

    limit = float(config.policy_action_limit)
    clipped = [_clip(value, -limit, limit) for value in policy_output]
    clip_count = sum(1 for raw, clipped_value in zip(policy_output, clipped) if not math.isclose(raw, clipped_value))
    clip_rate = clip_count / 4.0

    roll_delta = clipped[0] * config.rpy_delta_scale[0]
    pitch_delta = clipped[1] * config.rpy_delta_scale[1]
    yaw_delta = clipped[2] * config.rpy_delta_scale[2]
    depth_reference = _clip(base_depth + clipped[3] * config.depth_delta_scale, depth_min, depth_max)

    delta_quat = _normalize_quat(_quat_from_euler_xyz(roll_delta, pitch_delta, yaw_delta), "delta")
    adapted_quat = _normalize_quat(_quat_mul(base_quat, delta_quat), "adapted")
    adapted_reference = [depth_reference] + adapted_quat

    goal_quat = base_quat if observation_goal_quat is None else observation_goal_quat
    goal_match_error = quaternion_sign_equivalent_max_error(base_quat, goal_quat)

    diagnostics = {
        "adapter_mode": ADAPTER_MODE,
        "action_semantics": ACTION_SEMANTICS,
        "adapter_quat_convention": ADAPTER_QUAT_CONVENTION,
        "ppo_evidence_level": ppo_evidence_level,
        "policy_action_clip_count": clip_count,
        "policy_action_clip_rate": clip_rate,
        "base_reference_goal_match_max_error": goal_match_error,
        "depth_reference_clipped": not math.isclose(depth_reference, base_depth + clipped[3] * config.depth_delta_scale),
    }
    return PolicyAdapterOutput(
        adapted_reference_5d=adapted_reference,
        policy_output_4d_clipped=clipped,
        adapter_mode=ADAPTER_MODE,
        diagnostics=diagnostics,
    )
