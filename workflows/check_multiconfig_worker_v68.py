"""Frozen-model CPU worker readiness only; no physics or control-effect claim."""
import argparse
import json
from pathlib import Path
import sys
import time


def paths():
    root = Path(sys.argv[sys.argv.index('--release-root')+1]).resolve()
    sys.path.insert(0, str(root))
    import koopman, workflows
    for package in (koopman, workflows):
        package.__path__ = [str(Path(__file__).resolve().parents[1]/package.__name__), *list(package.__path__)]
    return root


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--release-root', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = paths()
    from workflows.runtime_assets_v56 import AssetLocation, load_assets
    from workflows.collect_runtime_v59 import HANDOFF_SHA
    from workflows.phase9_preflight_v59 import verify_release
    from koopman.rate30_v67 import portable_rate30_factory, SEARCH_CONFIG, FEEDBACK_CONFIG
    from koopman.solver_worker_v49 import IsolatedSolverWorker
    release = verify_release(root)
    assets = load_assets(AssetLocation(str(root), '.', 'assets/v38/inputs', HANDOFF_SHA), model_key='nonlinear__pooled')
    report = dict(schema='multiconfiguration-worker-readiness-v68', physics_steps=0, model_fits=0,
        control_benefit_claim=False, release_sha256=release['release_sha256'],
        model_sha256=assets.model_sha256, workers=[])
    names = json.loads((Path(__file__).resolve().parents[1]/'protocol.json').read_text())['configuration_order']
    for name in names:
        started = time.perf_counter()
        worker = IsolatedSolverWorker(portable_rate30_factory,
            assets.worker_spec(name, config=SEARCH_CONFIG, feedback_config=FEEDBACK_CONFIG))
        row = dict(configuration=name)
        try:
            worker.start()
            while worker.state == 'starting':
                event = worker.poll()
                if event is not None: row['event'] = event
                if time.perf_counter()-started > 30: raise TimeoutError('worker_startup')
                time.sleep(.005)
            row['state'] = worker.state
            if worker.state != 'ready': raise ValueError('worker_not_ready')
        except BaseException as exc:
            row['error'] = type(exc).__name__+':'+str(exc)
        finally:
            row['cleanup'] = worker.close()
            row['seconds'] = time.perf_counter()-started
            report['workers'].append(row)
        if row.get('error'): break
    report['passed'] = len(report['workers']) == len(names) and all(r.get('state') == 'ready'
        and r['cleanup'] == dict(process_stopped=True, io_threads_stopped=True) for r in report['workers'])
    with args.output.open('x') as f: json.dump(report, f, indent=2)
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__mp_main__': paths()
if __name__ == '__main__': raise SystemExit(main())
