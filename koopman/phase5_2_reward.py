from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Phase52RewardConfig:
    pwm_soft_limit: float = 0.90
    latency_ref_ms: float = 20.0
    latency_clip: float = 3.0
    w_fallback: float = 0.30
    w_pwm_sat: float = 0.20
    w_latency: float = 0.05
    w_action: float = 0.01
    w_delta_action: float = 0.02

    @classmethod
    def from_env_cfg(cls, cfg: Any) -> "Phase52RewardConfig":
        return cls(
            pwm_soft_limit=float(getattr(cfg, "phase5_2_pwm_soft_limit", cls.pwm_soft_limit)),
            latency_ref_ms=float(getattr(cfg, "phase5_2_latency_ref_ms", cls.latency_ref_ms)),
            latency_clip=float(getattr(cfg, "phase5_2_latency_clip", cls.latency_clip)),
            w_fallback=float(getattr(cfg, "phase5_2_w_fallback", cls.w_fallback)),
            w_pwm_sat=float(getattr(cfg, "phase5_2_w_pwm_sat", cls.w_pwm_sat)),
            w_latency=float(getattr(cfg, "phase5_2_w_latency", cls.w_latency)),
            w_action=float(getattr(cfg, "phase5_2_w_action", cls.w_action)),
            w_delta_action=float(getattr(cfg, "phase5_2_w_delta_action", cls.w_delta_action)),
        )


def _as_tensor_like(values: Any, like: Any) -> Any:
    if hasattr(values, "to") and hasattr(values, "reshape"):
        return values.to(device=like.device, dtype=like.dtype)
    return like.new_tensor(values)


def compute_phase52_reward_components(
    *,
    legacy_reward: Any,
    actions: Any,
    action_delta: Any,
    pwm: Any,
    fallback_used: Any,
    latency_ms: Any,
    config: Phase52RewardConfig | None = None,
) -> dict[str, Any]:
    config = config or Phase52RewardConfig()
    legacy_reward = legacy_reward.reshape(-1)
    actions = _as_tensor_like(actions, legacy_reward).reshape(legacy_reward.shape[0], -1)
    action_delta = _as_tensor_like(action_delta, legacy_reward).reshape(legacy_reward.shape[0], -1)
    pwm = _as_tensor_like(pwm, legacy_reward).reshape(legacy_reward.shape[0], -1)
    fallback = _as_tensor_like(fallback_used, legacy_reward).reshape(-1)
    latency = _as_tensor_like(latency_ms, legacy_reward).reshape(-1)

    if fallback.shape[0] != legacy_reward.shape[0]:
        fallback = fallback.repeat(legacy_reward.shape[0])[: legacy_reward.shape[0]]
    if latency.shape[0] != legacy_reward.shape[0]:
        latency = latency.repeat(legacy_reward.shape[0])[: legacy_reward.shape[0]]

    soft_limit = max(min(float(config.pwm_soft_limit), 0.999), 0.0)
    saturation_excess = ((abs(pwm) - soft_limit) / max(1.0 - soft_limit, 1e-6)).clamp(min=0.0)
    saturation_mean = saturation_excess.mean(dim=1)
    latency_ratio = ((latency - config.latency_ref_ms) / max(config.latency_ref_ms, 1e-6)).clamp(
        min=0.0,
        max=config.latency_clip,
    )

    fallback_penalty = config.w_fallback * fallback.clamp(min=0.0, max=1.0)
    pwm_saturation_penalty = config.w_pwm_sat * saturation_mean
    latency_penalty = config.w_latency * latency_ratio
    action_penalty = config.w_action * (actions * actions).sum(dim=1)
    delta_action_penalty = config.w_delta_action * (action_delta * action_delta).sum(dim=1)
    health_penalty = (
        fallback_penalty
        + pwm_saturation_penalty
        + latency_penalty
        + action_penalty
        + delta_action_penalty
    )

    return {
        "legacy_reward": legacy_reward,
        "fallback_penalty": fallback_penalty,
        "pwm_saturation_penalty": pwm_saturation_penalty,
        "latency_penalty": latency_penalty,
        "action_penalty": action_penalty,
        "delta_action_penalty": delta_action_penalty,
        "health_penalty": health_penalty,
        "total_reward": legacy_reward - health_penalty,
    }
