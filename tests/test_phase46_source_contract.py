from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_train_workflow_uses_isaaclab2_app_shim_before_post_app_imports():
    source = read_source("workflows/train.py")

    assert "from isaaclab_app import AppLauncher" in source
    assert "from omni.isaac.lab.app import AppLauncher" not in source
    assert "app_launcher = AppLauncher(args_cli)" in source
    assert source.index("app_launcher = AppLauncher(args_cli)") < source.index("import gymnasium as gym")
    assert source.index("app_launcher = AppLauncher(args_cli)") < source.index(
        "from easyuuv_task_registration import register_gym_tasks"
    )


def test_train_workflow_exposes_phase46_checkpoint_save_policy():
    source = read_source("workflows/train.py")

    assert "--save_interval" in source
    assert "agent_cfg.save_interval = args_cli.save_interval" in source
    assert "--result_bucket" in source
    assert 'default="legacy_ppo_baseline"' in source
    assert "--ppo_evidence_level" in source
    assert 'default="training_entrypoint_only"' in source


def test_train_workflow_sets_legacy_controller_baseline_for_phase46():
    source = read_source("workflows/train.py")

    assert 'env_cfg.controller_mode = "legacy"' in source
    assert 'env_cfg.control_method = "Ssurface"' in source
    assert "reward_profile" in source
    assert "legacy_easyuuv_v0" in source


def test_phase46_workflows_use_isaaclab2_parse_env_cfg_signature():
    for path in ("workflows/train.py", "workflows/play_eval.py", "workflows/gen_policy.py"):
        source = read_source(path)
        assert "def parse_env_config(" in source
        assert "device=getattr(args_cli, \"device\"" in source
        assert "use_gpu=" not in source


def test_play_eval_uses_isaaclab2_app_shim_and_compat_imports():
    source = read_source("workflows/play_eval.py")

    assert "from isaaclab_app import AppLauncher" in source
    assert "from omni.isaac.lab.app import AppLauncher" not in source
    assert "from isaaclab_compat import" in source
    assert "app_launcher = AppLauncher(args_cli)" in source
    assert source.index("app_launcher = AppLauncher(args_cli)") < source.index("import gymnasium as gym")


def test_play_eval_writes_phase46_legacy_summary_sidecar():
    source = read_source("workflows/play_eval.py")

    assert "--phase46_summary_path" in source
    assert "write_phase46_legacy_summary" in source
    assert '"result_bucket": args_cli.result_bucket' in source
    assert '"ppo_evidence_level": args_cli.ppo_evidence_level' in source
    assert "legacy_ppo_baseline" in source
    assert "checkpoint_smoke" in source
    assert "legacy/Ssurface" in source


def test_play_eval_does_not_export_policy_unless_requested():
    source = read_source("workflows/play_eval.py")

    assert "--export_policy" in source
    assert "if args_cli.export_policy:" in source


def test_gen_policy_uses_isaaclab2_app_shim_and_compat_imports():
    source = read_source("workflows/gen_policy.py")

    assert "from isaaclab_app import AppLauncher" in source
    assert "from omni.isaac.lab.app import AppLauncher" not in source
    assert "from isaaclab_compat import" in source
    assert "app_launcher = AppLauncher(args_cli)" in source
    assert source.index("app_launcher = AppLauncher(args_cli)") < source.index("import gymnasium as gym")
