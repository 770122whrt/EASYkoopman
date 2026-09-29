"""Fit-role-only refit and fail-closed full-observable diagnostics."""
import hashlib
import numpy as np
from koopman.sparse_world_edmd_v30 import lift,input_effect
from koopman.controlled_lift_v33 import full_step_input_effect,latent_step
from workflows.identify_sparse_world_v30 import from_record,_expected,validate_matrix
from workflows.identification_prediction_v32 import valid_predictions
from workflows.evaluate_projected_edmd_v24 import squared_errors


def fit_lift_matrix(episodes,parent):
    reference=from_record(parent);expected=_expected(parent['configurations'])
    if (len(episodes)!=len(expected) or {e.case['run_id'] for e in episodes}!=set(expected)
        or any(e.case!=expected.get(e.case['run_id']) or e.case['role']!='fit'
            or e.acceptance.get('training_eligible') is not True or e.source_commit!=parent['fit_source']
            or e.trace_sha256!=parent['fit_episode_hashes'].get(e.case['run_id']) for e in episodes)):
        raise ValueError('controlled_lift_fit_identity')
    current=[];following=[];effects=[];old_effects=[];weights=[]
    for e in sorted(episodes,key=lambda e:list(expected).index(e.case['run_id'])):
        if e.states.shape!=(641,11) or e.acceleration.shape!=(640,6):raise ValueError('controlled_lift_fit_shape')
        current.append(lift(e.states[:-1],e.context,reference.family));following.append(lift(e.states[1:],e.context,reference.family))
        effects.append(full_step_input_effect(e.states[:-1],e.acceleration,e.context,reference))
        old_effects.append(input_effect(e.states[:-1],e.acceleration,e.context,reference.family,reference.angular_damping))
        weights.append(np.r_[np.full(256,1/3),np.ones(384)])
    x=np.concatenate(current);y=np.concatenate(following);effect=np.concatenate(effects);old_effect=np.concatenate(old_effects)
    w=np.concatenate(weights);wn=w/w.sum();mean=wn@x;scale=np.maximum(np.sqrt(wn@((x-mean)**2)),1e-6)
    design=(x-mean)/scale;target=(y-effect-x)/scale;bias=wn@target;ridge=1e-6
    gram=design.T@(wn[:,None]*design)
    coefficient=np.linalg.solve(gram+ridge*np.eye(x.shape[1]),design.T@(wn[:,None]*(target-bias)))
    increment=coefficient*scale[None,:]/scale[:,None];matrix=np.eye(x.shape[1])+increment
    matrix[-1,:]+=bias*scale-mean@increment;matrix[:,-1]=0.;matrix[-1,-1]=1.
    matrix[:,10:16]=reference.matrix[:,10:16]
    validate_matrix(matrix,reference.family,reference.damping,reference.quadratic,reference.angular_damping)
    rmse=lambda a:np.sqrt(wn@(a*a)).tolist()
    result={'schema':'controlled-lift-input-v33','parent_model_id':parent['model_id'],'family':reference.family,
        'configurations':parent['configurations'],'fit_source':parent['fit_source'],'fit_episode_hashes':parent['fit_episode_hashes'],
        'matrix':matrix.tolist(),'damping':reference.damping.tolist(),'quadratic':reference.quadratic.tolist(),
        'angular_damping':reference.angular_damping,'feature_names':parent['feature_names'],
        'input_map':'lift(reference_full_step(x,a))-lift(reference_full_step(x,0))',
        'audit':{'training_role':'fit','episodes':len(episodes),'rows':len(x),'new_velocity_parameter_fits':0,
            'fixed_mean_ridge':ridge,'scale_floor':1e-6,'startup_weight':1/3,
            'weighted_one_step_lift_rmse_old':rmse(y-x@reference.matrix-old_effect),
            'weighted_one_step_lift_rmse_changed_input_only':rmse(y-x@reference.matrix-effect),
            'weighted_one_step_lift_rmse_refit':rmse(y-x@matrix-effect),
            'old_spectral_radius':float(np.max(np.abs(np.linalg.eigvals(reference.matrix)))),
            'new_spectral_radius':float(np.max(np.abs(np.linalg.eigvals(matrix)))),
            'fit_arrays_sha256':hashlib.sha256(x.tobytes()+y.tobytes()+effect.tobytes()+w.tobytes()).hexdigest()},
        'independent_validation':False,'model_handoff':False,'constant_AB':False}
    return result,matrix


def full_rollout(states,acceleration,reference,context,matrix,input_mode,horizon,*,start_control=128):
    x=np.asarray(states,dtype=float);u=np.asarray(acceleration,dtype=float);steps=2*horizon
    origins=np.arange(2*start_control,len(u)-steps+1,2)
    if len(x)!=len(u)+1 or not len(origins):raise ValueError('controlled_lift_rollout_shape')
    prediction=x[origins].copy();z=lift(prediction,context,reference.family)
    alive=np.ones(len(origins),dtype=bool);failure=np.full(len(origins),-1,dtype=int)
    summed=np.zeros((len(origins),4));endpoint=np.zeros_like(summed);exceptions=[];closure_max=0.
    for tick in range(steps):
        ids=np.flatnonzero(alive)
        if not len(ids):break
        try:
            with np.errstate(over='ignore',invalid='ignore',divide='ignore'):
                following,new=latent_step(z[ids],prediction[ids],u[origins[ids]+tick],context,reference,matrix,input_mode)
            good=valid_predictions(new)
        except (ValueError,FloatingPointError,np.linalg.LinAlgError) as exc:
            exceptions.append({'tick':tick+1,'exception':f'{type(exc).__name__}:{exc}'})
            good=np.zeros(len(ids),dtype=bool)
        bad=ids[~good];alive[bad]=False;failure[bad]=tick+1;ids=ids[good]
        if len(ids):
            z[ids]=following[good];prediction[ids]=new[good]
            relift=lift(prediction[ids],context,reference.family)
            closure=np.sqrt(np.mean(((z[ids]-relift)/(1+np.abs(relift)))**2,axis=1))
            closure_max=max(closure_max,float(np.max(closure)))
            error=squared_errors(x[origins[ids]+tick+1],prediction[ids]);summed[ids]+=error;endpoint[ids]=error
    complete=bool(alive.all())
    return {'horizon_control_intervals':horizon,'start_control':start_control,'origins':len(origins),
        'failed_origins':int(np.sum(~alive)),'first_failure_physics_tick':failure.tolist(),'complete_aggregate':complete,
        'endpoint_rmse':np.sqrt(endpoint.mean(0)).tolist() if complete else None,
        'path_rmse':np.sqrt(summed.mean(0)/steps).tolist() if complete else None,
        'maximum_scaled_closure_distance_on_valid_prefixes':closure_max,'exceptions':exceptions,
        'feature_reprojection':False,'input_mode':input_mode}
