"""A runnable Isaac source bundle must include its package-owned USD asset."""
import json
import tarfile
from workflows.prepare_disturbance_v86 import prepare


def test_bundle_contains_and_hashes_the_frozen_usd(tmp_path):
    output=tmp_path/'release';prepare(output)
    manifest=json.loads((output/'manifest.json').read_text())
    name='easyuuv_nc/data/embodiment/embodiment.usd'
    assert manifest['files'].get(name)=='40148fbe201b993448d2dfbac118ef48acdb71641c1ed88caa2b6168b9ae146d'
    with tarfile.open(output/'source.tar.gz') as bundle:
        assert name in bundle.getnames()
