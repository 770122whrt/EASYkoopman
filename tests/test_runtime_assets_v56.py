"""Read-only asset admission tests; no model fitting or formal test access."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
HANDOFF_REL = 'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
HANDOFF_SHA = '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'


def location():
    from workflows.runtime_assets_v56 import AssetLocation
    handoff = json.loads((ROOT/HANDOFF_REL).read_text())
    source = Path(handoff['frozen_source_directory']).relative_to(ROOT)
    return AssetLocation(str(ROOT), source.as_posix(), (source.parent/'inputs').as_posix(), HANDOFF_SHA)


def test_existing_assets_admitted_only_with_original_handoff_model_and_fit_binding():
    from workflows.runtime_assets_v56 import load_assets
    assets = load_assets(location(), model_key='nonlinear__pooled')
    assert len(assets.domains) == 8
    assert assets.model_sha256 == '9704fbb8cc0a40ebc74f3f4d2727cba0f52a0b4221ec6e71d4f5526d98a088f4'
    for name, domain in assets.domains.items():
        assert domain._verified_fit and len(domain.fit_sources) == 3
        assert domain.model_id == assets.model_sha256
        from koopman.prepared_projected_v40 import _context_key
        assert _context_key(assets.context(name)) == domain.context_key
    assert assets.handoff['closed_loop_controller_promoted'] is False


@pytest.mark.parametrize('bad', ['../source', '/source', 'C:/source', 'a\\b', '', 'a/../b', '//server/path'])
def test_portable_path_cannot_escape_explicit_project_root(bad):
    from workflows.runtime_assets_v56 import AssetLocation
    with pytest.raises(ValueError, match='relative'):
        AssetLocation(str(ROOT), bad, 'inputs', HANDOFF_SHA)


def test_handoff_hash_checked_before_following_any_embedded_paths(monkeypatch):
    from workflows.runtime_assets_v56 import load_assets
    loc = replace(location(), handoff_sha256='0'*64)
    with pytest.raises(ValueError, match='handoff_hash'):
        load_assets(loc, model_key='nonlinear__pooled')


def test_missing_model_key_cannot_be_admitted():
    from workflows.runtime_assets_v56 import load_assets
    with pytest.raises(ValueError, match='eligible_model'):
        load_assets(location(), model_key='unapproved-model')


def test_override_wrong_source_is_not_fallback_to_old_absolute_path(tmp_path):
    from workflows.runtime_assets_v56 import load_assets
    loc = replace(location(), source_relative='does-not-exist')
    with pytest.raises((ValueError, FileNotFoundError)):
        load_assets(loc, model_key='nonlinear__pooled')


def test_heldout_model_cannot_acquire_heldout_fit_support():
    from workflows.runtime_assets_v56 import load_assets
    assets = load_assets(location(), model_key='nonlinear__heldout-base')
    assert 'base' not in assets.domains and len(assets.domains) == 7
    with pytest.raises(ValueError, match='configuration_not_supported'):
        assets.context('base')


def test_portable_worker_binding_rejects_changed_model_or_support_before_compilation():
    from workflows.runtime_assets_v56 import load_assets, PortableWorkerSpec, portable_model_factory
    assets = load_assets(location(), model_key='nonlinear__pooled')
    spec = assets.worker_spec('base', compiler_directory=None)
    assert isinstance(spec, PortableWorkerSpec)
    for bad in (replace(spec, model_sha256='0'*64), replace(spec, support_id='0'*64)):
        with pytest.raises(ValueError, match='worker_binding'):
            portable_model_factory(bad)


def test_loaded_arrays_and_context_are_owned_across_calls():
    from workflows.runtime_assets_v56 import load_assets
    assets = load_assets(location(), model_key='nonlinear__pooled')
    a = assets.context('base'); b = assets.context('base')
    assert a is not b and not np.shares_memory(a.inertia, b.inertia)
    before = hashlib.sha256((ROOT/HANDOFF_REL).read_bytes()).hexdigest()
    assets.handoff['frozen_source_directory'] = 'deliberate_local_copy_mutation'
    assert hashlib.sha256((ROOT/HANDOFF_REL).read_bytes()).hexdigest() == before == HANDOFF_SHA


def test_asset_packager_refuses_existing_destination(tmp_path):
    from workflows.runtime_assets_v56 import prepare_assets
    marker = tmp_path/'keep.txt'; marker.write_text('existing work')
    with pytest.raises(FileExistsError):
        prepare_assets(location(), tmp_path)
    assert marker.read_text() == 'existing work'


def test_asset_packager_checks_byte_cap_before_creating_destination(tmp_path):
    from workflows.runtime_assets_v56 import prepare_assets
    target = tmp_path/'new'
    with pytest.raises(ValueError, match='size_limit'):
        prepare_assets(location(), target, maximum_bytes=1)
    assert not target.exists()
