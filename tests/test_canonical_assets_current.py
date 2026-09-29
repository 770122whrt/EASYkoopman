"""Asset path wiring only; the simulator config types are replaced for this check."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.mark.parametrize('file, name', [
    ('assets/easyuuv.py', 'EasyUUV_CFG'),
    ('easyuuv_nc/env/assets/warpauv.py', 'WARPAUV_CFG'),
])
def test_both_entrypoints_resolve_the_single_canonical_asset(file, name, monkeypatch):
    from easyuuv_nc.package_paths import EMBODIMENT_USD_PATH
    class Config:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    Config.InitialStateCfg = Config
    compat = ModuleType('isaaclab_compat')
    compat.RigidObjectCfg = Config
    compat.sim_utils = SimpleNamespace(UsdFileCfg=Config, RigidBodyPropertiesCfg=Config,
                                      ArticulationRootPropertiesCfg=Config)
    monkeypatch.setitem(sys.modules, 'isaaclab_compat', compat)
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('_asset_path_check', root / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resolved = Path(getattr(module, name).spawn.usd_path).resolve()
    assert resolved == EMBODIMENT_USD_PATH.resolve()
    assert resolved.is_file()
