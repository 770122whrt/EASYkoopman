"""Synthetic metric fixtures; no simulation or canonical evidence is produced."""
import copy
import numpy as np
import pytest
from workflows.formal_contract_v25 import proposal,analysis_policy


def records(role='validation'):
    result=[]
    for case in proposal()['entries']:
        if case['role']!=role:continue
        for h in analysis_policy()['horizons_control']:
            for family,scopes,value in [('persistence',['none'],1.),
                    ('linear_fixed',['heldout-'+case['configuration'],'pooled'],.8),
                    ('nonlinear_fixed',['heldout-'+case['configuration'],'pooled','local-'+case['configuration']],.25)]:
                for scope in scopes:
                    result.append({'family':family,'scope':scope,'mode':'persistence' if family=='persistence' else 'projected',
                        'run_id':case['run_id'],'configuration':case['configuration'],'seed':case['seed'],
                        'horizon_control_intervals':h,'origins':513-h,'failed_origins':0,
                        'complete_aggregate':True,'endpoint_rmse':[value]*4,'path_rmse':[value]*4})
    return result


def test_complete_paired_metrics_pass_including_pooled_handoff():
    from workflows.formal_metrics_v25 import gate_report
    report=gate_report(records(),'validation')
    assert report['decision']=='GO' and len(report['gates'])==12
    assert report['primary_complete_records']==360


def test_one_configuration_attitude_failure_cannot_hide_in_good_macro():
    from workflows.formal_metrics_v25 import gate_report
    scores=records()
    for s in scores:
        if s['family']=='nonlinear_fixed' and s['configuration']=='base' and s['horizon_control_intervals']==60:
            s['endpoint_rmse'][1]=1.14
    report=gate_report(scores,'validation')
    assert report['decision']=='NO_GO'
    gate=next(g for g in report['gates'] if g['scope']=='heldout' and g['horizon']==60 and g['metric']=='endpoint_rmse')
    assert gate['normalized_macro']<1 and not gate['per_configuration_metric_pass']


@pytest.mark.parametrize('family',['nonlinear_fixed','linear_fixed'])
def test_failed_origin_nulls_paired_comparison_instead_of_survivor_average(family):
    from workflows.formal_metrics_v25 import gate_report
    scores=records();s=next(s for s in scores if s['family']==family and s['horizon_control_intervals']==60)
    s.update(complete_aggregate=False,failed_origins=1,endpoint_rmse=None,path_rmse=None)
    report=gate_report(scores,'validation')
    assert report['decision']=='NO_GO'
    gate=next(g for g in report['gates'] if g['scope']=='heldout' and g['horizon']==60 and g['metric']=='endpoint_rmse')
    assert not gate['complete_paired_comparison'] and 'normalized_macro' not in gate


@pytest.mark.parametrize('mutation',['duplicate','missing','wrong_configuration','wrong_role','nonfinite'])
def test_corrupted_or_mixed_role_scores_are_rejected(mutation):
    from workflows.formal_metrics_v25 import gate_report
    scores=records()
    if mutation=='duplicate':scores.append(copy.deepcopy(scores[0]))
    elif mutation=='missing':scores.pop(0)
    elif mutation=='wrong_configuration':scores[0]['configuration']='uuv6'
    elif mutation=='wrong_role':scores[0]['run_id']=scores[0]['run_id'].replace('validation-8461','test-8471')
    else:scores[0]['endpoint_rmse'][0]=float('nan')
    with pytest.raises(ValueError,match='formal_score_'):gate_report(scores,'validation')


def test_pooled_failure_blocks_handoff_even_when_heldout_is_good():
    from workflows.formal_metrics_v25 import gate_report
    scores=records()
    for s in scores:
        if s['family']=='nonlinear_fixed' and s['scope']=='pooled' and s['horizon_control_intervals']==512:
            s.update(complete_aggregate=False,failed_origins=1,endpoint_rmse=None,path_rmse=None)
    assert gate_report(scores,'validation')['decision']=='NO_GO'


def test_two_perfect_models_do_not_count_as_nonlinear_improvement():
    from workflows.formal_metrics_v25 import gate_report,bootstrap_report
    scores=records('test')
    for score in scores:
        if score['family'] in ('linear_fixed','nonlinear_fixed'):
            score['endpoint_rmse']=[0.]*4;score['path_rmse']=[0.]*4
    decision=gate_report(scores,'test')
    assert decision['decision']=='NO_GO'
    assert all(g['over_linear_normalized_macro']==1. for g in decision['gates'])
    assert all(r['over_linear_interval']==[1.,1.] for r in bootstrap_report(scores,'test')['intervals'])


def test_bootstrap_is_paired_whole_episode_deterministic_and_test_only():
    from workflows.formal_metrics_v25 import bootstrap_report
    a=bootstrap_report(records('test'),'test');b=bootstrap_report(records('test'),'test')
    assert a==b and a['replicates']==2000 and a['unit']=='configuration_stratified_whole_episode'
    for result in a['intervals']:
        np.testing.assert_allclose(result['normalized_macro_interval'],[.25,.25])
        np.testing.assert_allclose(result['over_linear_interval'],[.3125,.3125])
    with pytest.raises(ValueError,match='formal_bootstrap_test_only'):bootstrap_report(records(),'validation')
