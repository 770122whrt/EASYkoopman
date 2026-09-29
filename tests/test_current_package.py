"""Importing the package should not activate superseded model families."""
from pathlib import Path
import subprocess
import sys


def test_package_import_leaves_historical_runtime_unloaded():
    probe = subprocess.run([sys.executable, '-c',
        "import sys, koopman; assert 'koopman.runtime' not in sys.modules; "
        "assert 'koopman.mpc_controller' not in sys.modules; "
        "from koopman import KoopmanDataset; "
        "from koopman.dataset import KoopmanDataset as Original; "
        "assert KoopmanDataset is Original"],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert probe.returncode == 0, probe.stderr
