import hashlib
from types import SimpleNamespace

import pytest


def fixture(tmp_path):
    root = tmp_path / 'release'; root.mkdir()
    addon = tmp_path / 'addon'; addon.mkdir()
    frozen = root / 'koopman' / 'old.py'; frozen.parent.mkdir()
    frozen.write_text('old')
    new = addon / 'koopman' / 'compiled_forecast_v64.py'; new.parent.mkdir()
    new.write_text('new')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    release = {'manifest': {'files_sha256': {'koopman/old.py': digest(frozen)}}}
    manifest = {'files_sha256': {'koopman/compiled_forecast_v64.py': digest(new)}}
    modules = {'koopman.old': SimpleNamespace(__file__=str(frozen)),
               'koopman.compiled_forecast_v64': SimpleNamespace(__file__=str(new))}
    return root, addon, release, manifest, modules


def test_exact_extension_and_frozen_sources(tmp_path):
    from workflows.runtime_addon_v64 import check_loaded_sources
    root, addon, release, manifest, modules = fixture(tmp_path)
    result = check_loaded_sources(root, release, addon, manifest, modules=modules)
    assert result['koopman.old']['source'] == 'frozen_release'
    assert result['koopman.compiled_forecast_v64']['source'] == 'verified_addon'


@pytest.mark.parametrize('corruption', ['addon', 'frozen', 'unlisted', 'wrong_name', 'outside'])
def test_reject_source_drift(tmp_path, corruption):
    from workflows.runtime_addon_v64 import check_loaded_sources
    root, addon, release, manifest, modules = fixture(tmp_path)
    if corruption in ('addon', 'frozen'):
        key = 'koopman.old' if corruption == 'frozen' else 'koopman.compiled_forecast_v64'
        from pathlib import Path
        Path(modules[key].__file__).write_text('changed')
    elif corruption == 'unlisted':
        manifest['files_sha256'].clear()
    elif corruption == 'wrong_name':
        modules['koopman.foreign'] = modules.pop('koopman.compiled_forecast_v64')
    else:
        p = tmp_path / 'compiled_forecast_v64.py'; p.write_text('new')
        modules['koopman.compiled_forecast_v64'] = SimpleNamespace(__file__=str(p))
    with pytest.raises(ValueError):
        check_loaded_sources(root, release, addon, manifest, modules=modules)
