from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "easyuuv_nc"


def read_source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_setuptools_discovery_supports_only_canonical_package():
    pyproject = read_source("pyproject.toml")
    discovery = pyproject.split("[tool.setuptools.packages.find]", maxsplit=1)[1].split("\n[", maxsplit=1)[0]

    assert re.search(r'^include\s*=\s*\["easyuuv_nc\*"\]\s*$', discovery, re.MULTILINE)
    assert "source" not in discovery
    assert ".planning" not in discovery
    assert "koopman" not in discovery
    assert 'easyuuv_nc = ["data/embodiment/*.usd", "data/embodiment/*.yaml"]' in pyproject


def test_embodiment_usd_resolves_inside_package():
    from easyuuv_nc.package_paths import PACKAGE_ROOT as INSTALLED_PACKAGE_ROOT
    from easyuuv_nc.package_paths import resolve_package_asset

    asset = resolve_package_asset("data/embodiment/embodiment.usd")

    assert asset.is_file()
    assert asset == INSTALLED_PACKAGE_ROOT / "data" / "embodiment" / "embodiment.usd"
    assert asset.is_relative_to(INSTALLED_PACKAGE_ROOT)


def test_asset_resolver_rejects_parent_traversal():
    from easyuuv_nc.package_paths import resolve_package_asset

    with pytest.raises(ValueError, match="inside the package"):
        resolve_package_asset("../koopman/model.py")


def test_asset_resolver_rejects_absolute_paths():
    from easyuuv_nc.package_paths import resolve_package_asset

    with pytest.raises(ValueError, match="relative"):
        resolve_package_asset((PACKAGE_ROOT / "data" / "embodiment" / "embodiment.usd").resolve())


def test_subprocess_import_and_asset_lookup_ignore_current_working_directory():
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(PROJECT_ROOT), existing_pythonpath) if part
    )
    temp_root = PROJECT_ROOT / ".pytest-tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-cwd-", dir=temp_root) as temp_dir:
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "import easyuuv_nc; "
                    "from easyuuv_nc.package_paths import EMBODIMENT_USD_PATH; "
                    "print(Path(easyuuv_nc.__file__).resolve()); "
                    "print(EMBODIMENT_USD_PATH.resolve())"
                ),
            ],
            cwd=temp_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    assert probe.returncode == 0, probe.stderr
    package_file, asset_file = (Path(line) for line in probe.stdout.strip().splitlines())
    assert package_file == (PACKAGE_ROOT / "__init__.py").resolve()
    assert asset_file == (PACKAGE_ROOT / "data" / "embodiment" / "embodiment.usd").resolve()


def test_package_registers_exactly_four_canonical_gym_ids():
    registration_source = read_source("easyuuv_nc/task_registration.py")
    task_ids = re.findall(r'^\s*id="([^"]+)"', registration_source, re.MULTILINE)

    assert task_ids == [
        "EasyUUV-Direct-v1",
        "EasyUUV-Direct-Parametric-v1",
        "EasyUUV-Direct-Parametric-SatObs-v1",
        "EasyUUV-Direct-Parametric-Wide256-v1",
    ]
    assert '_ENTRY = "easyuuv_nc.env:EasyUUVEnv"' in registration_source


def test_cached_pre_app_package_can_register_idempotently_and_reject_conflicts():
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(PROJECT_ROOT), existing_pythonpath) if part
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            r'''
import sys
import types

registry = {}
gym = types.ModuleType("gymnasium")
gym.registry = registry

def register(*, id, entry_point, disable_env_checker, kwargs):
    registry[id] = types.SimpleNamespace(
        id=id,
        entry_point=entry_point,
        disable_env_checker=disable_env_checker,
        kwargs=dict(kwargs),
    )

gym.register = register
gym.spec = registry.__getitem__
sys.modules["gymnasium"] = gym

import easyuuv_nc.embodiments
import easyuuv_nc
assert "easyuuv_nc" in sys.modules
assert registry == {}

env = types.ModuleType("easyuuv_nc.env")
class EasyUUVEnv: pass
class EasyUUVEnvCfg: pass
class EasyUUVParametricEnvCfg: pass
class EasyUUVParametricSatObsEnvCfg: pass
class EasyUUVPPORunnerCfg: pass
class EasyUUVParametricPPORunnerCfg: pass
class EasyUUVParametricWide256PPORunnerCfg: pass
env.EasyUUVEnv = EasyUUVEnv
env.EasyUUVEnvCfg = EasyUUVEnvCfg
env.EasyUUVParametricEnvCfg = EasyUUVParametricEnvCfg
env.EasyUUVParametricSatObsEnvCfg = EasyUUVParametricSatObsEnvCfg
env.agents = types.SimpleNamespace(
    rsl_rl_ppo_cfg=types.SimpleNamespace(
        EasyUUVPPORunnerCfg=EasyUUVPPORunnerCfg,
        EasyUUVParametricPPORunnerCfg=EasyUUVParametricPPORunnerCfg,
        EasyUUVParametricWide256PPORunnerCfg=EasyUUVParametricWide256PPORunnerCfg,
    )
)
sys.modules["easyuuv_nc.env"] = env

expected_ids = easyuuv_nc.register_gym_tasks()
assert tuple(registry) == expected_ids
assert easyuuv_nc.register_gym_tasks() == expected_ids
registry[expected_ids[0]].entry_point = "conflicting.module:Env"
try:
    easyuuv_nc.register_gym_tasks()
except RuntimeError as exc:
    assert str(exc) == f"task_registration_conflict:{expected_ids[0]}"
else:
    raise AssertionError("conflicting task registration was accepted")
''',
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert probe.returncode == 0, probe.stderr


def test_v1_koopman_pwm_contract_remains_unchanged():
    model_source = read_source("koopman/model.py")
    mpc_source = read_source("koopman/mpc.py")

    assert "from koopman_data import PWM_DIM" in model_source
    assert "control_dim: int = PWM_DIM" in model_source
    assert "pwm_min: float = -1.0" in mpc_source
    assert "pwm_max: float = 1.0" in mpc_source
