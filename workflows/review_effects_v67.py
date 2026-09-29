"""Independent local reconstruction of pulled actual v67 traces and paired metrics."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from workflows.runtime_assets_v56 import AssetLocation, load_assets
from workflows.collect_runtime_v59 import HANDOFF_SHA
from workflows.validate_effects_v67 import validate_execution
from workflows.validate_tracking_v67 import validate_tracking_audit
from workflows.compare_effects_v67 import classify_pair
from koopman.control_objective_v44 import tracking_terms, control_mask


def review(evidence, release):
    assets = load_assets(AssetLocation(str(release.resolve()), '.', 'assets/v38/inputs', HANDOFF_SHA), model_key='nonlinear__pooled')
    results, traces, analyses, pairs = {}, {}, {}, {}
    charged = 0.
    for folder in sorted((evidence/'results').iterdir()):
        if not (folder/'output/diagnostic.json.gz').is_file(): continue
        native = json.loads((folder/'native.json').read_text())
        charged += native['seconds']+native.get('analysis', {}).get('seconds', 0.)
        with gzip.open(folder/'output/diagnostic.json.gz', 'rt') as f: data = json.load(f)
        traces[folder.name] = data
        case = data['case']
        entry = dict(case=case, exception=data.get('exception'), native_exit=native['native_exit'],
            actual_physics_steps=len(data.get('substeps', [])), group_stopped=native['group_stopped'],
            complete=False, trace_sha256=hashlib.sha256((folder/'output/diagnostic.json.gz').read_bytes()).hexdigest())
        assert native['group_stopped'] and not native['remaining_group_pids']
        if (folder/'analysis.json').exists():
            accepted = json.loads((folder/'analysis.json').read_text())
            assert native['native_exit'] == 0 and native['analysis']['native_exit'] == 0 and native['analysis']['group_stopped']
            assert data['status'] == 'diagnostic_returned' and not data.get('exception')
            assert not data['cleanup_errors'] and data['cleanup_completed']['environment'] and data['cleanup_completed']['simulation_app']
            if case['controller'] == 'mpc':
                assert data['worker_closed'] == dict(process_stopped=True, io_threads_stopped=True)
            check = validate_execution(data, case, assets.domains[case['configuration']], assets.context(case['configuration']))
            feedback = validate_tracking_audit(data, assets.domains[case['configuration']], assets.context(case['configuration']))
            terms = tracking_terms(np.asarray([r['state_after_physics_11'][0] for r in data['substeps']]), case['reference'], control_mask(case['configuration']))
            metrics = dict(normalized_tracking_score=float(np.mean(terms['depth']/.02**2+terms['attitude']/.04**2)),
                depth_rmse_m=float(np.sqrt(np.mean(terms['depth']))), attitude_rmse_rad=float(np.sqrt(np.mean(terms['attitude']))))
            commands = np.asarray([r['decision']['packet']['command'] for r in data['intervals']])
            wrenches = np.asarray([r['command']['telemetry']['applied_wrench_6'][0] for r in data['substeps']])
            metrics.update(command_variation=float(np.linalg.norm(np.diff(commands, axis=0), axis=1).sum()),
                applied_force_squared_N2_s=float(np.sum(wrenches[:, :3]**2)/120),
                applied_torque_squared_Nm2_s=float(np.sum(wrenches[:, 3:]**2)/120))
            for key, value in metrics.items():
                if not np.isclose(value, accepted['metrics'][key], rtol=1e-12, atol=1e-12):
                    raise ValueError('metric_mismatch:'+folder.name+':'+key)
            entry.update(complete=True, independent_replay='passed', feedback_audit=feedback,
                metrics=accepted['metrics'], timing=accepted['timing'])
            analyses[folder.name] = accepted
        probe = data.get('latency_probe_v67', {})
        decisions = probe.get('feedback', [])
        if decisions:
            entry['feedback_latency'] = dict(p50_ms=float(np.median([r['wall_ms'] for r in decisions])),
                max_ms=max(r['wall_ms'] for r in decisions), gc_event_count=len(probe.get('gc_events', [])))
        results[folder.name] = entry
    for name in ('base', 'asymmetric', 'uuv4'):
        for task in ('pitch', 'depth'):
            prefix = name+'-'+task
            f, m = prefix+'-feedback', prefix+'-mpc'
            if f not in analyses or m not in analyses: continue
            u = lambda key: np.asarray([r['decision']['packet']['command'] for r in traces[key]['intervals']])
            pair = classify_pair(analyses[f], analyses[m], command_difference=float(np.max(np.abs(u(f)-u(m)))))
            pair['cost_ratios_mpc_over_feedback'] = {key: analyses[m]['metrics'][key]/analyses[f]['metrics'][key]
                if analyses[f]['metrics'][key] else None for key in
                ('command_variation', 'applied_force_squared_N2_s', 'applied_torque_squared_Nm2_s')}
            pairs[prefix] = pair
    result = dict(status='reviewed_actual_cases_only', case_results=results, pairs=pairs,
        measured_case_seconds=charged, zero_refits=True, runtime_qualified=False,
        unique_koopman_advantage_proven=False, complete_paired_scenarios=len(pairs))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--release', type=Path, default=REPO/'.pytest-tmp/phase9-runtime-v59-20260920')
    args = p.parse_args()
    result = review(args.evidence, args.release)
    (args.evidence/'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps(dict(cases=len(result['case_results']), pairs=result['pairs'], seconds=result['measured_case_seconds'])))
