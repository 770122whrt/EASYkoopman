import copy
from pathlib import Path
import numpy as np
import pytest
from workflows.evaluate_projected_edmd_v24 import rollout


def fixture_score():
    x=np.zeros((1025,11));x[:,1]=1;x[:,0]=np.arange(1025)*.001
    score=rollout(x,np.zeros((1024,6)),None,None,None,'persistence',20)
    return x,score


@pytest.mark.parametrize('mutation',['endpoint_average','path_average','origin_index','prediction'])
def test_saved_score_audit_recomputes_arithmetic_and_endpoints(mutation):
    from workflows.evaluate_formal_v25 import audit_score
    x,score=fixture_score();audit_score(score,x)
    if mutation=='endpoint_average':score['endpoint_rmse'][0]+=.001
    elif mutation=='path_average':score['path_rmse'][0]+=.001
    elif mutation=='origin_index':score['origin_control_indices'][0]=1
    else:score['final_predictions'][0][0]+=.5
    with pytest.raises(ValueError,match='formal_audit_'):audit_score(score,x)


def test_test_stage_refuses_absent_freeze_before_creating_outputs(tmp_path):
    from workflows.evaluate_formal_v25 import verify_freeze
    with pytest.raises(ValueError,match='formal_freeze_missing'):
        verify_freeze(tmp_path/'output',tmp_path/'evidence',{'source_commit':'a'*40},'b'*40)
    assert not (tmp_path/'output').exists()


def test_bounded_analysis_keeps_consumed_time_across_stages():
    from workflows.evaluate_formal_v25 import remaining_seconds
    assert remaining_seconds({'charged_seconds':300})==3300
    with pytest.raises(ValueError,match='formal_analysis_time_budget'):remaining_seconds({'charged_seconds':3600})


def test_unapproved_analysis_stops_before_loading_data_or_creating_results(tmp_path):
    from workflows.evaluate_formal_v25 import check_approval
    with pytest.raises(ValueError,match='formal_d23_not_approved'):check_approval({'decision':'pending'})
