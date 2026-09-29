"""Fit-only complete-path cost diagnosis; profiled times are not admission data."""
import argparse
import cProfile
from dataclasses import replace
import datetime
import importlib.util
import json
import os
from pathlib import Path
import pstats
import sys
import time


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def profile_call(call, root, frozen):
    profile = cProfile.Profile(); result = profile.runcall(call)
    stats = pstats.Stats(profile); functions = []
    for (filename, line, function), (_, calls, own, cumulative, _) in stats.stats.items():
        try: filename = 'frozen/'+Path(filename).relative_to(frozen).as_posix()
        except ValueError:
            try: filename = Path(filename).relative_to(root).as_posix()
            except ValueError: pass
        functions.append(dict(file=filename, line=line, function=function, calls=calls,
                              self_ms=1000*own, cumulative_ms=1000*cumulative))
    return result, dict(profiled_total_ms=1000*stats.total_tt,
        by_self=sorted(functions, key=lambda f: -f['self_ms'])[:50],
        by_cumulative=sorted(functions, key=lambda f: -f['cumulative_ms'])[:50])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--compiler-dir', required=True, type=Path)
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    helper = load_file('mpc_profile_helper', root/'workflows/benchmark_command_state_v39.py')
    pilot = root/'docs/evidence/phase9/mpc-v44-pilot-20260920'
    old = helper.read(pilot/'protocol.json'); old_result = helper.read(pilot/'result.json')
    assert old_result['overall_gate'] == 'NO_GO'
    assert old_result['protocol_sha256'] == helper.sha(pilot/'protocol.json')
    assert all(helper.sha(pilot/'source'/name) == digest for name, digest in old['sources'].items())
    handoff_path = root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    assert helper.sha(handoff_path) == old['handoff_sha256']
    handoff = helper.read(handoff_path); frozen = Path(handoff['frozen_source_directory'])
    modules = ['koopman/command_state_v39.py', 'koopman/prepared_projected_v40.py',
        'koopman/prepared_allocation_v42.py', 'koopman/command_batch_v42.py', 'koopman/compiled_projected_v43.py',
        'koopman/control_objective_v44.py', 'koopman/bounded_mpc_v44.py']
    # Only the named v44 clock repair/test differs from the archived failed pilot.
    assert all(helper.sha(root/name) == digest for name, digest in old['sources'].items()
               if name not in ('koopman/bounded_mpc_v44.py', 'tests/test_bounded_mpc_v44.py'))
    sources = modules+['workflows/profile_bounded_mpc_v44.py', 'tests/test_bounded_mpc_v44.py']
    protocol = dict(schema='mpc-v44-profile-v1', configurations=['base', 'uuv6_angled'],
        origin_control=128, horizon=20, reference=[5.5, 1., 0., 0., 0.], model='nonlinear__pooled',
        baseline='repeat_last_past_issued_command', warmups=1, profiled_calls_per_path=1,
        diagnostic_solve_limit_ms=1000., original_admission_limit_ms=100.,
        maximum_seconds=90, output_limit_bytes=8*1024**2,
        max_active_compute_processes=1, max_resident_processes=1, compute_threads=1,
        sources={name:helper.sha(root/name) for name in sources},
        prior_result_sha256=helper.sha(pilot/'result.json'), handoff_sha256=helper.sha(handoff_path),
        formal_test_access=False, new_fits=0, new_server_runs=0)
    if args.output.exists(): raise FileExistsError('mpc_profile_exists')
    args.output.mkdir(parents=True); helper.dump(args.output/'protocol.json', protocol)
    for name in sources:
        target=args.output/'source'/name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write((root/name).read_bytes())
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS'): os.environ[key]='1'
    sys.path.insert(0, str(args.compiler_dir.resolve())); sys.path.insert(0, str(frozen))
    started=time.perf_counter(); rows=[]; status='failed'; error=None
    def budget():
        if time.perf_counter()-started >= 90: raise TimeoutError('mpc_profile_budget')
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        from workflows.projected_release_v38 import verify_bundle
        from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
        from workflows.feedback_v31 import FeedbackPolicy, validate_decision
        verify_bundle(frozen, frozen.parent/'inputs', handoff['source_commit'])
        loaded={Path(name).stem:load_file(name[:-3].replace('/','.'),root/name) for name in modules}
        entry=handoff['eligible_models'][protocol['model']]; path=frozen/entry['path']
        assert helper.sha(path)==entry['sha256']
        model=from_record(helper.read(path)); core=loaded['bounded_mpc_v44']; domains=core.load_fit_domains(root,path)
        episodes=[e for e in load_fit_cache(root) if e.case['excitation']=='prbs'
                  and e.case['configuration'] in protocol['configurations']]
        assert len(episodes)==2 and all(e.case['role']=='fit' for e in episodes)
        for e in episodes:
            budget(); name=e.case['configuration']; episode_id=e.case['run_id']
            t=time.perf_counter(); predictor=loaded['compiled_projected_v43'].prepare_compiled(model,e.context)
            prepare_ms=1000*(time.perf_counter()-t)
            live=loaded['command_state_v39'].CausalCommandState(name,e.context,episode_id=episode_id,zero_rotor_reset_verified=True)
            for i in range(256): live.record_issued(e.arrays['issued_control'][i],physics_index=i,episode_id=episode_id)
            snapshot=live.snapshot(configuration=name,context=e.context,origin_control=128,episode_id=episode_id)
            solver=core.BoundedMPC(domains[name],predictor,model_id=entry['sha256'],
                                  config=replace(core.SearchConfig(),timeout_ms=1000.))
            def solve():
                previous=e.arrays['issued_control'][255].copy()
                result=solver.solve(snapshot,e.states[256].copy(),np.repeat(previous[None],20,axis=0),previous,
                    protocol['reference'],episode_id=episode_id,reference_id='fixed-z5.5-upright',request_id='profile')
                return json.loads(json.dumps(result,default=lambda a:a.tolist(),allow_nan=False))
            warm=solve(); budget()
            solved, solver_stats=profile_call(solve,root,frozen)
            assert solved['status'] in ('selected','baseline') and solved['status']==warm['status']
            np.testing.assert_allclose(solved['commands'],warm['commands'],rtol=1e-12,atol=1e-12)
            policy=FeedbackPolicy(name)
            def fallback():
                decision=policy.decide(e.states[256].copy(),np.zeros(4))
                accepted=validate_decision(decision,e.states[256].copy(),np.zeros(4),name)
                return dict(accepted=bool(accepted), decision=decision)
            fallback(); budget()
            fb, fallback_stats=profile_call(fallback,root,frozen)
            assert fb['accepted'] and live.physics_index==256
            rows.append(dict(configuration=name,episode_id=episode_id,trace_sha256=e.trace_sha256,
                prepare_before_calls_ms=prepare_ms,solver=solver_stats,solver_result=solved,
                fallback=fallback_stats,fallback_result=fb))
            print(json.dumps(dict(configuration=name,solver_profile_ms=solver_stats['profiled_total_ms'],
                                  fallback_profile_ms=fallback_stats['profiled_total_ms'])),flush=True)
        budget(); verify_bundle(frozen,frozen.parent/'inputs',handoff['source_commit'])
        assert all(helper.sha(root/name)==digest for name,digest in protocol['sources'].items())
        status='local_complete_path_profile_complete'
    except Exception as exc: error=f'{type(exc).__name__}:{exc}'
    result=dict(status=status,error=error,seconds=time.perf_counter()-started,rows=rows,
        protocol_sha256=helper.sha(args.output/'protocol.json'),created_at=datetime.datetime.now().astimezone().isoformat(),
        clocks={key:vars(time.get_clock_info(key)) for key in ('monotonic','perf_counter')},
        prior_gate_unchanged='NO_GO',controller_promoted=False,
        limitations=['two_fit_configurations_only','profiled_time_not_deadline_evidence','no_actual_issuance'])
    helper.dump(args.output/'result.json',result)
    if sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('profile_output_budget')
    print(json.dumps(dict(status=status,seconds=result['seconds'],error=error)),flush=True)
    if status!='local_complete_path_profile_complete':raise SystemExit(1)


if __name__=='__main__':main()
