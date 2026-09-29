"""Validate a frozen release plus exactly the three versioned MPC additions."""
import hashlib
from pathlib import Path
import sys


ADDON_MODULES = {
    'koopman.compiled_forecast_v64': 'koopman/compiled_forecast_v64.py',
    'koopman.bounded_mpc_v64': 'koopman/bounded_mpc_v64.py',
    'koopman.compiled_recovery_v64': 'koopman/compiled_recovery_v64.py',
}


def check_loaded_sources(root, release, addon, manifest, *, modules=None):
    """Manifest integrity must be established by the launch supervisor first.

    Never relax the frozen-file checks or permit arbitrary addon modules.
    This helper is loaded as a separately supervisor-verified entrypoint helper.
    """
    root, addon = Path(root).resolve(), Path(addon).resolve()
    if root == addon or addon.is_relative_to(root) or root.is_relative_to(addon):
        raise ValueError('runtime_addon_must_be_separate')
    result = {}
    for name, module in tuple((sys.modules if modules is None else modules).items()):
        if name.split('.')[0] not in ('workflows', 'koopman', 'easyuuv_nc'):
            continue
        filename = getattr(module, '__file__', None)
        if filename is None:
            continue
        path = Path(filename).resolve()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_relative_to(root):
            rel = path.relative_to(root).as_posix()
            expected = release['manifest']['files_sha256'].get(rel)
            source = 'frozen_release'
        elif name in ADDON_MODULES and path == (addon / ADDON_MODULES[name]).resolve():
            rel = ADDON_MODULES[name]
            expected = manifest['files_sha256'].get(rel)
            source = 'verified_addon'
        else:
            raise ValueError('runtime_import_outside_release:' + name)
        if expected != actual:
            raise ValueError('runtime_import_not_frozen:' + name)
        result[name] = dict(relative_path=rel, sha256=actual, source=source)
    return result
