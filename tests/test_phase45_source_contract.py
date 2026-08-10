from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ppo_koopman_workflow_preserves_app_launcher_import_order():
    source = (PROJECT_ROOT / "workflows" / "play_ppo_koopman.py").read_text(encoding="utf-8")

    assert "from isaaclab_app import AppLauncher" in source
    assert "app_launcher = AppLauncher(args_cli)" in source
    assert source.index("app_launcher = AppLauncher(args_cli)") < source.index("import gymnasium as gym")
    assert source.index("app_launcher = AppLauncher(args_cli)") < source.index(
        "from easyuuv_task_registration import register_gym_tasks"
    )


def test_ppo_koopman_workflow_preflights_checkpoint_before_isaac_app_start():
    source = (PROJECT_ROOT / "workflows" / "play_ppo_koopman.py").read_text(encoding="utf-8")

    assert "preflight_policy_mode(args_cli)" in source
    assert source.index("preflight_policy_mode(args_cli)") < source.index("app_launcher = AppLauncher(args_cli)")
    assert "No PPO checkpoint found before Isaac app startup" in source


def test_ppo_koopman_workflow_declares_guarded_adapter_contract():
    source = (PROJECT_ROOT / "workflows" / "play_ppo_koopman.py").read_text(encoding="utf-8")

    assert "--policy_mode" in source
    assert "stub" in source
    assert "checkpoint" in source
    assert "training_smoke" in source
    assert "heuristic_reference_delta_v0" in source
    assert "stub_only" in source
    assert "checkpoint_smoke" in source
    assert "training_entrypoint_only" in source
    assert "paper_lifted_edmd" not in source


def test_ppo_koopman_workflow_refreshes_reference_before_step():
    source = (PROJECT_ROOT / "workflows" / "play_ppo_koopman.py").read_text(encoding="utf-8")

    assert "set_koopman_reference(env.unwrapped, adapter_output.adapted_reference_5d)" in source
    assert "obs = step_policy_obs(env, policy_action)" in source
    assert source.index("set_koopman_reference(env.unwrapped, adapter_output.adapted_reference_5d)") < source.index(
        "obs = step_policy_obs(env, policy_action)"
    )


def test_ppo_koopman_workflow_defaults_to_direct_state_manifest_contract():
    source = (PROJECT_ROOT / "workflows" / "play_ppo_koopman.py").read_text(encoding="utf-8")

    assert "--koopman_manifest_path" in source
    assert "verify_koopman_manifest_contract(args_cli.koopman_manifest_path)" in source
    assert "model_class" in source
    assert "controller_mode = args_cli.controller_mode" in source
    assert 'default="koopman_mpc"' in source
