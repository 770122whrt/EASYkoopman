"""Descriptive matched-episode metrics and issued-first-command prediction audit."""
import argparse,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=[];comparisons=[]
    for cfg in ('base','uuv4','long_body','uuv6'):
        arms={}
        for kind in ('feedback','projected_koopman','nominal_physics'):
            suffix='r1' if cfg=='base' and kind=='feedback' else 'r3'
            directory=a.root/(cfg+'-pitch-'+kind+'-'+suffix)
            if not (directory/'trace.json.gz').exists():
                rows.append(dict(configuration=cfg,controller=kind,status='not_returned'));continue
            raw=(directory/'trace.json.gz').read_bytes();d=json.loads(gzip.decompress(raw))
            accepted=(directory/'acceptance.json').exists()
            if accepted:
                acceptance=json.loads((directory/'acceptance.json').read_text())
                assert acceptance['status']=='accepted_bounded_simulation_time_closed_loop'
                assert acceptance['trace_sha256']==hashlib.sha256(raw).hexdigest()
            row=dict(configuration=cfg,controller=kind,status='accepted' if accepted else d['status'],
                trace_sha256=hashlib.sha256(raw).hexdigest(),physics_steps=d['physical_steps'],
                exception=d.get('exception'),metrics=d.get('metrics'),wall_seconds=d['wall_seconds'])
            commands=np.asarray([x['command']['telemetry']['virtual_control_4'][0] for x in d['substeps'][::4]])
            if len(commands):
                row['command_variation_l1']=float(np.sum(np.abs(np.diff(commands,axis=0))))
                row['command_rms']=float(np.sqrt(np.mean(commands**2)))
            if not accepted and d.get('solve_audit'):row['terminal_solve']=d['solve_audit'][-1]
            if accepted:
                arms[kind]=d['metrics'];audits=d['solve_audit']
                row['selection_counts']=dict(Counter(x['status'] for x in audits))
                row['solver_counts']=dict(Counter(x['solver']['return_status'] for x in audits))
                if audits:
                    errors=[];angle=[]
                    for result in audits:
                        j=result['physics_index'];expected=np.asarray(result['predictions'])[:4]
                        actual=np.asarray([x['state_after_physics_11'][0] for x in d['substeps'][j:j+4]])
                        commanded=np.asarray([x['command']['telemetry']['virtual_control_4'][0] for x in d['substeps'][j:j+4]])
                        np.testing.assert_allclose(commanded,np.tile(result['commands'][0],(4,1)),atol=1e-7,rtol=0)
                        errors.append(np.abs(expected-actual))
                        p_=expected[:,1:5]/np.linalg.norm(expected[:,1:5],axis=1,keepdims=True)
                        q_=actual[:,1:5]/np.linalg.norm(actual[:,1:5],axis=1,keepdims=True)
                        angle.extend(2*np.arccos(np.clip(np.abs(np.sum(p_*q_,axis=1)),0,1)))
                    row['issued_one_interval_prediction_max_abs_11']=np.max(np.vstack(errors),axis=0).tolist()
                    row['issued_one_interval_attitude_max_rad']=float(max(angle))
                    times=[x['elapsed_seconds'] for x in audits]
                    row['solve_wall_seconds']=dict(median=float(np.median(times)),maximum=max(times))
            rows.append(row)
        if len(arms)==3:
            f,k,p_=(arms[x] for x in ('feedback','projected_koopman','nominal_physics'))
            def gain(old,new):return 100*(old-new)/old
            comparisons.append(dict(configuration=cfg,
                koopman_vs_feedback_score_gain_percent=gain(f['normalized_tracking_score'],k['normalized_tracking_score']),
                physical_vs_feedback_score_gain_percent=gain(f['normalized_tracking_score'],p_['normalized_tracking_score']),
                koopman_vs_physical_score_gain_percent=gain(p_['normalized_tracking_score'],k['normalized_tracking_score']),
                koopman_vs_feedback_attitude_rmse_gain_percent=gain(f['attitude_rmse_rad'],k['attitude_rmse_rad']),
                koopman_vs_feedback_depth_rmse_gain_percent=gain(f['depth_rmse_m'],k['depth_rmse_m'])))
    result=dict(scope='single_episode_2s_development_not_statistical_validation',rows=rows,comparisons=comparisons,
        gain_sign='positive_is_lower_error',prediction_scope='only_first_four_physics_steps_with_identical_actually_issued_command',
        independent_representation_gain_claim=False)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps(comparisons,indent=2))


if __name__=='__main__':main()
