import omni.isaac.lab.sim as sim_utils

from omni.isaac.lab.assets import RigidObjectCfg

import os
# easyuuv_nc 布局：本文件在 env/assets/，共享资产统一放在包根 easyuuv_nc/data/ 下。
USD_PATH = os.path.join(os.path.dirname(__file__), "../../data/embodiment/embodiment.usd")

WARPAUV_CFG = RigidObjectCfg(
    prim_path="{ENV_REGEX_NS}/Robot",
    spawn=sim_utils.UsdFileCfg(
        usd_path=USD_PATH,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            max_depenetration_velocity=10.0,
            enable_gyroscopic_forces=True,
        ),
        copy_from_source=False,
    ),
    init_state=RigidObjectCfg.InitialStateCfg(
        pos=(0.0, 0.0, 5),
    )
)
"""Configuration for the WarpAUV."""
