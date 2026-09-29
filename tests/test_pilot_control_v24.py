import importlib.util
import numpy as np
import pytest


def module():
    assert importlib.util.find_spec('workflows.pilot_control_v24'), 'pilot runner missing'
    from workflows import pilot_control_v24
    return pilot_control_v24


def spec(**changes):
    return {'run_id':'local-test','configuration':'uuv4','seed':8400,'mode':'direct_pre_tam_v24',
            'intervals':32,'excitation':'prbs','amplitudes':[.04,.04,.08,.2],
            'hold_intervals':4,'trace':True,'replay_path':None,**changes}


def test_generation_is_seeded_bounded_masked_and_isolated_from_global_rng():
    m=module();s=m.validate_request(spec());a=m.commands(s)
    np.random.seed(33);np.random.normal(size=500)
    np.testing.assert_array_equal(a,m.commands(s))
    assert a.shape==(32,4) and np.all(a[:,2]==0)
    assert np.all(np.abs(a)<=np.asarray(s['amplitudes'])+1e-8)
    assert not np.array_equal(a,m.commands(m.validate_request(spec(seed=8401))))


@pytest.mark.parametrize('changes',[{'run_id':'../escape'},{'intervals':512},{'amplitudes':[1.1]*4},{'mode':'unknown'},{'configuration':'not_known'},{'seed':True},{'hold_intervals':0}])
def test_bad_request_rejected(changes):
    with pytest.raises(ValueError):module().validate_request(spec(**changes))


def test_replay_is_diagnostic_only_and_requires_a_bound_source_trace():
    with pytest.raises(ValueError,match='replay_path'):
        module().validate_request(spec(mode='direct_sequence_replay_v24'))
    with pytest.raises(ValueError,match='replay_forbidden'):
        module().validate_request(spec(replay_path='x.json'))
