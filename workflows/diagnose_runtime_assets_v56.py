"""Single fixed relocated request at 1000ms for diagnosis, never admission."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


class TimedSolver:
    def __init__(self, solver):
        self.solver = solver

    def __call__(self, request):
        measured = {}
        def timed(name, fn):
            def call(*args, **kwargs):
                start = time.perf_counter()
                try: return fn(*args, **kwargs)
                finally: measured[name] = 1000*(time.perf_counter()-start)
            return call
        baseline = self.solver.baseline.build; search = self.solver.solver.solve
        self.solver.baseline.build = timed('baseline_ms', baseline)
        self.solver.solver.solve = timed('search_ms', search)
        start = time.perf_counter()
        try:
            result = self.solver(request)
            result['diagnostic_component_times'] = dict(measured, total_ms=1000*(time.perf_counter()-start))
            return result
        finally:
            self.solver.baseline.build = baseline; self.solver.solver.solve = search


def factory(spec):
    from workflows.runtime_assets_v56 import portable_model_factory
    return TimedSolver(portable_model_factory(spec))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--compiler-dir',type=Path,required=True)
    args=parser.parse_args(); root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[key]='1'
    from workflows.check_runtime_assets_v56 import dump
    from workflows.runtime_assets_v56 import AssetLocation,load_assets
    original_path=root/'docs/evidence/phase9/runtime-assets-v56-relocation-20260920/result.json'
    original=json.loads(original_path.read_text())['paths'][0]['reply']['payload']
    args.output.mkdir(parents=True,exist_ok=False)
    protocol=dict(schema='relocated-worker-v56-diagnosis',maximum_seconds=90,output_limit_bytes=4*1024**2,
        worker_timeout_ms=1000,solver_timeout_ms=1000,original_admission_ms=100,diagnostic_only=True,
        request_count=1,retries=0,configuration='base',origin_control=128,
        old_result_sha256=hashlib.sha256(original_path.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),new_fits=0,new_physics_steps=0)
    dump(args.output/'protocol.json',protocol); (args.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    started=time.perf_counter();worker=None;report=dict(status='failed',error=None)
    def budget():
        if time.perf_counter()-started>=90:raise TimeoutError('relocation_diagnosis_budget')
    try:
        import numpy as np
        import torch
        torch.set_num_threads(1);torch.set_num_interop_threads(1)
        from workflows.identify_sparse_world_v30 import load_fit_cache
        from koopman.prepared_execution_v49 import PreparedCausalCommandState
        from koopman.execution_ledger_v48 import ExecutionCapture
        from koopman.recovery_solver_v50 import PlanningRequest,request_binding
        from koopman.bounded_mpc_v44 import SearchConfig
        from koopman.solver_worker_v49 import IsolatedSolverWorker,WorkerLimits
        loc=AssetLocation(str(args.assets.resolve()),'.','assets/v38/inputs','5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632')
        assets=load_assets(loc,model_key='nonlinear__pooled');d=assets.domains['base']
        e=next(e for e in load_fit_cache(Path(loc.root)) if e.case['configuration']=='base' and e.case['excitation']=='prbs')
        live=PreparedCausalCommandState('base',e.context,episode_id=e.case['run_id'],zero_rotor_reset_verified=True)
        for i in range(256):live.record_issued(e.arrays['issued_control'][i],physics_index=i,episode_id=e.case['run_id'])
        origin=live.snapshot(configuration='base',context=e.context,origin_control=128,episode_id=e.case['run_id'])
        b=original['binding']; prefix=np.array(original['commands'][:8],dtype=np.float32)
        digest=hashlib.sha256(e.arrays['issued_control'][:256].astype(np.float32).tobytes()).hexdigest()
        cap=ExecutionCapture(b['execution_id'],b['episode_id'],b['reset_id'],256,digest,0,b['reference_id'],0,
            'base',d.context_key,d.model_id,d.identity,time.perf_counter(),e.states[256].copy(),
            np.array([5.5,1.,0.,0.,0.]),e.arrays['issued_control'][255].copy(),origin)
        req=PlanningRequest(b['request_id'],cap,prefix);assert request_binding(req)==b
        spec=assets.worker_spec('base',compiler_directory=str(args.compiler_dir.resolve()),config=SearchConfig(timeout_ms=1000))
        worker=IsolatedSolverWorker(factory,spec,limits=WorkerLimits(request_timeout_ms=1000.))
        worker.start();event=None
        while event is None:
            budget();event=worker.poll()
            if event is None:time.sleep(.001)
        report['ready']=event
        if event['status']!='ready':raise ValueError('diagnostic_not_ready')
        receipt=worker.submit(req.request_id,req);report['submitted']=receipt;event=None
        if receipt['status']!='accepted':raise ValueError('diagnostic_not_accepted')
        while event is None:
            budget();event=worker.poll()
            if event is None:time.sleep(.0005)
        report['reply']=event
        if event['status']=='result' and event['payload']['status'] in ('selected','baseline'):
            answer=event['payload'];differences={}
            for key in ('commands','predictions'):
                a,b=np.asarray(original[key]),np.asarray(answer[key]);np.testing.assert_allclose(a,b,rtol=1e-12,atol=1e-12)
                differences[key]=float(np.max(np.abs(a-b)))
            np.testing.assert_allclose([original['cost'],original['baseline_cost']],[answer['cost'],answer['baseline_cost']],rtol=1e-12,atol=1e-12)
            report.update(status='diagnostic_result_equivalent',differences=differences,admission_promoted=False)
        else:report['status']='diagnostic_rejected'
    except Exception as exc:report['error']=type(exc).__name__+':'+str(exc)
    finally:
        if worker is not None:report['closed']=worker.close()
        report['seconds']=time.perf_counter()-started;dump(args.output/'result.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('reply','submitted')},ensure_ascii=False),flush=True)
    return 0 if report['error'] is None else 1


if __name__=='__main__':raise SystemExit(main())
