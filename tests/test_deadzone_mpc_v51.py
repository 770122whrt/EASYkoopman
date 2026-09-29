"""Runtime deadzone margin must screen every candidate before optimization."""
from dataclasses import replace
import numpy as np
import pytest

from test_bounded_mpc_v44 import fixtures
from test_bounded_mpc_v45 import compare
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS


def solvers(name='base'):
    from koopman.bounded_mpc_v45 import BoundedMPC as Old
    from koopman.bounded_mpc_v51 import BoundedMPC as New
    live,d,fixture,args=fixtures(name)
    kw=dict(model_id=d.model_id,config=fixture.config,weights=fixture.weights,allow_diagnostic=True)
    return live,Old(d,fixture.predictor,**kw),New(d,fixture.predictor,**kw),args


def test_better_cost_cannot_select_a_command_at_deadzone_boundary():
    live,old,new,args=solvers();cfg=replace(old.config,perturbation=(.002,)*4)
    old.config=new.config=cfg
    args['previous'][3]=.018;args['baseline'][:,3]=.018
    before=old.solve(**args);after=new.solve(**args)
    assert before['selected_index']==8 and before['status']=='selected'
    assert after['selected_index']!=8 and after['status'] in ('baseline','selected')
    assert after['candidates'][8]['rejection']['reason']=='raw_pwm_deadzone_margin'
    assert not after['candidates'][8]['feasible']
    assert live.physics_index==0


@pytest.mark.parametrize('u',[.02,-.02,.020001,-.020001,.019999,-.019999])
def test_ambiguous_baseline_rejects_before_any_model_call(u):
    _,_,solver,args=solvers();args['previous'][3]=u;args['baseline'][:,3]=u
    def forbidden(*args):raise AssertionError('an inadmissible baseline reached prediction')
    solver.predictor=forbidden
    got=solver.solve(**args)
    assert got['status']=='no_plan' and got['reason']=='baseline_infeasible'
    assert got['candidates'][0]['rejection']['reason']=='raw_pwm_deadzone_margin'


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_legal_source_cases_keep_existing_predictions_selection_and_cost(name):
    _,old,new,args=solvers(name)
    compare(new.solve(**args),old.solve(**args))


def test_recovery_worker_uses_candidate_filter_and_retains_final_validation():
    from koopman.recovery_solver_v51 import RecoverySolver
    from koopman.bounded_mpc_v51 import BoundedMPC
    from test_recovery_solver_v50 import request_and_solver
    ledger,req,old=request_and_solver()
    solver=RecoverySolver(old.domain,old.baseline.context,old.solver.predictor,
        config=old.config,feedback_config=old.baseline.config,allow_diagnostic=True)
    assert isinstance(solver.solver,BoundedMPC)
    got=solver(req)
    assert got['status'] in ('selected','baseline') and not got['runtime_eligible']
    np.testing.assert_array_equal(got['commands'][:8],req.prefix)
    assert ledger.physics_index==2
