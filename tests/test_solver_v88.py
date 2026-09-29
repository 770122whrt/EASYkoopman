import numpy as np


def test_infeasible_candidate_is_not_saved_by_valid_final_fallback():
    from workflows.solve_disturbance_v88 import assess_answer
    class Checker:
        def check(self,origin,state,commands,previous,reference):
            return dict(feasible=bool(np.max(abs(commands))<.1),reason='fixture',predictions=None)
    answer=dict(commands=np.zeros((20,4)),candidate_commands=np.ones((20,4)))
    result=assess_answer(Checker(),None,None,None,None,answer)
    assert result['parent_check']['feasible'] and not result['candidate_check']['feasible']
    assert not result['passed']
    answer['commands']=None;answer['candidate_commands']=np.zeros((20,4))
    result=assess_answer(Checker(),None,None,None,None,answer)
    assert result['candidate_check']['feasible'] and not result['passed']
