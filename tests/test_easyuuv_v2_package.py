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
    package_source = read_source("easyuuv_nc/__init__.py")
    task_ids = re.findall(r'^\s*id="([^"]+)"', package_source, re.MULTILINE)

    assert task_ids == [
        "EasyUUV-Direct-v1",
        "EasyUUV-Direct-Parametric-v1",
        "EasyUUV-Direct-Parametric-SatObs-v1",
        "EasyUUV-Direct-Parametric-Wide256-v1",
    ]
    assert '_ENTRY = "easyuuv_nc.env:EasyUUVEnv"' in package_source


def test_v1_koopman_pwm_contract_remains_unchanged():
    model_source = read_source("koopman/model.py")
    mpc_source = read_source("koopman/mpc.py")

    assert "from koopman_data import PWM_DIM" in model_source
    assert "control_dim: int = PWM_DIM" in model_source
    assert "pwm_min: float = -1.0" in mpc_source
    assert "pwm_max: float = 1.0" in mpc_source
