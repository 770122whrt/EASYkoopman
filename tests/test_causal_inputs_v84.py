import importlib
import numpy as np
import pytest
from test_prepared_projected_v40 import context


def api():
    assert importlib.util.find_spec('workflows.verify_causal_inputs_v84'), 'causal replay runner missing'
    return importlib.import_module('workflows.verify_causal_inputs_v84')


def test_command_replay_is_causal_and_branch_isolated():
    m=api();cmd=np.zeros((20,4));cmd[:,3]=.05
    a=m.replay_inputs('base',context(),cmd,origin=8,horizon=8)
    changed=cmd.copy();changed[14:,3]=.15
    b=m.replay_inputs('base',context(),changed,origin=8,horizon=8)
    np.testing.assert_array_equal(a[:6],b[:6]);assert np.max(abs(a[6:]-b[6:]))>0
    np.testing.assert_array_equal(a,m.replay_inputs('base',context(),cmd,origin=8,horizon=8))
    np.testing.assert_array_equal(cmd[:,3],.05)


def test_replay_rejects_missing_history_and_broken_hold():
    m=api();cmd=np.zeros((12,4));cmd[1,3]=.1
    with pytest.raises(ValueError,match='hold'):m.replay_inputs('base',context(),cmd,origin=4,horizon=8)
    with pytest.raises(ValueError):m.replay_inputs('base',context(),np.zeros((2,4)),origin=4,horizon=8)
