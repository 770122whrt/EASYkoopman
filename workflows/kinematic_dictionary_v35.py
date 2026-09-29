"""One fixed fit-role-only dictionary repair and the inherited numerical gate."""
import re,hashlib
import numpy as np
from koopman.kinematic_dictionary_v35 import lift,feature_names,KinematicModel
from koopman.sparse_world_edmd_v30 import lift as parent_lift
from koopman.controlled_lift_v33 import full_step_input_effect
from koopman.projected_edmd_v24 import _readonly
from workflows.identify_sparse_world_v30 import from_record as read_parent,_expected
from workflows.state_projection_v34 import fit_screen as previous_screen


def fit_readout(episodes,parent,parent_sha256):
    reference=read_parent(parent);expected=_expected(parent['configurations'])
    if (reference.family!='nonlinear' or not re.fullmatch('[0-9a-f]{64}',parent_sha256)
        or len(episodes)!=len(expected) or {e.case['run_id'] for e in episodes}!=set(expected)
        or any(e.case!=expected.get(e.case['run_id']) or e.case['role']!='fit'
            or e.acceptance.get('training_eligible') is not True or e.source_commit!=parent['fit_source']
            or e.trace_sha256!=parent['fit_episode_hashes'].get(e.case['run_id']) for e in episodes)):
        raise ValueError('kinematic_fit_identity')
    current=[];following=[];effects=[];weights=[]
    for e in sorted(episodes,key=lambda e:list(expected).index(e.case['run_id'])):
        if e.states.shape!=(641,11) or e.acceleration.shape!=(640,6):raise ValueError('kinematic_fit_shape')
        current.append(lift(e.states[:-1],e.context));following.append(parent_lift(e.states[1:],e.context,'nonlinear')[:,:10])
        effects.append(full_step_input_effect(e.states[:-1],e.acceleration,e.context,reference)[:,:10])
        weights.append(np.r_[np.full(256,1/3),np.ones(384)])
    x=np.concatenate(current);y=np.concatenate(following);effect=np.concatenate(effects);w=np.concatenate(weights);wn=w/w.sum()
    mean=wn@x;scale=np.maximum(np.sqrt(wn@((x-mean)**2)),1e-6)
    design=(x-mean)/scale;target=(y-effect-x[:,:10])/scale[:10];bias=wn@target
    gram=design.T@(wn[:,None]*design);ridge=1e-6
    coefficient=np.linalg.solve(gram+ridge*np.eye(62),design.T@(wn[:,None]*(target-bias)))
    increment=coefficient*scale[None,:10]/scale[:,None]
    K=np.vstack([reference.matrix[:,:16],np.zeros((9,16))]);K[:,:10]=np.eye(62)[:,:10]+increment
    K[52,:10]+=bias*scale[:10]-mean@increment
    result={k:parent[k] for k in ('family','configurations','fit_source','fit_episode_hashes','damping','quadratic','angular_damping')}
    result.update(schema='kinematic-dictionary-v35',parent_model_id=parent['model_id'],parent_sha256=parent_sha256,
        matrix=K.tolist(),feature_names=feature_names(),readout='z_R9_vworld_wbody_then_SO3_and_relift',
        audit={'training_role':'fit','episodes':len(episodes),'rows':len(x),'new_velocity_parameter_fits':0,
            'fixed_mean_ridge':ridge,'scale_floor':1e-6,'startup_weight':1/3,'learned_output_columns':list(range(10)),
            'weighted_pose_observable_rmse':np.sqrt(wn@((y-effect-x@K[:,:10])**2)).tolist(),
            'fit_arrays_sha256':hashlib.sha256(x.tobytes()+y.tobytes()+effect.tobytes()+w.tobytes()).hexdigest()},
        independent_validation=False,model_handoff=False,constant_AB=False)
    return result


def from_record(record,parent,parent_sha256):
    reference=read_parent(parent)
    if (record.get('schema')!='kinematic-dictionary-v35' or not re.fullmatch('[0-9a-f]{64}',parent_sha256)
        or record.get('parent_sha256')!=parent_sha256 or record.get('parent_model_id')!=parent.get('model_id')
        or any(record.get(k)!=parent.get(k) for k in ('family','configurations','fit_source','fit_episode_hashes','damping','quadratic','angular_damping'))
        or record.get('feature_names')!=feature_names() or record.get('family')!='nonlinear'
        or record.get('audit',{}).get('training_role')!='fit' or record.get('audit',{}).get('new_velocity_parameter_fits')!=0):
        raise ValueError('kinematic_parent_binding')
    K=np.asarray(record['matrix'],dtype=float)
    if (K.shape!=(62,16) or not np.isfinite(K).all()
        or not np.array_equal(K[:53,10:16],reference.matrix[:,10:16]) or np.any(K[53:,10:16])):
        raise ValueError('kinematic_fixed_velocity_readout')
    return KinematicModel(_readonly(K),reference)


def fit_screen(candidates,baselines):
    if any(r['family']!='nonlinear_v35' or r['mode']!='kinematic_state_projected' for r in candidates):
        raise ValueError('kinematic_score_identity')
    # Reuse exactly the frozen arithmetic after an internal schema adapter.
    # Episode roles, identities, metrics, origins and output records are unchanged.
    normalized=[dict(r,family='nonlinear_v34',mode='full_state_projected') for r in candidates]
    return previous_screen(normalized,baselines)
