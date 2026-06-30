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
    assert "register_easyuuv_task()" in source
    assert source.index("simulation_app = app_launcher.app") < source.index("register_easyuuv_task()")


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
    assert "register_easyuuv_task" in source
    assert "EasyUUV-Isaac-Simulation" not in source


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
