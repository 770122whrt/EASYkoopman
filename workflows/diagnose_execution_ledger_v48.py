"""Three preserved historical rejections and one interface profile; no new run."""
import argparse
import cProfile
import importlib.util
import io
import json
import os
from pathlib import Path
import pstats
import sys
import time


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    helper=load('ledger_diagnosis_helper',root/'workflows/benchmark_command_state_v39.py')
    old=root/'docs/evidence/phase9/execution-v48-replay-20260920'
    prior=helper.read(old/'protocol.json');previous=helper.read(old/'result.json')
    assert previous['local_gate']=='NO_GO' and previous['protocol_sha256']==helper.sha(old/'protocol.json')
    assert all(helper.sha(root/n)==h for n,h in prior['sources'].items())
    handoff_path=root/'docs/evidence/phase8_4/server-projected-formal-v38-r23/prediction-control-handoff-v2.json'
    assert helper.sha(handoff_path)==prior['handoff_sha256']
    handoff=helper.read(handoff_path);frozen=Path(handoff['frozen_source_directory'])
    protocol=dict(schema='ledger-v48-three-rejections-profile-v1',cases=[['asymmetric',1],['uuv6',0],['uuv6_angled',0]],
        profile={'configuration':'base','control_index':1,'repetitions':1},maximum_seconds=60,output_limit_bytes=8*1024**2,
        new_simulation_intervals=0,new_model_fits=0,formal_test_access=False,
        replay_result_sha256=helper.sha(old/'result.json'),runner_sha256=helper.sha(__file__))
    if args.output.exists():raise FileExistsError('diagnosis_output_exists')
    args.output.mkdir(parents=True);helper.dump(args.output/'protocol.json',protocol)
    (args.output/'runner.py.txt').write_bytes(Path(__file__).read_bytes())
    for n in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[n]='1'
    sys.path.insert(0,str(frozen));started=time.perf_counter()
    import numpy as np
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    from workflows.identify_sparse_world_v30 import load_fit_cache
    modules={Path(n).stem:load(n[:-3].replace('/','.'),root/n) for n in prior['sources'] if n.startswith('koopman/')}
    core=modules['execution_ledger_v48'];feedback=modules['bounded_feedback_v47']
    domains=modules['bounded_mpc_v44'].load_fit_domains(root,frozen/handoff['eligible_models']['nonlinear__pooled']['path'])
    episodes={e.case['configuration']:e for e in load_fit_cache(root) if e.case['excitation']=='prbs'}
    ref=np.array([5.5,1.,0.,0.,0.]);rows=[]
    for name,i in protocol['cases']:
        e=episodes[name];d=domains[name];policy=feedback.TrackingFeedback(d,e.context)
        seed=policy.prepare_startup(e.states[0],ref);old_command=e.arrays['issued_control'][2*i]
        previous_command=None if i==0 else e.arrays['issued_control'][2*i-1]
        target=feedback.feedback_demand(e.states[2*i],ref,name,e.context,policy.config)['target_wrench']
        lower=d.command_lower if previous_command is None else np.maximum(d.command_lower,previous_command-.01)
        upper=d.command_upper if previous_command is None else np.minimum(d.command_upper,previous_command+.01)
        inspection=policy.steady.inspect(old_command,target,lower,upper)
        rows.append(dict(configuration=name,control_index=i,old_command=old_command,prepared_startup=seed['command'],
            startup_difference=old_command-seed['command'] if i==0 else None,
            previous_command=previous_command,command_step=None if i==0 else old_command-previous_command,
            target_wrench=target,inspection=inspection))
    e=episodes['base'];d=domains['base'];policy=feedback.TrackingFeedback(d,e.context)
    seed=policy.prepare_startup(e.states[0],ref);eid=e.case['run_id'];rid=e.trace_sha256
    ledger=core.ExecutionLedger(d,e.context,core.ResetObservation(eid,rid,0,e.states[0],e.arrays['causal_rotor_speed'][0]),
        reference=ref,reference_id='hold',startup_command=seed['command'])
    def interval(i):
        cap=ledger.capture(core.BoundaryObservation(eid,rid,2*i,e.states[2*i]),ref,reference_id='hold')
        token=ledger.reserve(cap,e.arrays['issued_control'][2*i],source='fallback',startup=i==0)
        packet=ledger.dispatch(token)
        acknowledgments=[ledger.acknowledge(token,e.arrays['issued_control'][2*i+j],physics_index=2*i+j,episode_id=eid,reset_id=rid) for j in range(2)]
        json.loads(json.dumps(dict(packet=packet,acknowledgments=acknowledgments),default=lambda a:a.tolist(),allow_nan=False))
    interval(0);profile=cProfile.Profile();profile.enable();interval(1);profile.disable()
    out=io.StringIO();pstats.Stats(profile,stream=out).sort_stats('cumulative').print_stats(35)
    (args.output/'profile.txt').write_text(out.getvalue(),encoding='utf8')
    seconds=time.perf_counter()-started
    if seconds>=60:raise TimeoutError('diagnosis_budget')
    assert all(helper.sha(root/n)==h for n,h in prior['sources'].items())
    result=dict(status='diagnosis_complete',seconds=seconds,protocol_sha256=helper.sha(args.output/'protocol.json'),
        rows=rows,new_simulation_intervals=0,controller_promoted=False,replay_no_go_preserved=True)
    with (args.output/'result.json').open('x',encoding='utf8') as f:
        json.dump(result,f,default=lambda a:a.tolist(),indent=2,allow_nan=False)
    if sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())>protocol['output_limit_bytes']:
        raise RuntimeError('diagnosis_output_limit')
    print(json.dumps(dict(status=result['status'],seconds=seconds)),flush=True)


if __name__=='__main__':main()
