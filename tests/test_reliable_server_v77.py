"""Actual solver process replay on recorded failures; zero new physics."""
import gzip,json,os
from pathlib import Path
import numpy as np
import pytest
pytest.importorskip('casadi')


@pytest.fixture(scope='module')
def assets():
    from workflows.runtime_assets_v56 import AssetLocation,load_assets
    root=os.environ.get('V77_ASSETS')
    if not root:pytest.skip('recorded-server-assets test')
    return load_assets(AssetLocation(root,'.','assets/v38/inputs','5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')


@pytest.mark.parametrize('cfg,kind',[('long_body','projected_koopman'),('long_body','nominal_physics'),('uuv6','projected_koopman'),('uuv6','nominal_physics')])
def test_actual_worker_recovers_recorded_failure(assets,cfg,kind):
    from workflows.identify_sparse_world_v30 import from_record
    from workflows.runtime_assets_v56 import read
    from koopman.command_state_v39 import CausalCommandState
    from koopman.reliable_mpc_v77 import create_solver
    path=Path(os.environ['V77_TRACES'])/(cfg+'-pitch-'+kind+'-r3')/'trace.json.gz'
    d=json.loads(gzip.decompress(path.read_bytes()));c=assets.context(cfg)
    live=CausalCommandState(cfg,c,episode_id='v77-replay',zero_rotor_reset_verified=True)
    for i,r in enumerate(d['substeps']):live.record_issued(r['command']['telemetry']['virtual_control_4'][0],physics_index=i,episode_id='v77-replay')
    n=len(d['substeps']);origin=live.snapshot(configuration=cfg,context=c,origin_control=n//2,episode_id='v77-replay')
    solver=create_solver(assets.domains[cfg],from_record(read(assets.model_path)),c,kind)
    try:
        if cfg=='uuv6' and kind=='nominal_physics':
            solver._last=dict(origin=n//2-2,reference=np.array(d['case']['reference']),commands=np.array(d['solve_audit'][-2]['commands']))
        result=solver.solve(origin=origin,initial_state=d['substeps'][-1]['state_after_physics_11'][0],
            baseline=np.tile(d['feedback_audit'][-1]['result']['command'],(10,1)),
            previous=d['substeps'][-1]['command']['telemetry']['virtual_control_4'][0],reference=d['case']['reference'])
        assert result['exact_feasible'],result
        assert result['worker_pid']!=os.getpid()
        assert result['worker_threads']=={'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
        assert result['solver']['return_status']!='Maximum_CpuTime_Exceeded'
        if cfg=='uuv6' and kind=='nominal_physics':assert result['warm_start_used']
        assert live.physics_index==n
    finally:assert solver.close()=={'process_stopped':True,'io_threads_stopped':True}


@pytest.mark.parametrize('index',[160,192])
def test_actual_worker_escapes_recorded_zero_gradient_deadzone(assets,index):
    from workflows.identify_sparse_world_v30 import from_record
    from workflows.runtime_assets_v56 import read
    from koopman.command_state_v39 import CausalCommandState
    from koopman.reliable_mpc_v77 import create_solver
    source=os.environ.get('V77_RELIABLE_TRACE')
    if not source:pytest.skip('v77 deadzone trace not supplied')
    d=json.loads(gzip.decompress(Path(source).read_bytes()));c=assets.context('uuv4')
    live=CausalCommandState('uuv4',c,episode_id='deadzone-replay',zero_rotor_reset_verified=True)
    for i,row in enumerate(d['substeps'][:index]):
        live.record_issued(row['command']['telemetry']['virtual_control_4'][0],physics_index=i,episode_id='deadzone-replay')
    origin=live.snapshot(configuration='uuv4',context=c,origin_control=index//2,episode_id='deadzone-replay')
    feedback=next(x for x in d['feedback_audit'] if x['physics_index']==index)['result']
    solver=create_solver(assets.domains['uuv4'],from_record(read(assets.model_path)),c,'projected_koopman')
    try:
        answer=solver.solve(origin=origin,initial_state=d['substeps'][index-1]['state_after_physics_11'][0],
            baseline=np.tile(feedback['command'],(10,1)),reference=d['case']['reference'],
            previous=d['substeps'][index-1]['command']['telemetry']['virtual_control_4'][0],
            physical_target=feedback['static_command'])
        assert answer['exact_feasible'],answer
        assert answer['initialization_kind']=='physical_target_ramp'
        assert answer['solver']['return_status']=='Solve_Succeeded'
        assert live.physics_index==index
    finally:assert solver.close()=={'process_stopped':True,'io_threads_stopped':True}
