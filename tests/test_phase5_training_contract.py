from pathlib import Path

import pytest
import torch

from koopman.ppo_training_adapter import Phase5KoopmanReferenceWrapper


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingEnv:
    def __init__(self, num_envs: int = 1):
        self.num_envs = num_envs
        self.device = torch.device("cpu")
        self._goal = torch.tensor([[1.0, 0.0, 0.0, 0.0]] * num_envs, dtype=torch.float32)
        self.events: list[str] = []
        self.unwrapped = self

    def step(self, actions):
        assert hasattr(self, "_koopman_reference_5d")
        self.events.append("underlying_step")
        return {"policy": torch.zeros((self.num_envs, 9), dtype=torch.float32)}


def test_phase5_wrapper_refreshes_reference_before_underlying_step():
    env = RecordingEnv()
    wrapper = Phase5KoopmanReferenceWrapper(env)

    wrapper.step(torch.tensor([[0.1, -0.2, 0.3, 0.4]], dtype=torch.float32))

    assert env.events == ["underlying_step"]
    assert env._koopman_reference_5d.shape == (1, 5)
    assert wrapper.adapter_refresh_count == 1
    assert wrapper.adapter_refresh_before_env_step is True
    assert wrapper.last_adapter_diagnostics["adapter_mode"] == "heuristic_reference_delta_v0"
    assert wrapper.last_adapter_diagnostics["base_reference_goal_match_max_error"] == pytest.approx(0.0)


def test_phase5_wrapper_fails_fast_for_unverified_vectorized_training():
    env = RecordingEnv(num_envs=2)
    wrapper = Phase5KoopmanReferenceWrapper(env)

    with pytest.raises(ValueError, match="num_envs=1"):
        wrapper.step(torch.zeros((2, 4), dtype=torch.float32))


def test_train_ppo_koopman_source_places_wrapper_before_rsl_rl_vec_wrapper():
    source = (PROJECT_ROOT / "workflows" / "train_ppo_koopman.py").read_text(encoding="utf-8")

    assert "Phase5KoopmanReferenceWrapper" in source
    assert "phase5_env = Phase5KoopmanReferenceWrapper(" in source
    assert "env = RslRlVecEnvWrapper(phase5_env)" in source
    assert source.index("phase5_env = Phase5KoopmanReferenceWrapper(") < source.index(
        "env = RslRlVecEnvWrapper(phase5_env)"
    )
    assert 'env_cfg.controller_mode = "koopman_mpc"' in source
    assert "controller_mode=koopman_mpc alone is not enough" in source
    assert "8D PWM" not in source
