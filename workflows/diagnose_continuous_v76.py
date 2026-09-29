"""One recorded startup, isolated solver-numerics ablations; no physics/fitting."""
import argparse,gzip,json,time
from pathlib import Path
import numpy as np
import casadi as ca
from workflows.runtime_assets_v56 import AssetLocation,load_assets,read
from workflows.identify_sparse_world_v30 import from_record
from koopman.prepared_projected_v40 import prepare_projected
from koopman.continuous_mpc_v76 import ContinuousMPC
from koopman.command_state_v39 import CausalCommandState
from workflows.continuous_replay_v76 import plain


def main():
    p=argparse.ArgumentParser();p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--assets',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(exist_ok=False)
    d=json.loads(gzip.decompress(a.trace.read_bytes()));cfg=d['case']['configuration']
    assets=load_assets(AssetLocation(a.assets,'.','assets/v38/inputs','5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    c=assets.context(cfg);predictor=prepare_projected(from_record(read(assets.model_path)),c)
    live=CausalCommandState(cfg,c,episode_id='diagnose',zero_rotor_reset_verified=True)
    for i,row in enumerate(d['substeps']):live.record_issued(row['command']['telemetry']['virtual_control_4'][0],physics_index=i,episode_id='diagnose')
    origin=live.snapshot(configuration=cfg,context=c,origin_control=len(d['substeps'])//2,episode_id='diagnose')
    x=np.asarray(d['substeps'][-1]['state_after_physics_11'][0]);previous=d['substeps'][-1]['command']['telemetry']['virtual_control_4'][0]
    base=np.tile(d['feedback_audit'][-1]['result']['command'],(10,1))
    variants=[('no_redundant_bounds',{})]
    original=ca.nlpsol
    for name,options in variants:
        def factory(n,kind,problem,settings):return original(n,kind,problem,dict(settings,**options))
        ca.nlpsol=factory
        try:solver=ContinuousMPC(assets.domains[cfg],predictor,horizon=10,solve_seconds=30.)
        finally:ca.nlpsol=original
        # Squared norms are inherently nonnegative, and normalized-quaternion
        # rotation components inherently lie in [-1,1]. Their active zero-
        # gradient barriers add no physical restriction and can hurt IPOPT.
        if name=='no_redundant_bounds':
            for k in range(40):
                solver._lower_g[15*k+12:15*k+14]=-np.inf
                solver._upper_g[15*k+14]=np.inf
                for j in (1,2,3):
                    if solver._lower_g[15*k+j]<=-1:solver._lower_g[15*k+j]=-np.inf
                    if solver._upper_g[15*k+j]>=1:solver._upper_g[15*k+j]=np.inf
        result=solver.solve(origin=origin,initial_state=x,baseline=base,previous=previous,reference=d['case']['reference'])
        stats=solver._solver.stats();result['numerical_diagnostics']=stats
        (a.output/(name+'.json')).write_text(json.dumps(plain(result),indent=2,allow_nan=False))
        print(json.dumps(plain(dict(variant=name,**{k:result.get(k) for k in ('status','reason','cost','baseline_cost','solver','elapsed_seconds')},
            terminal={k:v[-1] for k,v in stats.get('iterations',{}).items() if isinstance(v,list) and v}))),flush=True)


if __name__=='__main__':main()
