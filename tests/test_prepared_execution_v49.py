"""Retain v48 issue contracts and compare the prepared live recurrence."""
import numpy as np
import pytest

# Re-run the same observable execution contracts with only the live map replaced.
from test_execution_ledger_v48 import *
import koopman.execution_ledger_v48 as original_ledger_module
from koopman.command_state_v39 import CausalCommandState


@pytest.fixture(autouse=True)
def use_prepared_live_map(monkeypatch):
    from koopman.prepared_execution_v49 import PreparedExecutionLedger
    monkeypatch.setattr(original_ledger_module,'ExecutionLedger',PreparedExecutionLedger)


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_prepared_ack_recurrence_matches_original_for_changing_signed_commands(name):
    from koopman.prepared_execution_v49 import PreparedCausalCommandState
    c=context(name)
    old=CausalCommandState(name,c,episode_id='same',zero_rotor_reset_verified=True)
    new=PreparedCausalCommandState(name,c,episode_id='same',zero_rotor_reset_verified=True)
    random=np.random.default_rng(490).uniform(-.15,.15,(20,4))
    for i,u in enumerate(np.repeat(random,2,axis=0)):
        for obj in (old,new):obj.record_issued(u,physics_index=i,episode_id='same')
        if i%2:
            a=old.snapshot(configuration=name,context=c,origin_control=(i+1)//2,episode_id='same')
            b=new.snapshot(configuration=name,context=c,origin_control=(i+1)//2,episode_id='same')
            np.testing.assert_allclose(a._actuator.current(),b._actuator.current(),rtol=1e-12,atol=1e-12)
            assert a._actuator.elapsed_time==b._actuator.elapsed_time


def test_real_ack_path_no_longer_calls_the_old_pid_diagnostic_kernel(monkeypatch):
    from workflows.control_seam_v23 import ControlKernel
    ledger,u,_=setup()
    def forbidden(*args,**kwargs):raise AssertionError('old diagnostic kernel called during ack')
    monkeypatch.setattr(ControlKernel,'command',forbidden)
    execute(ledger,u,startup=True)
    execute(ledger,u)
    assert ledger.physics_index==4 and ledger.startup_consumed
