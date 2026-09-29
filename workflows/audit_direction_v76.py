"""Inspect recovery direction through exact actuator/wrench/state dynamics."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
from workflows.runtime_assets_v56 import AssetLocation,load_assets,read
from workflows.identify_sparse_world_v30 import from_record
from koopman.prepared_projected_v40 import prepare_projected
from koopman.command_state_v39 import CausalCommandState


def main():
    p=argparse.ArgumentParser();p.add_argument('--assets',required=True)
    p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assets=load_assets(AssetLocation(str(Path(a.assets).resolve()),'.','assets/v38/inputs',
        '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    model=from_record(read(assets.model_path));rows=[]
    for path in sorted(a.results.glob('*failure-projected_koopman-prefix*.json')):
        r=read(path);raw=Path(r['input']['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==r['input']['sha256']
        d=json.loads(gzip.decompress(raw));cfg=d['case']['configuration'];c=assets.context(cfg)
        index=r['physics_index'];prefix=r['committed_macro_steps']
        live=CausalCommandState(cfg,c,episode_id='direction',zero_rotor_reset_verified=True)
        for i in range(index):
            live.record_issued(d['substeps'][i]['command']['telemetry']['virtual_control_4'][0],physics_index=i,episode_id='direction')
        origin=live.snapshot(configuration=cfg,context=c,origin_control=index//2,episode_id='direction')
        initial=np.asarray(d['substeps'][index]['before']['state_11'][0])
        result=origin.forecast(initial,np.repeat(r['commands'],2,axis=0),prepare_projected(model,c))
        # Cross-platform float32 allocation can differ; this descriptive replay
        # does not replace the server's strict independent admission check.
        replay_error=float(np.max(np.abs(result['predictions']-np.asarray(r['predictions']))))
        np.testing.assert_allclose(result['predictions'],r['predictions'],rtol=0,atol=3e-6)
        states=np.vstack([initial,result['predictions']]);omega=states[:,9]
        first_free=prefix*4
        delta=np.diff(omega)*120
        braking=np.flatnonzero((omega[:-1]>0)&(delta<0)&(np.arange(len(delta))>=first_free))
        q=states[:,1:5];q=q/np.linalg.norm(q,axis=1,keepdims=True)
        pitch=np.arcsin(np.clip(2*(q[:,0]*q[:,2]-q[:,3]*q[:,1]),-1,1))
        rows.append(dict(trace=r['trace'],prefix_macro_steps=prefix,first_free_physics_offset=first_free,
            initial_pitch_rad=float(pitch[0]),terminal_predicted_pitch_rad=float(pitch[-1]),
            initial_omega_y_rad_s=float(omega[0]),terminal_predicted_omega_y_rad_s=float(omega[-1]),
            first_free_command=r['commands'][prefix],
            first_free_thruster_angular_acceleration_y=float(result['acceleration'][first_free,4]),
            first_free_net_angular_acceleration_y=float(delta[first_free]),
            first_braking_physics_offset=int(braking[0]) if len(braking) else None,
            maximum_predicted_omega_y=float(max(omega)),exact_state_support_rejection=assets.domains[cfg].check_states(result['predictions']),
            constraint_violation=r['constraint_violation'],cross_platform_replay_max_abs=replay_error))
    a.output.write_text(json.dumps(dict(evidence='offline_counterfactual_not_new_physics',rows=rows),indent=2,allow_nan=False))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
