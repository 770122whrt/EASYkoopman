"""Compatibility imports for Isaac Lab 2.x with Isaac Lab 1.x fallback.

Import this module only after `AppLauncher` has started the Isaac app.
"""

from __future__ import annotations

try:
    import isaaclab.sim as sim_utils
    import isaaclab.utils.math as math_utils
    from isaaclab.assets import RigidObject, RigidObjectCfg
    from isaaclab.envs import DirectRLEnv, DirectRLEnvCfg
    from isaaclab.envs.ui import BaseEnvWindow
    from isaaclab.markers import (
        BLUE_ARROW_X_MARKER_CFG,
        CUBOID_MARKER_CFG,
        GREEN_ARROW_X_MARKER_CFG,
        RED_ARROW_X_MARKER_CFG,
        VisualizationMarkers,
    )
    from isaaclab.scene import InteractiveSceneCfg
    from isaaclab.sim import SimulationCfg
    from isaaclab.sim.spawners.from_files import GroundPlaneCfg, spawn_ground_plane
    from isaaclab.utils import configclass
    from isaaclab.utils.math import (
        convert_quat,
        euler_xyz_from_quat,
        normalize,
        quat_apply,
        quat_conjugate,
        quat_error_magnitude,
        quat_from_angle_axis,
        quat_from_euler_xyz,
        quat_inv,
        quat_mul,
        sample_uniform,
    )
    from isaaclab.utils.noise import (
        GaussianNoiseCfg,
        NoiseCfg,
        NoiseModel,
        NoiseModelCfg,
        NoiseModelWithAdditiveBias,
        NoiseModelWithAdditiveBiasCfg,
        gaussian_noise,
    )
    from isaaclab_tasks.utils import get_checkpoint_path, parse_env_cfg
    from isaaclab_tasks.utils.parse_cfg import load_cfg_from_registry
    from isaaclab_rl.rsl_rl import (
        RslRlOnPolicyRunnerCfg,
        RslRlPpoActorCriticCfg,
        RslRlPpoAlgorithmCfg,
        RslRlVecEnvWrapper,
        export_policy_as_jit,
        export_policy_as_onnx,
    )
except ImportError:
    from omni.isaac.lab import sim as sim_utils
    import omni.isaac.lab.utils.math as math_utils
    from omni.isaac.lab.assets import RigidObject, RigidObjectCfg
    from omni.isaac.lab.envs import DirectRLEnv, DirectRLEnvCfg
    from omni.isaac.lab.envs.ui import BaseEnvWindow
    from omni.isaac.lab.markers import (
        BLUE_ARROW_X_MARKER_CFG,
        CUBOID_MARKER_CFG,
        GREEN_ARROW_X_MARKER_CFG,
        RED_ARROW_X_MARKER_CFG,
        VisualizationMarkers,
    )
    from omni.isaac.lab.scene import InteractiveSceneCfg
    from omni.isaac.lab.sim import SimulationCfg
    from omni.isaac.lab.sim.spawners.from_files import GroundPlaneCfg, spawn_ground_plane
    from omni.isaac.lab.utils import configclass
    from omni.isaac.lab.utils.math import (
        convert_quat,
        euler_xyz_from_quat,
        normalize,
        quat_apply,
        quat_conjugate,
        quat_error_magnitude,
        quat_from_angle_axis,
        quat_from_euler_xyz,
        quat_inv,
        quat_mul,
        sample_uniform,
    )
    from omni.isaac.lab.utils.noise import (
        GaussianNoiseCfg,
        NoiseCfg,
        NoiseModel,
        NoiseModelCfg,
        NoiseModelWithAdditiveBias,
        NoiseModelWithAdditiveBiasCfg,
        gaussian_noise,
    )
    from omni.isaac.lab_tasks.utils import get_checkpoint_path, parse_env_cfg
    from omni.isaac.lab_tasks.utils.parse_cfg import load_cfg_from_registry
    from omni.isaac.lab_tasks.utils.wrappers.rsl_rl import (
        RslRlOnPolicyRunnerCfg,
        RslRlPpoActorCriticCfg,
        RslRlPpoAlgorithmCfg,
        RslRlVecEnvWrapper,
        export_policy_as_jit,
        export_policy_as_onnx,
    )
