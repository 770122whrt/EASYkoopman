"""Combine actual accepted 2 s trajectories; do not invent scores for failures."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

CONFIGURATIONS=('base','uuv4','long_body','uuv6')
MODELS=('projected_koopman','nominal_physics')
SOURCE='815b212077ef792d06e8568226edf90a2a603b9379195c17f3a90b15bbc3e090'
MODEL='9704fbb8cc0a40ebc74f3f4d2727cba0f52a0b4221ec6e71d4f5526d98a088f4'
WALL_ENTRY='0946a8ab1b6c5be41d792b77c33d27f30f9f91ae042886a4c4a92a1ce07ad2b1'
WEIGHTS=dict(depth=4.,attitude=1.,vertical_speed=.1,angular_speed=.1,effort=.01,slew=.05,terminal=1.)


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def up(q):
    w,x,y,z=np.moveaxis(q,-1,0)
    return np.stack((2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)),axis=-1)


def physical_metrics(raw):
    x=np.asarray([r['state_after_physics_11'][0] for r in raw['substeps']])
    assert x.shape==(240,11)
    ref=np.asarray(raw['case']['reference']);ref[1:]/=np.linalg.norm(ref[1:])
    q=x[:,1:5]/np.linalg.norm(x[:,1:5],axis=1,keepdims=True)
    if raw['case']['configuration'].startswith('uuv4'):
        aa,bb=up(q),up(ref[1:]);angle=np.arctan2(np.linalg.norm(np.cross(aa,bb),axis=1),np.clip(aa@bb,-1,1))
    else:angle=2*np.arccos(np.clip(np.abs(q@ref[1:]),0,1))
    depth=x[:,0]-ref[0]
    commands=np.asarray([r['command']['telemetry']['virtual_control_4'][0] for r in raw['substeps']])
    pwm=np.asarray([r['command']['telemetry']['motor_pwm_n'][0] for r in raw['substeps']])
    mask=np.array([1.,1.,0. if raw['case']['configuration'].startswith('uuv4') else 1.,1.])
    tracking=4*depth**2+angle**2+.1*np.sum(up(q)*x[:,5:8],axis=1)**2+.1*np.sum((x[:,8:11]*mask[:3])**2,axis=1)
    effort=float(np.sum((commands*mask)**2)/120)
    slew=float(np.sum(np.diff(np.vstack([np.zeros(4),commands*mask]),axis=0)**2)/60)
    full_cost=float(np.sum(tracking)/120+tracking[-1]+.01*effort+.05*slew)
    # Cross-check a full actual trajectory, not a sum of overlapping forecasts.
    from koopman.control_objective_v44 import trajectory_cost,ObjectiveWeights
    expected=trajectory_cost(x,commands[::2],np.zeros(4),ref,mask,ObjectiveWeights(depth=4.))
    assert abs(full_cost-expected)<1e-12
    return dict(depth_rmse_m=float(np.sqrt(np.mean(depth**2))),attitude_rmse_rad=float(np.sqrt(np.mean(angle**2))),
        normalized_tracking_score=float(np.mean(depth**2/.02**2+angle**2/.04**2)),
        command_squared_integral=effort,pwm_squared_integral=float(np.sum(pwm**2)/120),
        full_task_cost_depth4=full_cost,
        full_task_cost_components=dict(tracking_integral=float(np.sum(tracking)/120),
            terminal=float(tracking[-1]),effort=.01*effort,slew=.05*slew))


def executed_prediction_errors(raw):
    """Only the first executed 30 Hz interval; later controls are reoptimized."""
    predicted=[];observed=[]
    for audit in raw.get('solve_audit',[]):
        start=audit['physics_index'];states=audit.get('predictions')
        if states is None or start+4>len(raw['substeps']):continue
        actual=raw['substeps'][start:start+4]
        commands=np.asarray([s['command']['telemetry']['virtual_control_4'][0] for s in actual])
        assert np.allclose(commands,np.asarray(audit['commands'])[0],atol=1e-7,rtol=0)
        predicted.extend(states[:4]);observed.extend(s['state_after_physics_11'][0] for s in actual)
    if not predicted:return None
    p,o=np.asarray(predicted),np.asarray(observed)
    pq=p[:,1:5]/np.linalg.norm(p[:,1:5],axis=1,keepdims=True)
    oq=o[:,1:5]/np.linalg.norm(o[:,1:5],axis=1,keepdims=True)
    angle=2*np.arccos(np.clip(np.abs(np.sum(pq*oq,axis=1)),0,1))
    return dict(compared_substeps=len(p),horizon_seconds=1/30,
        depth_rmse_m=float(np.sqrt(np.mean((p[:,0]-o[:,0])**2))),
        full_attitude_rmse_rad=float(np.sqrt(np.mean(angle**2))),
        body_velocity_vector_rmse=float(np.sqrt(np.mean(np.sum((p[:,5:8]-o[:,5:8])**2,axis=1)))),
        angular_velocity_vector_rmse=float(np.sqrt(np.mean(np.sum((p[:,8:]-o[:,8:])**2,axis=1)))))


def describe(path,cfg,kind,origin,profile=None):
    p=Path(path);row=dict(configuration=cfg,controller=kind,origin=origin,path=str(p),profile=profile,
        accepted=False,status='not_run',reason=None,physics_steps=0)
    if not (p/'summary.json').exists():return row
    s=read(p/'summary.json');case=s['case']
    assert case['configuration']==cfg and case['controller']==kind
    assert case['controls']==60 and case['seed']==19760 and case['task']=='pitch_0.04_rad'
    assert np.allclose(case['reference'],[5.5,.9998000066665778,0,.01999866669333308,0],atol=1e-14,rtol=0)
    assert s['model_fits']==0 and s['timing_mode']=='synchronous_nonrealtime'
    if 'model' not in s:
        assert not (p/'acceptance.json').exists()
        row.update(status='failed_before_model_initialization',reason=s.get('exception'),physics_steps=s['physical_steps'])
        return row
    assert s['model']['frozen_parameter_source_sha256']==MODEL
    if 'collector_entrypoint_sha256' in s:
        assert s['collector_entrypoint_sha256']==WALL_ENTRY and s['collector_wall_limit_seconds']==1350
        row.update(collector_entrypoint_sha256=WALL_ENTRY,collector_wall_limit_seconds=1350)
    if profile is not None:
        assert case['profile']==profile and s['source_manifest_sha256']==SOURCE
        assert s['model']['horizon_macro_steps']==(20 if profile=='depth4_h20' else 10)
        assert s['model']['weights']==(WEIGHTS if profile=='depth4_h20' else {**WEIGHTS,'depth':1.})
    row.update(status='failed_or_unaccepted',reason=s.get('exception'),physics_steps=s['physical_steps'],
        source_manifest_sha256=s['source_manifest_sha256'],context=s.get('context_audit',{}).get('observed_context_key'))
    trace=p/'trace.json.gz'
    if not trace.exists():return row
    raw=json.loads(gzip.decompress(trace.read_bytes()));row['trace_sha256']=sha(trace)
    audits=raw.get('solve_audit',[])
    row['decision_statuses']=dict(Counter(a['status'] for a in audits))
    row['nlp_statuses']=dict(Counter(a.get('solver',{}).get('return_status','none') for a in audits))
    values=[a['elapsed_seconds'] for a in audits if a.get('elapsed_seconds') is not None]
    if values:row['solve_seconds']=dict(median=float(np.median(values)),p95=float(np.percentile(values,95)),maximum=max(values))
    cycles=[r['whole_cycle_wall_ms'] for r in raw['intervals'] if r.get('whole_cycle_wall_ms') is not None]
    if cycles:row['whole_cycle_ms']=dict(median=float(np.median(cycles)),maximum=max(cycles))
    if not (p/'acceptance.json').exists():
        row['reason']=row['reason'] or 'independent_acceptance_missing'
        return row
    a=read(p/'acceptance.json');assert a['trace_sha256']==row['trace_sha256'] and a['physics_steps']==240
    assert a['status']=='accepted_bounded_simulation_time_closed_loop'
    if origin=='new_v78':
        for suffix in ('.exit.json','-validation.exit.json'):
            native=read(p.parent/(p.name+suffix))
            assert native['native_exit']==0 and native['group_stopped']
    assert s['physical_steps']==240 and s['completed_controls']==60 and not s['cleanup_errors']
    assert s['cleanup_completed']['environment'] and s['cleanup_completed']['simulation_app']
    if kind!='feedback':
        assert s['cleanup_completed']['worker']
        assert s['worker_closed']=={'process_stopped':True,'io_threads_stopped':True}
    calc=physical_metrics(raw)
    for key in ('depth_rmse_m','attitude_rmse_rad','normalized_tracking_score'):
        assert abs(calc[key]-s['metrics'][key])<1e-10,(p,key)
    row.update(accepted=True,status='accepted',metrics=calc,
        executed_prediction_errors=executed_prediction_errors(raw))
    return row


def summarize(new,old,feedback):
    rows=[];repair=[];prior_attempts=[];retry_prefix=None
    for cfg in CONFIGURATIONS:
        base=describe(feedback/(cfg+'-pitch-feedback-'+('r1' if cfg=='base' else 'r3')),cfg,'feedback','reused_v76')
        assert base['accepted'];base['improvement_percent']=0.;rows.append(base)
        for kind in MODELS:
            if cfg=='uuv4':p=old/f'{cfg}-pitch-{kind}-depth4_h20-r4';origin='reused_v77'
            else:p=new/f'{cfg}-pitch-{kind}-depth4_h20-v78r1';origin='new_v78'
            if cfg=='uuv6' and kind=='projected_koopman' and (new/f'{cfg}-pitch-{kind}-depth4_h20-v78r2').exists():
                previous_attempt=describe(p,cfg,kind,origin,'depth4_h20')
                assert not previous_attempt['accepted'] and previous_attempt['reason']=='TimeoutError:case_wall_budget'
                prior_attempts.append(previous_attempt)
                p=new/f'{cfg}-pitch-{kind}-depth4_h20-v78r2'
            row=describe(p,cfg,kind,origin,'depth4_h20')
            if cfg=='uuv6' and kind=='projected_koopman' and prior_attempts and row['accepted']:
                before=json.loads(gzip.decompress(Path(prior_attempts[-1]['path']).joinpath('trace.json.gz').read_bytes()))
                after=json.loads(gzip.decompress(p.joinpath('trace.json.gz').read_bytes()))
                n=len(before['substeps'])
                def array(raw,key):
                    if key=='state':return np.asarray([r['state_after_physics_11'][0] for r in raw['substeps'][:n]])
                    return np.asarray([r['command']['telemetry']['virtual_control_4'][0] for r in raw['substeps'][:n]])
                retry_prefix=dict(compared_physics_steps=n,
                    maximum_state_absolute_difference=float(np.max(np.abs(array(before,'state')-array(after,'state')))),
                    maximum_command_absolute_difference=float(np.max(np.abs(array(before,'command')-array(after,'command')))))
                retry_prefix['within_1e_6']=max(retry_prefix['maximum_state_absolute_difference'],retry_prefix['maximum_command_absolute_difference'])<=1e-6
            previous=describe(old/f'{cfg}-pitch-{kind}-repair-r4',cfg,kind,'reused_v77','repair')
            assert previous['accepted']
            for r in (row,previous):
                if r['accepted']:
                    assert r['context']==base['context']
                    r['improvement_percent']=100*(1-r['metrics']['normalized_tracking_score']/base['metrics']['normalized_tracking_score'])
                    r['command_intensity_ratio_to_feedback']=r['metrics']['command_squared_integral']/base['metrics']['command_squared_integral']
                    r['pwm_intensity_ratio_to_feedback']=r['metrics']['pwm_squared_integral']/base['metrics']['pwm_squared_integral']
                    r['full_task_cost_depth4_improvement_percent']=100*(1-r['metrics']['full_task_cost_depth4']/base['metrics']['full_task_cost_depth4'])
            if row['accepted']:
                row['improvement_over_repair_percent']=100*(1-row['metrics']['normalized_tracking_score']/previous['metrics']['normalized_tracking_score'])
            rows.append(row);repair.append(previous)
    exits=[read(p) for p in new.glob('*.exit.json')]
    starts=sum(any(c in r['command'] for c in ('workflows.collect_reliable_v77','workflows.collect_reliable_v78')) for r in exits)
    seconds=sum(r['seconds'] for r in exits)
    assert starts<=7 and seconds<=7200
    return dict(schema='common-profile-v78-report/1',profile='depth4_h20',task_seconds=2,seed=19760,
        new_physics_starts=starts,native_wall_seconds=seconds,
        main_rows=rows,old_repair_rows=repair,prior_attempts=prior_attempts,retry_prefix_agreement=retry_prefix,
        accepted_main_rows=sum(r['accepted'] for r in rows),
        limitations=['known configurations and one short development task','uuv4 and feedback explicitly reused',
            'simulation paused while solving; not real-time','projected readout equals identified-parameter physics',
            'command/PWM intensity proxies are not measured energy','no confidence interval or unseen-configuration claim'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--new',type=Path,required=True);p.add_argument('--old',type=Path,required=True)
    p.add_argument('--feedback',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=summarize(a.new,a.old,a.feedback)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    fields=['configuration','controller','origin','status','physics_steps','depth_rmse_m','attitude_rmse_rad',
        'normalized_tracking_score','improvement_percent','full_task_cost_depth4',
        'full_task_cost_depth4_improvement_percent','solve_median_seconds','whole_cycle_median_ms','reason']
    with a.output.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
        for row in result['main_rows']:
            v={k:row.get(k) for k in fields};v.update({k:row.get('metrics',{}).get(k) for k in fields if k in ('depth_rmse_m','attitude_rmse_rad','normalized_tracking_score','full_task_cost_depth4')})
            v['solve_median_seconds']=row.get('solve_seconds',{}).get('median');v['whole_cycle_median_ms']=row.get('whole_cycle_ms',{}).get('median')
            writer.writerow(v)
    print(json.dumps({k:v for k,v in result.items() if k not in ('main_rows','old_repair_rows')}))
    for r in result['main_rows']:print(r['configuration'],r['controller'],r['status'],r.get('improvement_percent'),r['reason'])


if __name__=='__main__':main()
