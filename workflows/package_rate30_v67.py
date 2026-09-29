"""Explicit-file additive deployment of the 30Hz pilot; no frozen source edits."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import tarfile


def package(root, output, *, defer_gc=False):
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for name in ('compiled_forecast_v64', 'bounded_mpc_v64', 'compiled_recovery_v64',
                 'inexact_tracking_v66', 'rate30_v67', 'bounded_mpc_v67'):
        files['koopman/'+name+'.py'] = 'koopman/'+name+'.py'
    for name in ('isaac_execution_v67', 'runtime_episode_v67', 'runtime_audit_v67',
                 'runtime_addon_v67', 'runtime_timing_v67', 'validate_effects_v67',
                 'validate_tracking_v67', 'compare_effects_v67'):
        files['workflows/'+name+'.py'] = 'workflows/'+name+'.py'
    files['easyuuv_nc/control_v67.py'] = 'easyuuv_nc/control_v67.py'
    for name in ('collect_effects_v67', 'analyze_effects_v67', 'check_rate30_worker_v67',
                 'runtime_prepare_v61', 'runtime_lifecycle_v62'):
        files['bin/'+name+'.py'] = 'workflows/'+name+'.py'
    files['supervisor.py'] = 'workflows/supervise_rate30_v67.py'
    for destination, source in files.items():
        target = output/destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/source, target)
    cases = []
    for configuration in ('base', 'asymmetric', 'uuv4'):
        for task, reference in (('pitch', [5.5, math.cos(.02), 0, math.sin(.02), 0]),
                                ('depth', [5.48, 1, 0, 0, 0])):
            for arm in ('feedback', 'mpc'):
                cases.append(dict(case_id=configuration+'-'+task+'-'+arm,
                    configuration=configuration, controller=arm, mode='simulation_effect',
                    controls=60, control_rate_hz=30, seed=19500, reference=reference,
                    reference_id=task+'-v67', model_key='nonlinear__pooled',
                    strategy='paired_rate30_inexact_v67', defer_gc=defer_gc))
    protocol = dict(schema='phase9-effects-v67', cases=cases,
        authorization='2026-09-21 user requested 30Hz adaptation, latency diagnosis and multi-configuration trials; primary server31348',
        gc_policy='collect before bounded episode, defer automatic GC within episode, restore and bound RSS growth64MiB' if defer_gc else 'automatic GC unchanged',
        limits=dict(total_seconds=2280, case_seconds=180, attempts=13,
            new_bytes_per_host=16*1024**2, retained_research_bytes_per_host=256*1024**2),
        no_fit=True, no_formal_test_access=True, physics_rate_hz=120, prediction_grid_hz=60,
        horizon_micro_controls=20, committed_micro_controls=8, macro_slew=.02,
        solve_deadline_ms=100, feedback_deadline_ms=10,
        first_cycle_deadline_ms=100, steady_cycle_deadline_ms=1000/30,
        score=dict(primary='mean(depth_squared/.02**2+controllable_attitude_squared/.04**2)',
            minimum_relative_improvement=.05, minimum_depth_rmse_improvement_m=.0002,
            minimum_attitude_rmse_improvement_rad=.0005, report_cost_tradeoff=True),
        expansion_gate='all four base arms physically and causally valid; at least one base pair materially improves; stop on any later failed case',
        runtime_claim=False, unique_koopman_claim=False,
        model_sha256='9704fbb8cc0a40ebc74f3f4d2727cba0f52a0b4221ec6e71d4f5526d98a088f4',
        release_sha256='aa1efbb4c57b3d01225a3d1604f9b39a2adbc4d04e6e359b249afbfbabb7e3a9')
    (output/'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf8')
    manifest = dict(schema='phase9-rate30-addon-v67', files_sha256={
        p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob('*')) if p.is_file()})
    (output/'MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    archive = output.with_suffix('.tar.gz')
    with tarfile.open(archive, 'x:gz') as tar:
        for name in [*manifest['files_sha256'], 'MANIFEST.json']:
            tar.add(output/name, arcname=name, recursive=False)
    return dict(bundle=str(output), files=len(manifest['files_sha256'])+1,
        manifest_sha256=hashlib.sha256((output/'MANIFEST.json').read_bytes()).hexdigest(),
        archive=str(archive), archive_bytes=archive.stat().st_size,
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--defer-gc', action='store_true')
    args = p.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parents[1], args.output.resolve(), defer_gc=args.defer_gc)))
