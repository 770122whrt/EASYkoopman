"""Recorded near-rest startup regression; requires frozen assets and real trace."""
import gzip,json,os
from pathlib import Path
import numpy as np
import pytest


def test_recorded_startup_converges_without_tautological_barriers():
    pytest.importorskip('casadi')
    path=os.environ.get('V76_STARTUP_TRACE');root=os.environ.get('V76_ASSET_ROOT')
    if not path or not root:pytest.skip('requires archived v76 server startup and frozen assets')
    from workflows.runtime_assets_v56 import AssetLocation,load_assets,read
    from workflows.identify_sparse_world_v30 import from_record
    from koopman.prepared_projected_v40 import prepare_projected
    from koopman.command_state_v39 import CausalCommandState
    from koopman.continuous_mpc_v76 import ContinuousMPC
    d=json.loads(gzip.decompress(Path(path).read_bytes()))
    assets=load_assets(AssetLocation(root,'.','assets/v38/inputs','5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    c=assets.context('base');live=CausalCommandState('base',c,episode_id='startup-regression',zero_rotor_reset_verified=True)
    for i,row in enumerate(d['substeps']):
        live.record_issued(row['command']['telemetry']['virtual_control_4'][0],physics_index=i,episode_id='startup-regression')
    assert live.physics_index==4
    origin=live.snapshot(configuration='base',context=c,origin_control=2,episode_id='startup-regression')
    solver=ContinuousMPC(assets.domains['base'],prepare_projected(from_record(read(assets.model_path)),c),solve_seconds=30.)
    result=solver.solve(origin=origin,initial_state=d['substeps'][-1]['state_after_physics_11'][0],
        previous=d['substeps'][-1]['command']['telemetry']['virtual_control_4'][0],
        baseline=np.tile(d['feedback_audit'][-1]['result']['command'],(10,1)),reference=d['case']['reference'])
    assert result['solver']['success'], result['solver']
    assert result['status']=='optimized' and result['exact_feasible']
    assert result['cost']<result['baseline_cost']
    assert live.physics_index==4
