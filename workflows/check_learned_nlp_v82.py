"""Four bounded real worker solves before the learned-model physics stage."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from koopman.preview_solver_v82 import create_solver, load_model, verify_support
from koopman.control_objective_v44 import ObjectiveWeights
from koopman.bounded_feedback_v46 import FeedbackConfig
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from workflows.server_method_audit_v79 import origin_at, plain
from workflows.runtime_assets_v56 import AssetLocation, load_assets, read
from workflows.validate_preview_decision_v79 import audit_decision


def main():
    p=argparse.ArgumentParser();p.add_argument('--assets',required=True)
    p.add_argument('--models',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();result=dict(schema='learned-nlp-v82-diagnostic/1',physics_runs=0,model_fits=0,
        status='started',solves=[],closed_loop_benefit_claimed=False)
    def save():
        result['wall_seconds']=time.monotonic()-started
        (a.output/'diagnostic.json').write_text(json.dumps(plain(result),indent=2,allow_nan=False))
    assets=load_assets(AssetLocation(a.assets,'.','assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    inputs=read(a.inputs/'traces.json');save()
    try:
        for cfg in ('base','uuv4'):
            row=next(r for r in inputs if r['configuration']==cfg and r['controller']=='feedback')
            payload=(a.inputs/row['file']).read_bytes()
            if hashlib.sha256(payload).hexdigest()!=row['sha256']:raise ValueError('trace_identity')
            data=json.loads(gzip.decompress(payload));c=assets.context(cfg);d=assets.domains[cfg];index=4
            state=np.asarray(data['substeps'][index]['before']['state_11'][0]);ref=np.asarray(data['case']['reference'])
            old=np.asarray(data['substeps'][index-1]['command']['telemetry']['virtual_control_4'][0])
            def factory():return InexactTrackingFeedback(d,c,config=FeedbackConfig(slew=.02,timeout_ms=2000.))
            feedback=factory().decide(state,ref,previous=old)
            if feedback['status']!='ready':raise ValueError('current_feedback')
            for ridge in ('0.001','0.1'):
                if time.monotonic()-started>450:raise TimeoutError('diagnostic_budget')
                path=a.models/f'pooled__learned_{ridge}.json';sha=hashlib.sha256(path.read_bytes()).hexdigest()
                loaded=load_model(path,sha);verify_support(loaded,assets)
                live,origin=origin_at(data,index,c);solver=None
                entry=dict(configuration=cfg,ridge=ridge,model_sha256=sha,trace_sha256=row['sha256'])
                result['solves'].append(entry)
                try:
                    solver=create_solver(d,c,'learned_velocity',learned_model=path,learned_sha256=sha,
                        horizon=20,weights=ObjectiveWeights(depth=4.),preview_enabled=True)
                    entry['model_identity']=solver.model_identity
                    decision=solver.solve(origin=origin,initial_state=state,baseline=np.tile(feedback['command'],(20,1)),
                        previous=old,reference=ref,physical_target=feedback.get('static_command'))
                    entry['decision']=decision
                    if not decision['exact_feasible']:raise ValueError('no_feasible_plan:'+str(decision['reason']))
                    entry['audit']=audit_decision(checker=solver.checker,origin=origin,state=state,previous=old,
                        reference=ref,feedback_result=feedback,prior_decision=None,decision=decision,feedback_factory=factory)
                    if not entry['audit']['accepted'] or live.physics_index!=index:raise ValueError('decision_audit')
                finally:
                    if solver is not None:entry['worker_cleanup']=solver.close()
                    save()
                if entry['worker_cleanup']!={'process_stopped':True,'io_threads_stopped':True}:raise ValueError('worker_cleanup')
                print(json.dumps(dict(configuration=cfg,ridge=ridge,status=decision['status'],cost=decision['cost'])),flush=True)
        result['status']='real_worker_verified_not_closed_loop'
    except BaseException as exc:
        result.update(status='failed',exception=type(exc).__name__+':'+str(exc));raise
    finally:save()


if __name__=='__main__':main()
