"""Post-hoc online forecast errors only while actual inputs match that plan."""
import numpy as np
from koopman.control_objective_v44 import control_mask
from koopman.projected_edmd_v24 import rotation


def matching_predictions(data,payload):
    origin=payload['metadata']['history_physics_index']
    commands=np.asarray(payload['commands'],dtype=np.float32)
    predicted=np.asarray(payload['predictions'],dtype=float)
    if (type(origin) is not int or origin<0 or commands.ndim!=2 or commands.shape[1]!=4
            or predicted.shape!=(2*len(commands),11)):
        raise ValueError('forecast_diagnostic_shape')
    actual=[]
    for j in range(min(len(predicted),len(data['substeps'])-origin)):
        row=data['substeps'][origin+j]
        issued=np.asarray(row['command']['telemetry']['virtual_control_4'][0],dtype=np.float32)
        if not np.array_equal(issued,commands[j//2]):break
        actual.append(row['state_after_physics_11'][0])
    return predicted[:len(actual)],np.asarray(actual,dtype=float)


def diagnose(data):
    records=[];mask=control_mask(data['case']['configuration'])
    for event in data['arbitration_audit']:
        if event['method']!='ingest' or event['result'].get('status')!='staged':continue
        payload=event['event'].get('payload',{})
        if payload.get('status') not in ('selected','baseline'):continue
        predicted,actual=matching_predictions(data,payload)
        if not len(actual):continue
        p=predicted[:,1:5];a=actual[:,1:5]
        p=p/np.linalg.norm(p,axis=1)[:,None];a=a/np.linalg.norm(a,axis=1)[:,None]
        if mask[2]:angle=2*np.arccos(np.clip(np.abs(np.sum(p*a,axis=1)),-1,1))
        else:
            up=rotation(p)[:,2,:];ua=rotation(a)[:,2,:]
            angle=np.arctan2(np.linalg.norm(np.cross(up,ua),axis=1),np.clip(np.sum(up*ua,axis=1),-1,1))
        records.append(dict(origin_physics_index=payload['metadata']['history_physics_index'],matched_steps=len(actual),
            samples=[dict(horizon_physics_steps=k,depth_error_m=float(predicted[k-1,0]-actual[k-1,0]),
                attitude_error_rad=float(angle[k-1]),velocity_error_norm=float(np.linalg.norm(predicted[k-1,5:8]-actual[k-1,5:8])))
                for k in (4,8,16,24,32,40) if len(actual)>=k]))
    summary={}
    for k in (4,8,16,24,32,40):
        samples=[s for r in records for s in r['samples'] if s['horizon_physics_steps']==k]
        if samples:summary[str(k)]=dict(count=len(samples),seconds=k/120,
            depth_rmse_m=float(np.sqrt(np.mean([s['depth_error_m']**2 for s in samples]))),
            attitude_rmse_rad=float(np.sqrt(np.mean([s['attitude_error_rad']**2 for s in samples]))))
    return dict(case_id=data['case']['case_id'],online_forecast_records=len(records),summary=summary,records=records,
        refits=0,overlapping_predictions_not_independent_samples=True,
        claim='Descriptive prediction diagnostic on exactly matched actual commands; not independent benefit evidence')
