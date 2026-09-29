from copy import deepcopy
import pytest


def test_fixed_scope_and_separate_diagnostic_identity():
    from workflows.free_water_microtrace_v26 import cases,validate_case
    q=cases()
    assert len(q)==6 and sum(c['intervals'] for c in q)==832
    assert {c['role'] for c in q}=={'diagnostic'}
    assert len({c['run_id'] for c in q})==6
    for c in q:assert validate_case(c)==c


@pytest.mark.parametrize('field,value',[('intervals',512),('seed',8453),('role','fit'),
    ('starting_z_m',10.),('configuration','long_body'),('contact_observer',False)])
def test_case_mutation_cannot_enter_collector(field,value):
    from workflows.free_water_microtrace_v26 import cases,validate_case
    q=deepcopy(cases()[3]);q[field]=value
    with pytest.raises(ValueError,match='free_water_fixed_case'):
        validate_case(q)


def test_height_pairs_have_identical_commands():
    import numpy as np
    from workflows.free_water_microtrace_v26 import cases
    from workflows.pilot_control_v24 import commands
    q=cases()
    for i in (0,2,4):np.testing.assert_array_equal(commands(q[i]),commands(q[i+1]))


def test_high_altitude_never_uses_diagnostic_continue_mode():
    from workflows.free_water_microtrace_v26 import cases
    for q in cases():
        if q['starting_z_m']>1.5 and q['contact_observer']:assert q['stop_on_rejection']
