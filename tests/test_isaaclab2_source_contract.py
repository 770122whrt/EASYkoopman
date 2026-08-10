from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_compat_layer_documents_isaaclab2_and_legacy_imports():
    compat_source = read_source("isaaclab_compat.py")
    app_source = read_source("isaaclab_app.py")

    assert "from isaaclab.app import AppLauncher" in app_source
    assert "from omni.isaac.lab.app import AppLauncher" in app_source
    assert "import isaaclab.sim as sim_utils" in compat_source
    assert "from omni.isaac.lab import sim as sim_utils" in compat_source
    assert "from isaaclab_rl.rsl_rl import" in compat_source
    assert "from omni.isaac.lab_tasks.utils.wrappers.rsl_rl import" in compat_source


def test_direct_controller_starts_app_before_task_registration():
    source = read_source("workflows/play_controller.py")

    assert "from isaaclab_app import AppLauncher" in source
    assert "simulation_app = app_launcher.app" in source
    assert "register_gym_tasks()" in source
    assert source.index("simulation_app = app_launcher.app") < source.index("register_gym_tasks()")


def test_direct_controller_does_not_duplicate_applauncher_cli_flags():
    source = read_source("workflows/play_controller.py")

    assert 'parser.add_argument("--cpu"' not in source
    assert 'getattr(args_cli, "cpu", False)' in source


def test_direct_controller_has_stage_logging_and_short_smoke_flags():
    source = read_source("workflows/play_controller.py")

    assert "def log_stage(" in source
    assert "flush=True" in source
    assert "--steps_per_action" in source
    assert "--max_goals" in source
    assert "--trajectory_type" in source
    assert "--trajectory_cycles" in source
    assert "def build_goal_list(" in source
    assert "Creating Gym environment" in source
    assert "Gym environment created" in source


def test_direct_controller_builds_env_cfg_without_registry_parser():
    source = read_source("workflows/play_controller.py")

    assert "from easyuuv_env import EasyUUVEnvCfg" in source
    assert "env_cfg = EasyUUVEnvCfg()" in source
    assert "parse_env_cfg(" not in source


def test_direct_controller_uses_reset_when_public_observation_api_is_missing():
    source = read_source("workflows/play_controller.py")

    assert "result = env.reset()" in source
    assert 'hasattr(env.unwrapped, "get_observations")' in source


def test_direct_controller_does_not_require_ppo_wrapper_or_checkpoint():
    source = read_source("workflows/play_controller.py")
    forbidden = [
        "OnPolicyRunner",
        "RslRlVecEnvWrapper",
        "get_checkpoint_path",
        "export_policy_as_jit",
        "export_policy_as_onnx",
        "parse_rsl_rl_cfg",
    ]

    for token in forbidden:
        assert token not in source

    assert "step_policy_obs(env, action)" in source


def test_task_registration_uses_callable_entrypoint():
    source = read_source("easyuuv_task_registration.py")

    assert 'id="EasyUUV-Direct-v1"' in source
    assert "entry_point=EasyUUVEnv" in source
    assert "register_gym_tasks" in source
    assert "EasyUUV-Isaac-Simulation" not in source


def test_package_import_does_not_register_task_before_app_startup():
    source = read_source("__init__.py")

    assert "def register_gym_tasks(" in source
    assert "easyuuv_task_registration import register_gym_tasks as" in source
    assert "\nregister_gym_tasks()\n" not in source


def test_core_direct_path_uses_compat_layer_instead_of_old_namespace():
    migrated_files = [
        "easyuuv_env.py",
        "assets/easyuuv.py",
        "thruster_dynamics.py",
        "rigid_body_hydrodynamics.py",
        "asymmetric_noise_cfg.py",
        "agents/rsl_rl_ppo_cfg.py",
        "workflows/cli_args.py",
    ]

    for relative_path in migrated_files:
        assert "omni.isaac.lab" not in read_source(relative_path), relative_path


def test_easyuuv_env_cfg_declares_isaaclab2_spaces():
    source = read_source("easyuuv_env.py")

    assert "observation_space = 9" in source
    assert "action_space = 4" in source


def test_easyuuv_asset_disables_usd_articulation_root_for_rigid_object():
    source = read_source("assets/easyuuv.py")

    assert "ArticulationRootPropertiesCfg" in source
    assert "articulation_enabled=False" in source
