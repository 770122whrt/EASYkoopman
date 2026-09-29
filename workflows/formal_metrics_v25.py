"""Frozen v25 paired gates and whole-episode uncertainty; no fitting or I/O.

The family-wide completeness gate includes local, pooled and heldout primary
operators. Accuracy is required for heldout transfer and the pooled handoff.
This interpretation is fixed before any formal model fitting or validation.
"""
import numpy as np
from workflows.formal_contract_v25 import proposal,analysis_policy


def comparison_ratio(numerator,denominator):
    """Numerically indistinguishable perfect models are a tie, never a gain."""
    n=np.asarray(numerator,dtype=float);d=np.asarray(denominator,dtype=float)
    return np.where((n<=1e-15)&(d<=1e-15),1.,n/np.maximum(d,1e-15))


def role_cases(role):
    if role not in ('validation','test'):raise ValueError('formal_score_role')
    return [e for e in proposal()['entries'] if e['role']==role]


def _index(scores,role):
    expected={e['run_id']:e for e in role_cases(role)};result={}
    policy=analysis_policy()
    for record in scores:
        case=expected.get(record['run_id'])
        if (case is None or record['configuration']!=case['configuration'] or record['seed']!=case['seed']
                or record['horizon_control_intervals'] not in policy['horizons_control']
                or record['origins']!=513-record['horizon_control_intervals']):
            raise ValueError('formal_score_identity')
        family=record['family'];mode=record['mode'];scope=record['scope']
        if family=='persistence':valid=mode=='persistence' and scope=='none'
        else:
            valid=(family in policy['families'] and scope in ('pooled','local-'+case['configuration'],'heldout-'+case['configuration'])
                   and (mode=='projected' or family.startswith('nonlinear_') and mode=='unprojected_lift'))
        if not valid:raise ValueError('formal_score_family_scope')
        key=(family,scope,mode,record['horizon_control_intervals'],case['run_id'])
        if key in result:raise ValueError('formal_score_duplicate')
        if type(record['complete_aggregate']) is not bool:raise ValueError('formal_score_complete_type')
        if record['complete_aggregate']:
            if record['failed_origins']!=0:raise ValueError('formal_score_failure_count')
            for metric in ('endpoint_rmse','path_rmse'):
                array=np.asarray(record[metric],dtype=float)
                if array.shape!=(4,) or not np.isfinite(array).all() or np.any(array<0):
                    raise ValueError('formal_score_metric')
        elif (not 0<record['failed_origins']<=record['origins']
              or record['endpoint_rmse'] is not None or record['path_rmse'] is not None):
            raise ValueError('formal_score_failed_aggregate')
        result[key]=record
    for case in expected.values():
        for h in policy['horizons_control']:
            required=[('persistence','none','persistence')]
            required += [('nonlinear_fixed',scope,'projected') for scope in
                         ('pooled','local-'+case['configuration'],'heldout-'+case['configuration'])]
            required += [('linear_fixed',scope,'projected') for scope in ('pooled','heldout-'+case['configuration'])]
            if any((f,s,m,h,case['run_id']) not in result for f,s,m in required):
                raise ValueError('formal_score_missing')
    return result


def _paired(index,role,scope,horizon,metric):
    arrays={family:[] for family in ('persistence','linear_fixed','nonlinear_fixed')}
    for case in role_cases(role):
        active_scope='pooled' if scope=='pooled' else 'heldout-'+case['configuration']
        for family in arrays:
            key=(family,'none' if family=='persistence' else active_scope,
                 'persistence' if family=='persistence' else 'projected',horizon,case['run_id'])
            record=index[key]
            if not record['complete_aggregate']:return None
            arrays[family].append(record[metric])
    denominator=np.maximum(np.asarray(arrays['persistence']),analysis_policy()['denominator_floor'])
    return {name:np.asarray(array)/denominator for name,array in arrays.items()}


def gate_report(scores,role):
    index=_index(scores,role);policy=analysis_policy();limits=policy['gates']
    configs=proposal()['configurations'];cases=role_cases(role)
    masks={c:np.asarray([e['configuration']==c for e in cases]) for c in configs}
    primary=[r for key,r in index.items() if key[0]=='nonlinear_fixed' and key[2]=='projected']
    primary_complete=all(r['complete_aggregate'] for r in primary)
    gates=[]
    for scope in ('heldout','pooled'):
        for horizon in limits['mandatory_accuracy_horizons']:
            for metric in ('endpoint_rmse','path_rmse'):
                arrays=_paired(index,role,scope,horizon,metric)
                gate={'scope':scope,'horizon':horizon,'metric':metric,'complete_paired_comparison':arrays is not None,'pass':False}
                if arrays is not None:
                    candidate=arrays['nonlinear_fixed'];linear=arrays['linear_fixed']
                    per_config={c:candidate[masks[c]].mean(0) for c in configs}
                    macro=float(candidate.mean());velocity=float(candidate[:,2:].mean())
                    seed_counts={c:int(np.sum(candidate[masks[c],2:].mean(1)<1)) for c in configs}
                    ratio=float(comparison_ratio(macro,linear.mean()))
                    config_ratios={c:float(comparison_ratio(candidate[masks[c]].mean(),linear[masks[c]].mean())) for c in configs}
                    checks={'aggregate_pass':macro<=limits['aggregate_normalized_max'],
                            'per_configuration_pass':all(v.mean()<=limits['each_configuration_normalized_max'] for v in per_config.values()),
                            'per_configuration_metric_pass':all(np.all(v<=limits['each_configuration_each_metric_max']) for v in per_config.values()),
                            'velocity_pass':velocity<=limits['combined_velocity_max'] and min(seed_counts.values())>=limits['each_configuration_velocity_better_seed_count'],
                            'linear_comparison_pass':ratio<=limits['nonlinear_over_complete_linear_fixed_max'] and max(config_ratios.values())<=limits['each_configuration_over_linear_max']}
                    gate.update({k:bool(v) for k,v in checks.items()})
                    gate.update(normalized_macro=macro,per_configuration_metrics={c:v.tolist() for c,v in per_config.items()},
                                combined_velocity=velocity,seed_velocity_better_counts=seed_counts,
                                over_linear_normalized_macro=ratio,per_configuration_over_linear=config_ratios)
                    gate['pass']=all(checks.values())
                gates.append(gate)
    return {'decision':'GO' if primary_complete and all(g['pass'] for g in gates) else 'NO_GO',
            'role':role,'primary_all_scopes_complete':primary_complete,
            'primary_complete_records':sum(r['complete_aggregate'] for r in primary),
            'primary_expected_records':360,'gates':gates,'model_handoff':False,
            'limits':'Prediction gate only; formal source/role/inventory audit and matching controller handoff remain separate.'}


def bootstrap_report(scores,role):
    if role!='test':raise ValueError('formal_bootstrap_test_only')
    index=_index(scores,role);policy=analysis_policy();settings=policy['uncertainty']
    rng=np.random.default_rng(settings['seed']);count=settings['paired_episode_block_bootstrap_replicates']
    cases=role_cases(role);blocks=[np.flatnonzero([e['configuration']==c for e in cases]) for c in proposal()['configurations']]
    # Reuse paired whole-episode draws for all metrics, horizons and comparators.
    draw=np.concatenate([rng.choice(block,size=(count,len(block)),replace=True) for block in blocks],axis=1)
    intervals=[]
    for scope in ('heldout','pooled'):
        for horizon in policy['gates']['mandatory_accuracy_horizons']:
            for metric in ('endpoint_rmse','path_rmse'):
                item={'scope':scope,'horizon':horizon,'metric':metric}
                arrays=_paired(index,role,scope,horizon,metric)
                if arrays is None:item['status']='unavailable_incomplete_paired_comparison'
                else:
                    candidate=arrays['nonlinear_fixed'][draw].mean(axis=(1,2))
                    linear=arrays['linear_fixed'][draw].mean(axis=(1,2))
                    item.update(status='descriptive_interval',normalized_macro_interval=np.percentile(candidate,settings['percentiles']).tolist(),
                                over_linear_interval=np.percentile(comparison_ratio(candidate,linear),settings['percentiles']).tolist())
                intervals.append(item)
    return {'replicates':count,'seed':settings['seed'],'unit':'configuration_stratified_whole_episode',
            'blocks_per_configuration':3,'paired':True,'intervals':intervals,'interpretation':settings['interpretation']}
