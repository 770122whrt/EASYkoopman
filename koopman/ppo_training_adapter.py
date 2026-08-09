from __future__ import annotations

from typing import Any

from koopman.policy_adapter import ADAPTER_MODE, PolicyAdapterConfig, adapt_policy_reference
from koopman.phase5_2_profiles import (
    PHASE5_2_CANDIDATE_CHECKPOINT_PROVENANCE,
    PHASE5_2_CANDIDATE_EVIDENCE_LEVEL,
    PHASE5_2_EVIDENCE_LEVELS,
    PHASE5_2_MATCHED_EVIDENCE_LEVEL,
    PHASE5_2_PROVENANCE_BY_EVIDENCE_LEVEL,
    PHASE5_2_SENTINEL_CHECKPOINT_PROVENANCE,
    PHASE5_2_SENTINEL_EVIDENCE_LEVEL,
    PHASE5_2_TRAINING_EVIDENCE_LEVELS,
)


PHASE5_RESULT_BUCKET = "retrained_ppo_koopman_mpc"
PHASE5_EVIDENCE_LEVEL = "retrained_policy_smoke"
PHASE5_CHECKPOINT_PROVENANCE = "phase5_train_koopman_mpc"
PHASE5_CONTROLLER_PATH = "koopman_mpc/direct_state"
PHASE5_REWARD_PROFILE = "legacy_easyuuv_v0"
PHASE5_BASE_REFERENCE_SOURCE = "env_goal_quat_plus_zero_depth"
PHASE5_DEPTH_REFERENCE_SOURCE = "zero_depth_default"
PHASE5_1_SENTINEL_EVIDENCE_LEVEL = "stability_sentinel"
PHASE5_1_CANDIDATE_EVIDENCE_LEVEL = "stability_candidate"
PHASE5_1_MATCHED_EVIDENCE_LEVEL = "matched_stability_eval"
PHASE5_1_TRAINING_EVIDENCE_LEVELS = (
    PHASE5_1_SENTINEL_EVIDENCE_LEVEL,
    PHASE5_1_CANDIDATE_EVIDENCE_LEVEL,
)
PHASE5_1_EVIDENCE_LEVELS = PHASE5_1_TRAINING_EVIDENCE_LEVELS + (PHASE5_1_MATCHED_EVIDENCE_LEVEL,)
PHASE5_1_SENTINEL_CHECKPOINT_PROVENANCE = "phase5_1_stability_sentinel"
PHASE5_1_CANDIDATE_CHECKPOINT_PROVENANCE = "phase5_1_stability_candidate"
PHASE5_1_PROVENANCE_BY_EVIDENCE_LEVEL = {
    PHASE5_1_SENTINEL_EVIDENCE_LEVEL: PHASE5_1_SENTINEL_CHECKPOINT_PROVENANCE,
    PHASE5_1_CANDIDATE_EVIDENCE_LEVEL: PHASE5_1_CANDIDATE_CHECKPOINT_PROVENANCE,
}


class Phase5KoopmanReferenceWrapper:
    """Refresh the Koopman reference from PPO actions on the training step path.

    RSL-RL owns the rollout loop inside `OnPolicyRunner.learn()`, so Phase 5
    needs the adapter at the environment `step(action_4d)` boundary instead of
    in an outer script loop.
    """

    def __init__(
        self,
        env: Any,
        *,
        adapter_config: PolicyAdapterConfig | None = None,
        ppo_evidence_level: str = PHASE5_EVIDENCE_LEVEL,
        fail_fast_num_envs: int = 1,
    ) -> None:
        self.env = env
        self.adapter_config = adapter_config or PolicyAdapterConfig()
        self.ppo_evidence_level = ppo_evidence_level
        self.fail_fast_num_envs = fail_fast_num_envs
        self.adapter_refresh_count = 0
        self.adapter_refresh_before_env_step = False
        self.last_adapter_diagnostics: dict[str, Any] = {}
        self.last_adapted_reference_5d: list[float] | None = None
        self.last_policy_output_4d_clipped: list[float] | None = None

    @property
    def unwrapped(self) -> Any:
        return getattr(self.env, "unwrapped", self.env)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.env, name)

    def step(self, actions: Any) -> Any:
        target_env = self.unwrapped
        self._validate_single_env(target_env)
        action_matrix = self._action_matrix(actions)
        base_reference = self._base_reference_5d(target_env)
        goal_quat = self._goal_quat(target_env)

        adapter_output = adapt_policy_reference(
            action_matrix[0],
            base_reference,
            observation_goal_quat=goal_quat,
            config=self.adapter_config,
            ppo_evidence_level=self.ppo_evidence_level,
        )
        self._set_koopman_reference(target_env, adapter_output.adapted_reference_5d)
        self.adapter_refresh_count += 1
        self.adapter_refresh_before_env_step = True
        self.last_adapter_diagnostics = dict(adapter_output.diagnostics)
        self.last_adapter_diagnostics.update(
            {
                "base_reference_source": PHASE5_BASE_REFERENCE_SOURCE,
                "depth_reference_source": PHASE5_DEPTH_REFERENCE_SOURCE,
                "adapter_refresh_path": "Phase5KoopmanReferenceWrapper.step",
            }
        )
        self.last_adapted_reference_5d = list(adapter_output.adapted_reference_5d)
        self.last_policy_output_4d_clipped = list(adapter_output.policy_output_4d_clipped)
        return self.env.step(actions)

    def close(self) -> Any:
        if hasattr(self.env, "close"):
            return self.env.close()
        return None

    def seed(self, seed: int | None = None) -> Any:
        if hasattr(self.env, "seed"):
            return self.env.seed(seed)
        return None

    def phase5_summary_fields(self) -> dict[str, Any]:
        reward_components = getattr(self.unwrapped, "_last_phase5_2_reward_components", {}) or {}
        return {
            "adapter_mode": ADAPTER_MODE,
            "adapter_refresh_path": "Phase5KoopmanReferenceWrapper.step",
            "adapter_refresh_count": self.adapter_refresh_count,
            "adapter_refresh_before_env_step": self.adapter_refresh_before_env_step,
            "base_reference_source": PHASE5_BASE_REFERENCE_SOURCE,
            "depth_reference_source": PHASE5_DEPTH_REFERENCE_SOURCE,
            "base_reference_goal_match_max_error": self.last_adapter_diagnostics.get(
                "base_reference_goal_match_max_error"
            ),
            "policy_action_clip_rate": self.last_adapter_diagnostics.get("policy_action_clip_rate"),
            "phase5_2_reward_components_available": bool(reward_components),
            "phase5_2_last_reward_components": reward_components,
        }

    def _validate_single_env(self, target_env: Any) -> None:
        num_envs = int(getattr(target_env, "num_envs", 1))
        if num_envs != self.fail_fast_num_envs:
            raise ValueError(
                "Phase 5 training adapter currently requires num_envs=1 until vectorized reference refresh is tested"
            )

    def _action_matrix(self, actions: Any) -> Any:
        if hasattr(actions, "detach"):
            matrix = actions.detach().reshape(-1, 4)
            if tuple(matrix.shape) != (1, 4):
                raise ValueError("Phase 5 training adapter expects action_4d with shape (1, 4)")
            return matrix
        matrix = [list(row) for row in actions]
        if len(matrix) != 1 or len(matrix[0]) != 4:
            raise ValueError("Phase 5 training adapter expects action_4d with shape (1, 4)")
        return matrix

    def _goal_quat(self, target_env: Any) -> Any:
        if not hasattr(target_env, "_goal"):
            raise AttributeError("Phase 5 training adapter requires env._goal for base reference construction")
        goal = target_env._goal
        return goal[0].detach() if hasattr(goal[0], "detach") else goal[0]

    def _base_reference_5d(self, target_env: Any) -> list[float]:
        goal_quat = self._goal_quat(target_env).detach().cpu().reshape(-1).tolist()
        if len(goal_quat) != 4:
            raise ValueError("env._goal must expose a 4D goal quaternion")
        return [0.0] + [float(value) for value in goal_quat]

    def _set_koopman_reference(self, target_env: Any, reference: list[float]) -> None:
        target_env._koopman_reference_5d = target_env._goal.new_tensor(reference).reshape(1, 5)
