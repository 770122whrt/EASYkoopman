"""All three frozen arms must qualify on the predeclared evaluation inventory."""
import json
from pathlib import Path
import sys
from workflows.protocol_v87 import cases,protocol
from workflows.fit_disturbance_v87 import load_record


def verify_control_gate(model_sha,kind,validation,test,solver,*,model):
    record,_=load_record(model);manifest_sha=record['collection_manifest_sha256']
    seen=[]
    for role,path in [('validation',validation),('test',test)]:
        r=json.loads(Path(path).read_text(encoding='utf8'))
        inventory={(q['run_id'],start,arm) for q in cases() if q['role']==role
            for start in protocol()['prediction_origins'] for arm in ('physics','koopman','hybrid')}
        actual=[(x['episode'],x['origin'],x['model']) for x in r['rows']]
        if (r.get('schema')!='v87-prediction-evaluation' or r['role']!=role
                or r['model_sha256']!=model_sha or r['source_manifest_sha256']!=manifest_sha
                or len(actual)!=len(inventory) or set(actual)!=inventory or r['model_fits']!=0
                or any(not x['complete'] or x['metrics']['z_rmse_m']>.002
                    or x['metrics']['attitude_rmse_rad']>.004 for x in r['rows'])):
            raise ValueError('v87_prediction_gate:'+role)
        hashes=set(r['source_trace_hashes'])
        if len(hashes)!=4 or hashes & set(record['fit_episode_hashes'].values()):raise ValueError('v87_gate_overlap')
        seen.append(hashes)
    if seen[0]&seen[1]:raise ValueError('v87_gate_overlap')
    r=json.loads(Path(solver).read_text(encoding='utf8'))
    if (r.get('schema')!='v87-offline-solver-validation' or r['model_sha256']!=model_sha
            or r['source_manifest_sha256']!=manifest_sha or r['distinct_origins']!=4
            or any(not r['arms'][arm]['passed'] or len(r['arms'][arm]['rows'])!=4
                or any(not q['candidate_check']['feasible'] or not q['parent_check']['feasible']
                    for q in r['arms'][arm]['rows']) for arm in ('physics','koopman','hybrid'))):
        raise ValueError('v87_solver_gate')


if __name__=='__main__':
    from workflows.collect_learned_v82 import main
    sys.exit(main(experiment='v87'))
