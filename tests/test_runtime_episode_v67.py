import pytest
from test_runtime_episode_v57 import Clock,Session

class FourSession(Session):
    def run_interval(self,*a,**k):
        result=super().run_interval(*a,**k)
        self.runtime.ledger.physics_index+=2
        return result

def run(s,c,mode='startup_then_realtime'):
    from workflows.runtime_episode_v67 import run_intervals
    return run_intervals(s,lambda _:None,[5.5,1,0,0,0],reference_id='ref',controls=4,mode=mode,clock=c,sleep=c.sleep)

def test_30hz_means_four_physics_steps_and_30hz_wall_pacing():
    c=Clock();s=FourSession(c,cost=.028)
    r=run(s,c)
    assert s.runtime.ledger.physics_index==16
    assert r['simulated_seconds']==pytest.approx(4/30)
    assert c.now==pytest.approx(.028+3/30)
    assert r['steady_deadline_misses']==0

def test_60hz_receipts_cannot_masquerade_as_30hz():
    c=Clock();s=Session(c,cost=.001)
    with pytest.raises(ValueError,match='incomplete_receipts'):run(s,c)

@pytest.mark.parametrize('mode',['startup_then_realtime','simulation_effect'])
def test_34ms_is_still_late_at_30hz(mode):
    c=Clock();s=FourSession(c,cost=.034)
    if mode=='startup_then_realtime':
        with pytest.raises(ValueError,match='steady_deadline'):run(s,c,mode)
    else:assert run(s,c,mode)['steady_deadline_misses']==3
