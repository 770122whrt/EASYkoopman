import numpy as np
from workflows.feedback_inverse_v31 import solve_feasible_control
from workflows.feedback_inverse_v28 import solve_feasible_control as old_solve
from workflows.workpoint_v27 import _steady,mechanics,ACCELERATION_TOLERANCE
from workflows.control_seam_v23 import ControlKernel

FAILURE_TARGET=[0.,0.,2.174412985889643,.03874279078541216,-.4764078109017975,.4250576427396277]

def test_deadzone_failure_target_has_a_feasible_source_command(monkeypatch):
    # Frozen actual server exit point. Host LAPACK builds can choose a different
    # v28 inverse, so isolate the failed branch rather than requiring every host
    # to repeat the exact optimizer path.
    from workflows import feedback_inverse_v31 as module
    u=[-.0020004000980407,-.042008399963378906,.00800399947911501,.012002400122582912]
    w,s=_steady(ControlKernel('long_body'),u);m=mechanics('long_body')
    assert np.any(np.abs((w-FAILURE_TARGET)/np.r_[[m['mass_kg']]*3,m['inertia_kg_m2']])>ACCELERATION_TOLERANCE)
    monkeypatch.setattr(module,'previous_solve',lambda name,target:{'command_4':u,'within_tolerance':False,'pwm_raw':s['pwm_raw'],'iterations':6})
    r=solve_feasible_control('long_body',FAILURE_TARGET)
    assert r['within_tolerance']
    m=mechanics('long_body');w,s=_steady(ControlKernel('long_body'),r['command_4'])
    error=(w-FAILURE_TARGET)/np.r_[[m['mass_kg']]*3,m['inertia_kg_m2']]
    assert np.all(np.abs(error)<=ACCELERATION_TOLERANCE)
    assert r['pwm_headroom']>=.05 and np.min(np.abs(np.abs(s['pwm_raw'])-float(np.float32(.02))))>2e-6

def test_already_feasible_v28_solution_is_preserved():
    target=[0.,0.,.209927,-11.12434,11.12434,0.]
    assert solve_feasible_control('asymmetric',target)==old_solve('asymmetric',target)
