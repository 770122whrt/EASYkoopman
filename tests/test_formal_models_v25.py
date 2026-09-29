"""Mathematical/source-role fixtures; no canonical data or Isaac claims."""
from dataclasses import asdict
import copy
import numpy as np
import pytest
from workflows.formal_contract_v25 import proposal
from koopman.projected_edmd_v24 import PhysicalContext,observable


def episodes(role='fit',configuration='base'):
    from workflows.formal_models_v25 import Episode
    result=[]
    for case in proposal()['entries']:
        if case['configuration']!=configuration or case['role']!=role:continue
        rng=np.random.default_rng(case['seed']);x=np.zeros((1025,11));x[:,1]=1
        x[:,0]=1+np.cumsum(rng.normal(0,.001,1025));x[:,5:]=rng.normal(0,.05,(1025,6))
        context=PhysicalContext(20,[.4,.8,1],[0,0,.01],.02,1)
        result.append(Episode(case,'a'*64,x,rng.normal(0,.1,(1024,6)),context))
    return result


def test_exact_grid_has_68_models_and_heldout_never_trains_target():
    from workflows.formal_models_v25 import model_specs
    specs=model_specs();assert len(specs)==68 and len({s['model_id'] for s in specs})==68
    for spec in specs:
        if spec['scope'].startswith('heldout-'):
            assert len(spec['fit_configurations'])==7
            assert not set(spec['fit_configurations']) & set(spec['evaluation_configurations'])


@pytest.mark.parametrize('family',['linear_free','nonlinear_free','linear_fixed','nonlinear_fixed'])
def test_serialized_operator_roundtrip_preserves_prediction_and_fit_only_scaling(family):
    from workflows.formal_models_v25 import fit_one,load_operator,model_specs,json_value
    spec=next(s for s in model_specs() if s['family']==family and s['scope']=='local-base');ep=episodes()
    record,op=fit_one(spec,ep);restored=load_operator(family,json_value(asdict(op)))
    dictionary=family.split('_')[0];features=np.concatenate([observable(e.states[:-1],e.context,dictionary) for e in ep])
    np.testing.assert_allclose(op.mean,features.mean(0),atol=0,rtol=0)
    assert set(record['fit_episode_hashes'])=={e.case['run_id'] for e in ep}
    a=op.bind(ep[0].context,dictionary) if family.endswith('_fixed') else op
    b=restored.bind(ep[0].context,dictionary) if family.endswith('_fixed') else restored
    z=(features[:2]-op.mean)/op.scale
    np.testing.assert_allclose(a.advance_lift(z,ep[0].acceleration[:2]),b.advance_lift(z,ep[0].acceleration[:2]),atol=0,rtol=0)
    assert not restored.mean.flags.writeable


@pytest.mark.parametrize('role',['validation','test','preflight'])
def test_training_rejects_nonfit_episode_before_any_fitting(role):
    from workflows.formal_models_v25 import fit_one,model_specs
    spec=next(s for s in model_specs() if s['family']=='nonlinear_fixed' and s['scope']=='local-base')
    ep=episodes();ep[0].case=dict(ep[0].case,role=role)
    with pytest.raises(ValueError,match='formal_fit_role_inventory'):fit_one(spec,ep)


@pytest.mark.parametrize('mutation',['matrix_shape','nonfinite','zero_scale','force_coefficient'])
def test_corrupt_frozen_operator_is_rejected(mutation):
    from workflows.formal_models_v25 import fit_one,load_operator,model_specs,json_value
    spec=next(s for s in model_specs() if s['family']=='linear_fixed' and s['scope']=='local-base')
    _,op=fit_one(spec,episodes());payload=json_value(asdict(op))
    if mutation=='matrix_shape':payload['coefficient'].pop()
    elif mutation=='nonfinite':payload['coefficient'][0][0]=float('nan')
    elif mutation=='zero_scale':payload['scale'][0]=0
    else:payload['audit']['learned_force_coefficients']=1
    with pytest.raises(ValueError,match='formal_operator_'):load_operator('linear_fixed',payload)
