"""Reuse allocation, never actuator state or a different command/context."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import time

import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.command_batch_v42 import forecast_batch as reference
from koopman.prepared_allocation_v42 import PreparedDirectAllocation
from test_command_batch_v41 import setup, same


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
def test_prepared_commands_preserve_source_allocation_at_rails_and_deadzone(name):
    from koopman.prepared_commands_v45 import PreparedCommands
    from workflows.control_seam_v23 import ControlKernel
    _, origin, _, _ = setup(name, 0)
    rng = np.random.default_rng(450)
    drive = rng.uniform(-.95, .95, (2, 20, 4))
    for index, value in enumerate([-.95, .95, 0., -.02, .02,
            np.nextafter(np.float32(.02), np.float32(0)),
            np.nextafter(np.float32(.02), np.float32(1))]):
        drive[0, index] = [0., 0., 0., value]
    prepared = PreparedCommands(origin, drive); kernel = ControlKernel(name)
    for i in range(2):
        for j in range(20):
            actual = kernel.command(drive[i,j].astype(np.float32), pre_tam=True)
            for field in ('pwm', 'pwm_raw', 'virtual_control'):
                np.testing.assert_allclose(getattr(prepared, field)[i,j], actual[field], rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(prepared.requested_commands, drive)


@pytest.mark.parametrize('name', SUPPORTED_EMBODIMENTS)
@pytest.mark.parametrize('origin,horizon', [(0, 20), (128, 128)])
def test_forecast_keeps_every_field_and_live_history(name, origin, horizon):
    from koopman.prepared_commands_v45 import PreparedCommands
    from koopman.command_batch_v45 import forecast_prepared
    live, saved, x, predict = setup(name, origin)
    drive = np.random.default_rng(451).uniform(-.03, .03, (3, horizon, 4)); drive[:,:,3] += .12
    prepared = PreparedCommands(saved, drive); before = drive.copy()
    expected = reference(saved, x, drive, predict)
    actual = forecast_prepared(saved, x, prepared, predict)
    for a,b in zip(actual, expected): same(a,b)
    np.testing.assert_array_equal(drive,before)
    assert live.physics_index == 2*origin


def test_only_unique_float32_commands_allocated_once_and_no_future_allocation(monkeypatch):
    from koopman.prepared_commands_v45 import PreparedCommands
    from koopman.command_batch_v45 import forecast_prepared
    _, saved, x, predict = setup('uuv6_angled')
    drive=np.zeros((3,20,4)); drive[:,:,3]=np.array([.12,.13,.14])[:,None]
    expected=reference(saved,x,drive,predict)
    calls=[]; original=PreparedDirectAllocation.command
    def counted(self,*a,**kw): calls.append(1); return original(self,*a,**kw)
    monkeypatch.setattr(PreparedDirectAllocation,'command',counted)
    prepared=PreparedCommands(saved,drive)
    assert len(calls)==prepared.unique_command_count==3
    # Source array mutation cannot change the prepared command identity.
    drive[:]=.9
    first=forecast_prepared(saved,x,prepared,predict)
    assert len(calls)==3
    for a,b in zip(first,expected): same(a,b)
    for field in ('requested_commands','pwm','pwm_raw','virtual_control','wrench_matrix'):
        with pytest.raises(ValueError): getattr(prepared,field).flat[0]=99
        with pytest.raises(ValueError): getattr(prepared,field).setflags(write=True)


@pytest.mark.parametrize('mode',['nan','raise'])
def test_failure_isolation_matches_reference(mode):
    from koopman.prepared_commands_v45 import PreparedCommands
    from koopman.command_batch_v45 import forecast_prepared
    _, saved, x, _=setup(origin=0)
    drive=np.zeros((3,4,4)); drive[1,:,3]=.4
    def predict(states,u,c):
        bad=np.abs(u[:,2])>.02
        if mode=='raise' and bad.any(): raise ValueError('branch_domain')
        y=states.copy(); y[:,5:]+=1e-5*u
        if mode=='nan': y[bad]=np.nan
        return y
    results=forecast_prepared(saved,x,PreparedCommands(saved,drive),predict)
    for a,b in zip(results,reference(saved,x,drive,predict)): same(a,b)
    assert [r['complete'] for r in results]==[True,False,True]


def test_reordered_subset_parallel_calls_and_output_mutation_do_not_leak():
    from koopman.prepared_commands_v45 import PreparedCommands
    from koopman.command_batch_v45 import forecast_prepared
    _, saved, x, predict=setup('uuv4_angled')
    drive=np.random.default_rng(452).uniform(-.05,.05,(3,4,4))
    prepared=PreparedCommands(saved,drive); expected=reference(saved,x,drive,predict)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(forecast_prepared,saved,x,prepared,predict)
        b=pool.submit(forecast_prepared,saved,x,prepared,predict,indices=[2,0])
        first,second=a.result(),b.result()
    for a,b in zip(first,expected): same(a,b)
    for i,j in enumerate([2,0]): same(second[i],expected[j])
    first[0]['predictions'][:]=99
    first[0]['origin_rotor_speed'][:]=99
    for a,b in zip(forecast_prepared(saved,x,prepared,predict),expected): same(a,b)
    assert not np.any(saved._actuator.current()==99)


@pytest.mark.parametrize('shape',[(0,2,4),(65,2,4),(1,0,4),(1,129,4),(2,4),(1,2,5)])
def test_cache_work_and_storage_are_bounded(shape):
    from koopman.prepared_commands_v45 import PreparedCommands
    _,saved,_,_=setup()
    with pytest.raises(ValueError): PreparedCommands(saved,np.zeros(shape))


@pytest.mark.parametrize('value',[np.nan,np.inf,.951])
def test_invalid_commands_never_create_a_plan(value):
    from koopman.prepared_commands_v45 import PreparedCommands
    _,saved,_,_=setup(); drive=np.zeros((1,1,4));drive[0,0,3]=value
    with pytest.raises(ValueError): PreparedCommands(saved,drive)


def test_configuration_context_and_index_bindings_are_checked():
    from koopman.prepared_commands_v45 import PreparedCommands
    from koopman.command_batch_v45 import forecast_prepared
    live,saved,x,predict=setup(); drive=np.zeros((2,2,4));prepared=PreparedCommands(saved,drive)
    with pytest.raises(ValueError): PreparedCommands(live,drive)
    with pytest.raises(ValueError): PreparedCommands(saved,drive,allocator=PreparedDirectAllocation('uuv6'))
    _,other,_,_=setup('heavy_moderate')
    with pytest.raises(ValueError): forecast_prepared(other,x,prepared,predict)
    changed=deepcopy(saved)
    object.__setattr__(changed,'_context',replace(changed._context,gravity=changed._context.gravity+.01))
    with pytest.raises(ValueError): forecast_prepared(changed,x,prepared,predict)
    for indices in ([],[2],[-1],[True],[.5]):
        with pytest.raises(ValueError): forecast_prepared(saved,x,prepared,predict,indices=indices)


def test_high_resolution_deadlines_include_preparation_and_prediction(monkeypatch):
    from koopman.prepared_commands_v45 import PreparedCommands
    from koopman.command_batch_v45 import forecast_prepared
    live,saved,x,predict=setup(); drive=np.zeros((1,2,4))
    with pytest.raises(TimeoutError): PreparedCommands(saved,drive,deadline=time.perf_counter()-1)
    prepared=PreparedCommands(saved,drive)
    monkeypatch.setattr(time,'monotonic',lambda:12345.)
    def slow(x,u,c): time.sleep(.03); return x.copy()
    with pytest.raises(TimeoutError): forecast_prepared(saved,x,prepared,slow,deadline=time.perf_counter()+.01)
    for invalid in (True,np.nan,np.inf):
        with pytest.raises(ValueError): PreparedCommands(saved,drive,deadline=invalid)
        with pytest.raises(ValueError): forecast_prepared(saved,x,prepared,predict,deadline=invalid)
    assert live.physics_index==6
