"""Metadata changes on in-memory fixtures only; no canonical result promotion."""
import importlib
from copy import deepcopy
from dataclasses import asdict
import pytest
from test_validate_continuous_v76 import evidence
from koopman.control_objective_v44 import ObjectiveWeights


def prepared(evidence):
    assert importlib.util.find_spec('workflows.validate_reliable_v77'), 'v77 validator missing'
    from workflows.validate_reliable_v77 import validate
    original,assets=evidence;data=deepcopy(original)
    data.update(schema='reliable-control-v77',collector_pid=123)
    data['case']['profile']='repair';data['model']['weights']=asdict(ObjectiveWeights())
    return validate,data,assets


def test_feedback_physics_contract_remains_unchanged(evidence):
    validate,d,a=prepared(evidence);assert validate(d,a,0)['physics_steps']==240


@pytest.mark.parametrize('fault',['profile','weights','horizon'])
def test_mismatched_optimization_profile_rejected(evidence,fault):
    validate,d,a=prepared(evidence)
    if fault=='profile':d['case']['profile']='unknown'
    if fault=='weights':d['model']['weights']['depth']=2.
    if fault=='horizon':d['model']['horizon_macro_steps']=20
    with pytest.raises(ValueError):validate(d,a,0)
