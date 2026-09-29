import importlib
import numpy as np
import pytest


def api():
    assert importlib.util.find_spec('workflows.protocol_v86'), 'frozen disturbance protocol missing'
    return importlib.import_module('workflows.protocol_v86')


def test_episode_split_and_signal_are_frozen_and_disjoint():
    m = api(); cases = m.cases()
    assert len(cases)==8 and len({q['seed'] for q in cases})==8
    assert [q['role'] for q in cases].count('train')==4
    assert [q['role'] for q in cases].count('validation')==2
    assert [q['role'] for q in cases].count('test')==2
    for q in cases:
        signal = m.excitation(q)
        assert signal.shape==(160,4) and np.isfinite(signal).all()
        np.testing.assert_array_equal(signal[:64],0.)
        assert q['hidden_drag_fraction']==.2
    assert m.protocol()['ridge']==.001
    assert m.protocol()['history_states']==1


def test_test_membership_is_not_accepted_as_training():
    m=api(); rows=m.cases()
    m.validate_split(rows[:4], rows[4:6], rows[6:])
    with pytest.raises(ValueError,match='split'):
        m.validate_split(rows[:3]+rows[-1:],rows[4:6],rows[6:])


@pytest.mark.parametrize('kind',['physics','koopman','hybrid'])
def test_closed_loop_case_matches_task_initial_state_and_disturbance(kind):
    m=api();q=m.case_spec('base',kind,True,'pitch_pos')
    assert q['controls']==60 and q['hidden_drag_fraction']==.2
    assert q['configuration']=='base'
    assert q['seed']==m.case_spec('base','physics',True,'pitch_pos')['seed']
    with pytest.raises(ValueError):m.case_spec('uuv4',kind,True,'pitch_pos')
