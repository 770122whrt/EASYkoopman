"""Bounded, ordered v67 runs. CPU readiness is distinct from physical evidence."""
import gzip
import hashlib
import json
from pathlib import Path
import sys


def main():
    root = Path('/root/EASYkoopman-phase9-runtime-v59-20260920')
    addon = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    from workflows.phase9_preflight_v59 import verify_release
    from workflows import run_runtime_v59 as runner
    release = verify_release(root)
    manifest = json.loads((addon/'MANIFEST.json').read_text())
    for name, digest in manifest['files_sha256'].items():
        path = (addon/name).resolve()
        if not path.is_relative_to(addon) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('addon_hash:'+name)
    protocol = json.loads((addon/'protocol.json').read_text())
    if release['release_sha256'] != protocol['release_sha256']:
        raise ValueError('release_hash')
    case_id = sys.argv[1]
    cpu = case_id == 'cpu-check'
    cases = protocol['cases']
    if not cpu:
        readiness = json.loads((addon/'results/cpu-check/readiness.json').read_text())
        cpu_native = json.loads((addon/'results/cpu-check/native.json').read_text())
        if (readiness.get('passed') is not True or cpu_native['native_exit'] != 0
                or cpu_native['group_stopped'] is not True
                or readiness['model_sha256'] != protocol['model_sha256']):
            raise ValueError('worker_readiness_required')
        index = next(i for i, case in enumerate(cases) if case['case_id'] == case_id)
        # Every previous case must finish physical/causal validation, not only exit zero.
        for previous in cases[:index]:
            directory = addon/'results'/previous['case_id']
            native = json.loads((directory/'native.json').read_text())
            accepted = json.loads((directory/'analysis.json').read_text())
            if (native['native_exit'] != 0 or not native['group_stopped']
                    or native['analysis']['native_exit'] != 0 or not native['analysis']['group_stopped']
                    or accepted['status'] != 'physical_and_causal_replay_passed'
                    or accepted['case'] != previous):
                raise ValueError('previous_case_not_accepted')
        if cases[index]['configuration'] != 'base':
            # At least one base task must show a material benefit; retain both tasks' verdicts.
            import workflows
            workflows.__path__ = [str(addon/'workflows'), *list(workflows.__path__)]
            import numpy as np
            from workflows.compare_effects_v67 import classify_pair
            verdicts = []
            for task in ('pitch', 'depth'):
                pair, commands = [], []
                for arm in ('feedback', 'mpc'):
                    directory = addon/'results'/('base-'+task+'-'+arm)
                    pair.append(json.loads((directory/'analysis.json').read_text()))
                    with gzip.open(directory/'output/diagnostic.json.gz', 'rt') as f:
                        data = json.load(f)
                    commands.append(np.asarray([r['decision']['packet']['command'] for r in data['intervals']]))
                verdicts.append(classify_pair(*pair, command_difference=float(np.max(np.abs(commands[0]-commands[1])))))
            if not any(v['verdict'] == 'benefit_in_this_scenario' for v in verdicts):
                raise ValueError('base_no_material_benefit_stop_expansion')
    limit = protocol['limits']
    prior = [json.loads(p.read_text()) for p in (addon/'results').glob('*/native.json')]
    remaining = limit['total_seconds']-sum(r['seconds']+r.get('analysis', {}).get('seconds', 0) for r in prior)
    if remaining <= 3 or len(prior) >= limit['attempts']: raise ValueError('run_budget')
    runner.DISK_STOP_BYTES = 14*1024**2
    runner.PER_HOST_BYTES = limit['new_bytes_per_host']
    if runner.disk_bytes(root)+runner.disk_bytes(addon) > limit['retained_research_bytes_per_host']:
        raise ValueError('retained_bytes')
    folder = addon/'results'/case_id
    folder.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, '-B', '-u', str(addon/'bin'/('check_rate30_worker_v67.py' if cpu else 'collect_effects_v67.py')),
        '--release-root', str(root), '--output', str(folder/('readiness.json' if cpu else 'output'))]
    if not cpu: command += ['--case', case_id]
    allocated = min(120 if cpu else limit['case_seconds'], remaining)
    result = runner.bounded_process(command, addon, folder/'collector.log', timeout_seconds=allocated)
    result.update(case_id=case_id, diagnostic_only=True,
        manifest_sha256=hashlib.sha256((addon/'MANIFEST.json').read_bytes()).hexdigest())
    if not cpu and result['native_exit'] == 0 and result['group_stopped']:
        budget = min(60, allocated-result['seconds'])
        if budget > 3:
            command = [sys.executable, '-B', str(addon/'bin/analyze_effects_v67.py'), '--release-root', str(root), '--case', case_id]
            result['analysis'] = runner.bounded_process(command, addon, folder/'analysis.log', timeout_seconds=budget)
    with (folder/'native.json').open('x') as f: json.dump(result, f, indent=2)
    print(json.dumps(result))
    passed = result['native_exit'] == 0 and result['group_stopped']
    if not cpu:
        passed = passed and result.get('analysis', {}).get('native_exit') == 0 and result['analysis']['group_stopped']
    return 0 if passed else 1


if __name__ == '__main__': raise SystemExit(main())
