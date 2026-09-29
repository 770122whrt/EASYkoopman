"""The cross-model comparison requires a genuinely shared initial control origin."""
import copy
import importlib
import numpy as np
import pytest


def api():
    assert importlib.util.find_spec('workflows.analyze_initial_plans_v82')
    return importlib.import_module('workflows.analyze_initial_plans_v82')


def origins():
    row=dict(case=dict(configuration='base',profile='depth4_h20',preview_enabled=True,
        seed=19760,reference=[5.5,1,0,0,0],task='pitch_pos',controls=60),
        state=np.array([5.5,1,0,0,0,0,0,0,0,0,0.]),startup_command=np.array([0,0,0,.03]),
        observed_rotor=np.ones(8),origin_rotor=np.ones(8),origin_clock=.033333335,
        observed_clock=.033333335,reset_state=np.array([5.5,1,0,0,0,0,0,0,0,0,0.]))
    return {k:copy.deepcopy(row) for k in ('physics','learned_0.001','learned_0.1')}


def test_shared_origin_accepts_small_numerical_tolerance():
    rows=origins();rows['learned_0.1']['state'][0]+=5e-8
    result=api().verify_common_origins(rows)
    assert result['maximum_differences']['state']<1e-7


@pytest.mark.parametrize('field',['state','startup_command','observed_rotor','origin_rotor','origin_clock','reset_state'])
def test_different_origin_is_not_an_algorithm_comparison(field):
    rows=origins()
    if field=='origin_clock':rows['learned_0.1'][field]+=.01
    else:rows['learned_0.1'][field][0]+=.001
    with pytest.raises(ValueError,match='common_origin'):
        api().verify_common_origins(rows)


def test_nine_plan_model_cells_are_evaluated_without_solving():
    calls=[]
    class Checker:
        horizon=20
        def __init__(self,bias):self.bias=bias
        def check(self,origin,state,commands,previous,reference):
            calls.append((origin,state.copy(),commands.copy()))
            return dict(feasible=True,reason=None,cost=float(np.sum(commands))+self.bias,predictions=np.zeros((80,11)))
    plans={name:np.full((20,4),value) for name,value in [('physics',.1),('learned_0.001',.05),('learned_0.1',.02)]}
    checkers={name:Checker(i) for i,name in enumerate(plans)}
    result=api().cross_evaluate(checkers,'shared',np.zeros(11),np.zeros(4),np.zeros(5),plans)
    assert len(result)==9 and len(calls)==9
    assert all(c[0]=='shared' for c in calls)
    costs={r['plan_source']:r['cost'] for r in result if r['evaluation_model']=='physics'}
    assert costs['learned_0.1']<costs['physics']


def test_short_candidate_cannot_enter_cross_plan_report():
    plans={name:np.zeros((20,4)) for name in ('physics','learned_0.001','learned_0.1')}
    plans['learned_0.1']=np.zeros((1,4))
    with pytest.raises(ValueError,match='plan_shape'):
        api().cross_evaluate({},None,np.zeros(11),np.zeros(4),np.zeros(5),plans)
