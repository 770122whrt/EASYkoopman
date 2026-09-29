"""Verify frozen replay parity and imports from the reduced source archive."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def delta(a, b):
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        return max((delta(a[k], b[k]) for k in a), default=0.0)
    if isinstance(a, list):
        assert len(a) == len(b)
        return max((delta(x, y) for x, y in zip(a, b)), default=0.0)
    return abs(a - b)


def main():
    from workflows.source_freeze import analysis_identity, verify
    identity = analysis_identity()
    checks = {}
    for role in ('validation', 'test'):
        new = json.loads((OUT / f'{role}-replay.json').read_text())
        old = json.loads((ROOT / 'experiments/phase9/v88' / f'{role}.json').read_text())
        assert new['analysis_source_identity'] == identity
        for key in ('gates', 'source_trace_hashes', 'model_sha256', 'training_manifest_sha256',
                    'source_manifest_sha256', 'model_fits', 'closed_loop_admitted', 'physical_recalibrated'):
            assert new[key] == old[key], (role, key)
        assert len(new['rows']) == len(old['rows']) == 144
        maximum = 0.0
        for a, b in zip(new['rows'], old['rows']):
            assert a.keys() == b.keys()
            for key in set(a) - {'metrics'}:
                assert a[key] == b[key], (role, key)
            if a['metrics'] is None:
                assert b['metrics'] is None
            else:
                maximum = max(maximum, delta(a['metrics'], b['metrics']))
        assert maximum <= 1e-10, (role, maximum)
        assert new['ranges'] == old['ranges']
        checks[role] = dict(trajectories=len(new['source_trace_hashes']), model_windows=144,
                            maximum_metric_difference=maximum, gates_identical=True)
    release = ROOT / 'results/current-release'
    verified = verify(release / 'manifest.json', source_archive=release / 'source.tar.gz')
    unpacked = ROOT / '.pytest-tmp/current-package-final'
    unpacked.mkdir(parents=True, exist_ok=False)
    with tarfile.open(release / 'source.tar.gz', 'r:gz') as archive:
        for member in archive:
            target = (unpacked / member.name).resolve()
            assert target.is_relative_to(unpacked.resolve())
            if member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    probe = subprocess.run([sys.executable, '-I', '-c',
        'import sys,re; sys.path.insert(0,sys.argv[1]); '
        'from workflows.disturbance_data import frozen_model; '
        'from workflows.disturbance_protocol import get_protocol; '
        'from koopman.control_solver import make_predictor; '
        'from koopman.continuous_mpc import ContinuousMPC; '
        'from easyuuv_nc import control; '
        'record,physical=frozen_model(); '
        'assert record["lifted"]["training_rows"]==16640; '
        'assert get_protocol().excitation(get_protocol().cases()[0]).shape==(320,4); '
        'assert not any(re.search(r"_v[0-9]+",n) for n in sys.modules if n.startswith(("koopman.","workflows.","easyuuv_nc."))); '
        'print("isolated current source bundle passed")', str(unpacked)],
        cwd=unpacked, capture_output=True, text=True)
    assert probe.returncode == 0, probe.stderr
    suite = ET.parse(OUT / 'tests.xml').getroot()
    suites = list(suite) if suite.tag == 'testsuites' else [suite]
    tests = {key: sum(int(x.get(key, 0)) for x in suites)
             for key in ('tests', 'failures', 'errors', 'skipped')}
    assert tests['failures'] == tests['errors'] == tests['skipped'] == 0
    (OUT / 'source-manifest.json').write_bytes((release / 'manifest.json').read_bytes())
    result = dict(scope='local cleanup/refactor validation; no new training, Isaac run or closed loop',
                  source_identity=identity['content_sha256'], source_files=len(identity['files']),
                  tests=tests, metric_tolerance=1e-10, replay=checks, source_bundle=verified,
                  isolated_bundle_imports=True, snapshot_before_cleanup='7bbbbef125ec4e7e397da65f6da859fea05fb5ca')
    with (OUT / 'verification.json').open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
