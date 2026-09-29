"""Asset trust-chain rejection with temporary byte fixtures, not Isaac evidence."""
import hashlib
import json

import pytest

from workflows import runtime_assets as assets


def test_handoff_root_cannot_be_replaced_by_caller_digest(tmp_path):
    assert assets.HANDOFF_SHA256 == '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'
    location = assets.AssetLocation(str(tmp_path), '.', 'inputs', 'a'*64)
    with pytest.raises(ValueError, match='untrusted_handoff'):
        assets.load_assets(location, model_key='nonlinear__pooled')


@pytest.mark.parametrize('relative', ['../escape', '/absolute', 'C:/absolute', 'nested\\file'])
def test_asset_paths_cannot_escape_root(tmp_path, relative):
    with pytest.raises(ValueError, match='relative_path'):
        assets.AssetLocation(str(tmp_path), relative, 'inputs', assets.HANDOFF_SHA256)


def bundle_fixture(tmp_path, monkeypatch):
    def write(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf8')
        return hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = dict(source_commit='test-only', model_fits=0, model_handoff=False)
    freeze_sha = write('inputs/freeze.json', frozen)
    model_manifest_sha = write('inputs/model-manifest.json', {'test_fixture': True})
    trusted = {
        'freeze.json': freeze_sha, 'model-manifest.json': model_manifest_sha,
        'authorization.json': write('inputs/authorization.json', {'approved': True}),
        'resource-amendment.json': write('inputs/resource-amendment.json', {'approved': True}),
    }
    files = {
        'code.py': write('code.py', 'source'),
        'model.json': write('model.json', {'frozen': True}),
        assets.FIT_DIR+'/cache-inventory.json': write(assets.FIT_DIR+'/cache-inventory.json', {}),
        assets.FIT_ACCEPTANCE: write(assets.FIT_ACCEPTANCE, {'accepted': True}),
    }
    manifest_sha = write('SOURCE_MANIFEST.json', {'files_sha256': files})
    handoff = dict(schema='projected-v38-prediction-control-interface-handoff-v2',
                   status='qualified_for_bounded_control_integration', prediction_handoff=True,
                   closed_loop_controller_promoted=False, source_commit='test-only',
                   closeout_sha256=write(assets.HANDOFF_DIR+'/formal-closeout.json', {}),
                   formal_freeze_sha256=freeze_sha, model_manifest_sha256=model_manifest_sha,
                   source_manifest_sha256=manifest_sha,
                   eligible_models={'nonlinear__pooled': {'path': 'model.json',
                       'sha256': files['model.json'], 'training_configurations': ['base']}})
    digest = write(assets.HANDOFF_FILE, handoff)
    # Only the test's trust root and fit-domain constructor are substituted.
    # Every intermediate byte/hash/path check is exercised unmodified.
    monkeypatch.setattr(assets, 'HANDOFF_SHA256', digest)
    monkeypatch.setattr(assets, 'TRUSTED_INPUT_HASHES', trusted)
    monkeypatch.setattr(assets, 'load_fit_domains', lambda *args: {'base': object()})
    return assets.AssetLocation(str(tmp_path), '.', 'inputs', digest)


@pytest.mark.parametrize('path', [
    'inputs/authorization.json', 'inputs/resource-amendment.json', 'inputs/freeze.json',
    'inputs/model-manifest.json', 'SOURCE_MANIFEST.json', 'code.py', 'model.json',
    assets.FIT_DIR+'/cache-inventory.json', assets.FIT_ACCEPTANCE,
    assets.HANDOFF_FILE, assets.HANDOFF_DIR+'/formal-closeout.json',
])
def test_altered_source_model_approval_and_cache_bytes_are_rejected(tmp_path, monkeypatch, path):
    location = bundle_fixture(tmp_path, monkeypatch)
    assert assets.load_assets(location, model_key='nonlinear__pooled').model_path == tmp_path/'model.json'
    target = tmp_path / path
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(ValueError, match='assets_'):
        assets.load_assets(location, model_key='nonlinear__pooled')
