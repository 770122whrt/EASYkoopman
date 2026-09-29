"""Prospective fit-only screen with the original numerical improvement limits."""
import numpy as np
from workflows.identification_protocol_v29 import cases
from workflows.sparse_evaluation_v32 import _metric_record,_ratio


def fit_screen(candidates,baselines):
    catalog={q['run_id']:q for q in cases() if q['role']=='fit'}
    configurations=list(dict.fromkeys(q['configuration'] for q in catalog.values()))
    horizons=(1,20,60,128,320);scopes=('pooled','heldout');candidate_index={};baseline_index={}
    allowed=[('nonlinear',s) for s in scopes]+[('linear',s) for s in scopes]+[('known_physics','none'),('persistence','none')]
    expected_candidate={(q,s,h) for q in catalog for s in scopes for h in horizons}
    expected_baseline={(q,f,s,h) for q in catalog for f,s in allowed for h in horizons}
    def valid(r):
        q=catalog.get(r['run_id']);h=r['horizon_control_intervals']
        if (q is None or r['configuration']!=q['configuration'] or r['role']!='fit_diagnostic'
            or type(h) is not int or h not in horizons or r['origins']!=(1 if h==320 else 193-h)):
            raise ValueError('state_projection_score_identity')
        _metric_record(r)
        if not 0<=r['failed_origins']<=r['origins']:raise ValueError('state_projection_failed_origins')
    for r in candidates:
        valid(r);key=(r['run_id'],r['scope'],r['horizon_control_intervals'])
        if key not in expected_candidate or key in candidate_index or r['family']!='nonlinear_v34' or r['mode']!='full_state_projected':
            raise ValueError('state_projection_candidate_inventory')
        candidate_index[key]=r
    for r in baselines:
        if r['mode']!='projected':continue
        valid(r);key=(r['run_id'],r['family'],r['scope'],r['horizon_control_intervals'])
        if key not in expected_baseline or key in baseline_index:raise ValueError('state_projection_baseline_inventory')
        baseline_index[key]=r
    if set(candidate_index)!=expected_candidate or set(baseline_index)!=expected_baseline:raise ValueError('state_projection_score_inventory')
    all_complete=all(r['complete_aggregate'] for r in candidates);gates=[]
    for scope in scopes:
        for h in (20,60,128):
            for metric in ('endpoint_rmse','path_rmse'):
                triples=[(candidate_index[(q,scope,h)],baseline_index[(q,'linear',scope,h)],baseline_index[(q,'persistence','none',h)]) for q in catalog]
                result={'scope':scope,'horizon':h,'metric':metric,'pass':False}
                if all(r['complete_aggregate'] for t in triples for r in t):
                    den=np.maximum([t[2][metric] for t in triples],[.001]*4)
                    candidate=np.asarray([t[0][metric] for t in triples])/den;linear=np.asarray([t[1][metric] for t in triples])/den
                    groups={c:candidate[[q['configuration']==c for q in catalog.values()]].mean(0) for c in configurations}
                    ratios={c:_ratio(float(value.mean()),float(linear[[q['configuration']==c for q in catalog.values()]].mean())) for c,value in groups.items()}
                    macro=float(candidate.mean());relative=_ratio(macro,float(linear.mean()))
                    result.update(normalized_macro=macro,over_linear_macro=relative,
                        configuration_groups={c:v.tolist() for c,v in groups.items()},configuration_over_linear=ratios)
                    result['pass']=bool(macro<=.95 and all(v.mean()<=1.05 and max(v)<=1.25 for v in groups.values())
                        and relative<=.95 and max(ratios.values())<=1.05)
                gates.append(result)
    return {'pass':bool(all_complete and all(g['pass'] for g in gates)),'all_candidate_scores_complete':all_complete,
        'gates':gates,'scope':'fit_screen_only','independent_validation':False,'model_handoff':False}
