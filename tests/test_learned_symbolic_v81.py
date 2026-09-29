"""Server CasADi parity of the independently trained v81 schema and causal state.

These are numeric interface checks, not Isaac closed-loop evidence. The local
environment intentionally skips only the CasADi cases when it is unavailable.
"""
import copy
import json
import os
from pathlib import Path
import numpy as np
import pytest
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.command_state_v39 import CausalCommandState
from koopman.learned_velocity_v81 import prepare_learned, seal_record
from test_prepared_projected_v40 import context

MODEL_DIGESTS={
    '0.001':'0b199fae1d2fac89ed3934c81beead09faf3c3d96666eed682e31d8cefc414f7',
    '0.1':'862b0e4f5203b35ce869bacff7a2387b58d5a035ff73a7f87aba9f0cec6e479f'}


@pytest.fixture(scope='module',params=tuple(MODEL_DIGESTS))
def record(request):
    directory=Path(os.environ.get('V81_MODEL_DIRECTORY',str(Path(__file__).resolve().parents[1]/
        'docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion')))
    result=json.loads((directory/f'pooled__learned_{request.param}.json').read_text())
    assert result['schema']=='projected-controlled-edmd-velocity-v81'
    assert result['content_sha256']==MODEL_DIGESTS[request.param]
    return result


def setup(name,record):
    c=context(name);predictor=prepare_learned(record,c,expected_sha256=record['content_sha256'])
    live=CausalCommandState(name,c,episode_id='v81_parity',zero_rotor_reset_verified=True)
    command=np.array([.013,-.017,0.,.31],dtype=np.float32)
    for i in range(12):live.record_issued(command,physics_index=i,episode_id='v81_parity')
    origin=live.snapshot(configuration=name,context=c,origin_control=6,episode_id='v81_parity')
    attitude=np.array([1.,.003,-.004,.002]);attitude/=np.linalg.norm(attitude)
    x=np.r_[5.5,attitude,[.003,-.002,.004,.004,-.003,.002]]
    controls=np.tile(command,(20,1))
    controls[:,0]+=np.linspace(0,.002,20,dtype=np.float32)
    controls[:,1]-=np.linspace(0,.001,20,dtype=np.float32)
    return c,predictor,live,origin,x,controls


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_actual_pooled_record_has_causal_numpy_eighty_step_path(name,record):
    c,predictor,live,origin,x,controls=setup(name,record)
    speed=origin._actuator.current().copy();clock=origin._actuator.elapsed_time
    assert np.any(speed!=0) and clock>0 and np.any(x[2:5]!=0)
    result=origin.forecast(x,np.repeat(controls,2,axis=0),predictor)
    assert result['complete'],result['failure']
    assert result['predictions'].shape==(80,11)
    np.testing.assert_array_equal(origin._actuator.current(),speed)
    assert origin._actuator.elapsed_time==clock and live.physics_index==12


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_real_symbolic_uses_same_learned_matrix_and_causal_eighty_steps(name,record):
    pytest.importorskip('casadi',reason='real CasADi equivalence requires isolated server environment')
    from koopman.continuous_prediction_v76 import SymbolicPlant
    c,predictor,live,origin,x,controls=setup(name,record)
    plant=SymbolicPlant(predictor,name)
    np.testing.assert_array_equal(plant.base._matrix[:,10:16],record['velocity_matrix'])
    acceleration=np.array([.03,-.02,.04,.001,-.002,.003])
    np.testing.assert_allclose(np.asarray(plant.step(x,acceleration)).ravel(),
        predictor(x[None],acceleration[None],c)[0],rtol=1e-11,atol=1e-11)
    initial_speed=origin._actuator.current().copy();initial_clock=origin._actuator.elapsed_time
    exact=origin.forecast(x,np.repeat(controls,2,axis=0),predictor)
    assert exact['complete'],exact['failure']
    symbolic=plant.forecast(origin,x,controls)
    # Continuous symbolic PWM omits float32 command/allocation quantization.
    # 5 microunits in state and .0005 rotor-speed units are numeric parity,
    # not relaxed physical feasibility margins or a bitwise-equality promise.
    np.testing.assert_allclose(symbolic['predictions'],exact['predictions'],rtol=1e-7,atol=5e-6)
    np.testing.assert_allclose(symbolic['rotor_speed'],exact['rotor_speed'],rtol=1e-7,atol=5e-4)
    assert symbolic['predictions'].shape==(80,11)
    np.testing.assert_array_equal(origin._actuator.current(),initial_speed)
    assert origin._actuator.elapsed_time==initial_clock and live.physics_index==12


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_changing_learned_velocity_changes_numpy_and_real_symbolic_forecasts(name,record):
    pytest.importorskip('casadi',reason='real CasADi mutation counterexample requires server environment')
    from koopman.continuous_prediction_v76 import SymbolicPlant
    c,predictor,live,origin,x,controls=setup(name,record)
    modified=copy.deepcopy(record);modified['velocity_matrix'][-1][0]+=.0005
    modified=seal_record(modified);changed=prepare_learned(modified,c)
    original=origin.forecast(x,np.repeat(controls,2,axis=0),predictor)
    altered=origin.forecast(x,np.repeat(controls,2,axis=0),changed)
    assert original['complete'] and altered['complete']
    symbolic0=SymbolicPlant(predictor,name).forecast(origin,x,controls)['predictions']
    symbolic1=SymbolicPlant(changed,name).forecast(origin,x,controls)['predictions']
    delta=altered['predictions']-original['predictions'];symbolic_delta=symbolic1-symbolic0
    assert np.max(np.abs(delta))>.001
    assert np.max(np.abs(symbolic_delta))>.001
    np.testing.assert_allclose(symbolic_delta,delta,rtol=1e-5,atol=1e-5)
    assert live.physics_index==12
