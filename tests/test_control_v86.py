import importlib
import json
from types import SimpleNamespace
import numpy as np
import pytest


def test_parent_retains_rejected_timeout_candidate_as_evidence():
    from koopman.preview_mpc_v79 import PreviewMPC
    from test_preview_decision_v79 import Checker
    class Worker:
        def call(self,request):
            return dict(status='baseline_retained',commands=request['baseline'],reason=None,
                solver=dict(success=False,timed_out=True,return_status='Maximum_CpuTime_Exceeded'),
                candidate_commands=np.full((2,4),.8),command_bound_violation=.1,
                solution_check=dict(feasible=False,reason='command_slew',cost=None))
    solver=PreviewMPC(Checker(),Worker(),lambda:None,preview_enabled=False)
    x=np.r_[5.5,1.,np.zeros(9)]
    result=solver.solve(origin=SimpleNamespace(origin_control=0),initial_state=x,
        baseline=np.full((2,4),.03),previous=np.full(4,.03),reference=x[:5])
    np.testing.assert_array_equal(result['candidate_commands'],np.full((2,4),.8))
    assert result['solution_check']['feasible'] is False
    assert result['solver']['success'] is False


def test_control_rejects_failed_prediction_even_if_solver_succeeded(tmp_path):
    from workflows.collect_disturbance_control_v86 import verify_control_gate
    files=[]
    for role in ('validation','test'):
        p=tmp_path/(role+'.json');p.write_text(json.dumps(dict(schema='v86-prediction-evaluation',role=role,
            model_sha256='a'*64,model_fits=0,gates={'koopman':dict(prediction_passed=False)})))
        files.append(p)
    with pytest.raises(ValueError,match='prediction_gate'):
        verify_control_gate('a'*64,'koopman',*files,tmp_path/'absent-solver.json')


def test_solver_validation_recomputes_numpy_prediction_and_feasibility():
    assert importlib.util.find_spec('workflows.solve_disturbance_v86'), 'three-arm solver verification missing'


@pytest.mark.parametrize('kind',['koopman','hybrid'])
def test_full_latent_model_is_used_by_real_continuous_solver(kind):
    pytest.importorskip('casadi')
    from test_disturbance_lifted_v86 import predictor
    from test_continuous_mpc_v76 import setup
    from koopman.continuous_mpc_v80 import ContinuousMPC
    from koopman.preview_solver_v80 import ExactChecker
    old,_,args=setup();p=predictor(kind)
    solver=ContinuousMPC(old.domain,p,horizon=6,allow_diagnostic=True,solve_seconds=.1,max_iterations=10)
    result=solver.solve(**args)
    assert result['candidate_commands'] is not None
    assert result['exact_feasible'],result
    independent=ExactChecker(old.domain,p,horizon=6).check(args['origin'],args['initial_state'],
        result['commands'],args['previous'],args['reference'])
    assert independent['feasible']
    np.testing.assert_allclose(independent['predictions'],result['predictions'],atol=1e-12)
