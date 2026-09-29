"""Offline counterfactuals from authenticated recorded trajectories, no physics."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from workflows.runtime_assets_v56 import AssetLocation, load_assets, read
from workflows.identify_sparse_world_v30 import from_record
from koopman.prepared_projected_v40 import prepare_projected
from koopman.physical_control_v76 import PhysicalPredictor
from koopman.continuous_mpc_v76 import ContinuousMPC
from koopman.command_state_v39 import CausalCommandState


def plain(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [plain(v) for v in value]
    return value


def main():
    p = argparse.ArgumentParser(); p.add_argument('--assets', required=True)
    p.add_argument('--traces', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); args.output.mkdir(exist_ok=False)
    assets = load_assets(AssetLocation(args.assets, '.', 'assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'), model_key='nonlinear__pooled')
    fitted = from_record(read(assets.model_path)); results = []
    for name, record in read(args.traces/'trace-manifest.json').items():
        raw = (args.traces/(name+'.json.gz')).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record['sha256']
        data = json.loads(gzip.decompress(raw)); cfg = data['case']['configuration']
        c = assets.context(cfg); reference = data['case']['reference']
        if 'failure' in name:
            e = next(e for e in data['arbitration_audit'] if e['method']=='ingest' and e['result'].get('status')=='rejected')
            payload = e['event']['payload']; index = payload['metadata']['history_physics_index']
            baseline = np.asarray(payload['recovery']['commands'])[::2]
            prefixes = [payload['metadata']['committed_prefix']//2, 0]
        else:
            index = 120
            baseline = np.asarray([data['substeps'][i]['command']['telemetry']['virtual_control_4'][0]
                                   for i in range(index, index+40, 4)])
            prefixes = [0]
        live = CausalCommandState(cfg, c, episode_id=name, zero_rotor_reset_verified=True)
        assert np.max(np.abs(data['reset_record']['snapshot']['actuator_speed_n'])) == 0
        for i in range(index):
            live.record_issued(data['substeps'][i]['command']['telemetry']['virtual_control_4'][0],
                               physics_index=i, episode_id=name)
        origin = live.snapshot(configuration=cfg, context=c, origin_control=index//2, episode_id=name)
        state = np.asarray(data['substeps'][index]['before']['state_11'][0])
        previous = data['substeps'][index-1]['command']['telemetry']['virtual_control_4'][0]
        np.testing.assert_allclose(origin._actuator.current(), data['substeps'][index]['before']['actuator_speed_n'][0], atol=3e-4, rtol=1e-5)
        for kind in ('projected_koopman', 'nominal_physics', 'identified_physics'):
            predictor = (prepare_projected(fitted, c) if kind=='projected_koopman' else
                         PhysicalPredictor(fitted, c, identified=kind=='identified_physics'))
            solver = ContinuousMPC(assets.domains[cfg], predictor, horizon=len(baseline))
            for prefix in prefixes:
                result = solver.solve(origin=origin, initial_state=state, baseline=baseline,
                                      previous=previous, reference=reference, committed_prefix=prefix)
                row = dict(trace=name, input=record, physics_index=index, model_kind=kind,
                    committed_macro_steps=prefix, future_feedback_used_offline_only='feedback' in name,
                    model_sha256=assets.model_sha256, **result)
                if result['exact_feasible']:
                    row['max_change_from_baseline'] = float(np.max(np.abs(result['commands']-baseline)))
                    row['first_command_change'] = (result['commands'][prefix]-baseline[prefix]).tolist()
                path=args.output/(name+'-'+kind+'-prefix'+str(prefix)+'.json')
                path.write_text(json.dumps(plain(row),indent=2,allow_nan=False))
                summary={k:v for k,v in row.items() if k not in ('commands','predictions')}
                results.append(summary); print(json.dumps(plain({k:summary.get(k) for k in
                    ('trace','model_kind','committed_macro_steps','status','reason','cost','baseline_cost','constraint_violation','elapsed_seconds')})),flush=True)
        assert live.physics_index == index
    (args.output/'summary.json').write_text(json.dumps(plain(dict(results=results,
        physics_runs=0, model_fits=0, realtime_qualified=False, evidence='offline_recorded_state_counterfactual')),indent=2,allow_nan=False))


if __name__=='__main__': main()
