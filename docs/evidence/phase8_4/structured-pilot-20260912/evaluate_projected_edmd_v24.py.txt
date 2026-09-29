"""Bounded pilot recursive scoring. No intermediate truth enters prediction."""
import numpy as np
from koopman.projected_edmd_v24 import observable, known_pose_step, decode


def squared_errors(reference, prediction):
    a=np.asarray(reference,dtype=float);b=np.asarray(prediction,dtype=float)
    qa=a[:,1:5]/np.linalg.norm(a[:,1:5],axis=1,keepdims=True)
    qb=b[:,1:5]/np.linalg.norm(b[:,1:5],axis=1,keepdims=True)
    angle=2*np.arccos(np.clip(np.abs(np.sum(qa*qb,axis=1)),0,1))
    return np.column_stack(((a[:,0]-b[:,0])**2,angle**2,
                            np.mean((a[:,5:8]-b[:,5:8])**2,axis=1),
                            np.mean((a[:,8:11]-b[:,8:11])**2,axis=1)))


def rollout(states, inputs, operator, dictionary, context, mode, horizon):
    """All control-boundary origins; path metrics include every physics tick."""
    x=np.asarray(states,dtype=float);u=np.asarray(inputs,dtype=float)
    steps=2*horizon
    if mode not in ('projected','unprojected_lift','persistence') or len(x)!=len(u)+1 or steps>len(u):
        raise ValueError('rollout_contract_invalid')
    origins=np.arange(0,len(u)-steps+1,2);prediction=x[origins].copy()
    alive=np.ones(len(origins),dtype=bool);first_failure=np.full(len(origins),-1,dtype=int)
    summed=np.zeros((len(origins),4));endpoint=np.zeros_like(summed)
    if mode!='persistence':z=(observable(prediction,context,dictionary)-operator.mean)/operator.scale
    for tick in range(steps):
        ids=np.flatnonzero(alive)
        if not len(ids):break
        if mode!='persistence':
            with np.errstate(over='ignore',invalid='ignore',divide='ignore'):
                next_z=operator.advance_lift(z[ids],u[origins[ids]+tick])
                features=next_z*operator.scale+operator.mean
                if mode=='projected':next_x=known_pose_step(prediction[ids],features[:,7:13],1/120)
                else:next_x=decode(features)
            prediction[ids]=next_x
            good=(np.isfinite(next_x).all(axis=1)&(np.abs(next_x[:,0])<=100)
                  &np.all(np.abs(next_x[:,5:])<=100,axis=1)
                  &(np.abs(np.linalg.norm(next_x[:,1:5],axis=1)-1)<=1e-3))
            bad=ids[~good];alive[bad]=False;first_failure[bad]=tick+1
            ids=ids[good]
            if mode=='projected':z[ids]=(observable(prediction[ids],context,dictionary)-operator.mean)/operator.scale
            else:z[ids]=next_z[good]
        if len(ids):
            error=squared_errors(x[origins[ids]+tick+1],prediction[ids]);summed[ids]+=error;endpoint[ids]=error
    complete=bool(alive.all())
    return {'horizon_control_intervals':horizon,'origins':len(origins),'origin_control_indices':(origins//2).tolist(),
            'failed_origins':int(np.sum(~alive)),'first_failure_physics_tick':first_failure.tolist(),
            'endpoint_rmse':np.sqrt(endpoint.mean(0)).tolist() if complete else None,
            'path_rmse':np.sqrt(summed.mean(0)/steps).tolist() if complete else None,
            'per_origin_endpoint_squared_error':endpoint.tolist() if complete else None,
            'per_origin_path_mean_squared_error':(summed/steps).tolist() if complete else None,
            'final_predictions':prediction.tolist() if complete else None,
            'complete_aggregate':complete}
