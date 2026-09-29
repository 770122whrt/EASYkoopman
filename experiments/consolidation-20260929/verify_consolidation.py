"""Check refactor replay parity and imports from the actual isolated source bundle."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
FINAL = Path(__file__).resolve().parent / 'final'
TOLERANCE = 1e-10  # Same frozen forecasts; only numerical runtime roundoff is allowed.


def difference(a, b):
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        return max((difference(a[k], b[k]) for k in a), default=0.)
    if isinstance(a, list):
        assert len(a) == len(b)
        return max((difference(x, y) for x, y in zip(a, b)), default=0.)
    return abs(a - b)


def main():
    from workflows.source_freeze import analysis_identity, verify
    identity = analysis_identity()
    checks = {}
    for role in ('validation', 'test'):
        new = json.loads((FINAL / f'{role}-replay.json').read_text())
        old = json.loads((ROOT / 'docs/evidence/phase9/matrix-v88-20260929/server' / f'{role}.json').read_text())
        assert new['analysis_source_identity'] == identity
        for key in ('gates', 'source_trace_hashes', 'model_sha256', 'training_manifest_sha256',
                    'source_manifest_sha256', 'model_fits', 'closed_loop_admitted', 'physical_recalibrated'):
            assert new[key] == old[key], (role, key)
        assert len(new['rows']) == len(old['rows']) == 144
        delta = 0.
        for a, b in zip(new['rows'], old['rows']):
            for key in set(a) - {'metrics'}:
                assert a[key] == b[key], (role, key)
            if a['metrics'] is None:
                assert b['metrics'] is None
            else:
                delta = max(delta, difference(a['metrics'], b['metrics']))
        assert delta <= TOLERANCE, (role, delta)
        assert new['ranges'] == old['ranges']
        checks[role] = dict(trajectories=len(new['source_trace_hashes']), windows=144,
                            maximum_metric_difference=delta, gates_identical=True)

    release = FINAL / 'release'
    verified = verify(release / 'manifest.json', source_archive=release / 'source.tar.gz')
    unpacked = ROOT / '.pytest-tmp/consolidation-package-smoke-20260929'
    assert unpacked.resolve().is_relative_to(ROOT.resolve())
    unpacked.mkdir(parents=True, exist_ok=False)
    # verify() above rejects traversal, duplicate entries and links before extraction.
    with tarfile.open(release / 'source.tar.gz', 'r:gz') as archive:
        for member in archive:
            target = (unpacked / member.name).resolve()
            assert target.is_relative_to(unpacked.resolve())
            if member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    probe = subprocess.run([sys.executable, '-I', '-c',
        'import sys; sys.path.insert(0, sys.argv[1]); '
        'from workflows.disturbance_data import frozen_model; '
        'from workflows.disturbance_protocol import get_protocol; '
        'from koopman.control_solver import make_predictor; '
        'from koopman.continuous_mpc import ContinuousMPC; '
        'from easyuuv_nc import control; '
        'record, physical = frozen_model(); '
        'assert record["lifted"]["training_rows"] == 16640; '
        'assert get_protocol().excitation(get_protocol().cases()[0]).shape == (320, 4); '
        'assert "easyuuv_nc.control_v24" not in sys.modules; '
        'assert "koopman.continuous_mpc_v80" not in sys.modules; '
        'print("isolated current bundle imports and frozen model load passed")', str(unpacked)],
        cwd=unpacked, capture_output=True, text=True)
    assert probe.returncode == 0, probe.stderr
    suite = ET.parse(FINAL / 'tests.xml').getroot()
    suites = list(suite) if suite.tag == 'testsuites' else [suite]
    tests = {key: sum(int(x.get(key, 0)) for x in suites)
             for key in ('tests', 'failures', 'errors', 'skipped')}
    assert tests['failures'] == tests['errors'] == tests['skipped'] == 0
    result = dict(scope='local refactor verification; no new Isaac run or training',
                  analysis_source_sha256=identity['content_sha256'], tests=tests,
                  metric_tolerance=TOLERANCE, replay=checks, source_bundle=verified,
                  isolated_bundle_imports=True, deleted_files=0,
                  previous_git_commit='1d7d1f4379b763e7bd6146ab650203128078260d')
    output = FINAL / 'verification.json'
    with output.open('x', encoding='utf8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
