from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_easyuuv_env_exposes_controller_mode_and_pre_thrust_pwm_cache():
    source = (PROJECT_ROOT / "easyuuv_env.py").read_text(encoding="utf-8")

    assert "controller_mode = 'legacy'" in source
    assert "_last_pwm_8d = torch.zeros(self.num_envs, 8" in source
    assert "self._last_pwm_8d = motorValues.clone()" in source
    assert "motorValues[torch.abs(motorValues) < threshold] = 0" in source
    assert source.index("self._last_pwm_8d = motorValues.clone()") < source.index(
        "motorValues[torch.abs(motorValues) < threshold] = 0"
    )


def test_workflows_offer_consistent_koopman_log_arguments():
    required = [
        "workflows/play_controller.py",
        "workflows/play_eval.py",
        "workflows/play_eval_step.py",
        "workflows/play_eval_task2.py",
    ]

    for relative_path in required:
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "--koopman_log_path" in source
        assert "KoopmanDataLogger" in source
        assert "record_koopman_step" in source
