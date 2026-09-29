"""Fit-only identifiability summaries, with constant directions kept explicit."""
import numpy as np
from workflows.identification_protocol_v29 import cases,pulse
from koopman.projected_edmd_v24 import rotation
from koopman.physical_terms_v26 import continuous_rate


def matrix_audit(values,names,*,active_std_floor=1e-9):
    x=np.asarray(values,dtype=float)
    if x.ndim!=2 or x.shape[1]!=len(names) or len(x)<2 or not np.isfinite(x).all():
        raise ValueError('identification_coverage_matrix')
    scale=x.std(0);active=scale>active_std_floor;centered=(x[:,active]-x[:,active].mean(0))/scale[active]
    sv=np.linalg.svd(centered,compute_uv=False)
    rank=int(np.sum(sv>sv[0]*1e-7)) if len(sv) else 0
    corr=centered.T@centered/len(x);np.fill_diagonal(corr,0)
    return {'rows':len(x),'columns':list(names),'minimum':x.min(0).tolist(),'maximum':x.max(0).tolist(),
        'std':scale.tolist(),'active_columns':[n for n,a in zip(names,active) if a],
        'constant_columns':[n for n,a in zip(names,active) if not a],
        'centered_rank':rank,'rank_relative_tolerance':1e-7,'active_std_floor':active_std_floor,
        'standardized_singular_values':sv.tolist(),
        'retained_condition':float(sv[0]/sv[rank-1]) if rank else None,
        'maximum_abs_active_correlation':float(np.max(np.abs(corr))) if corr.size else 0.}


def validate_fit_inventory(episodes):
    expected=[q for q in cases() if q['role']=='fit'];ids={q['run_id']:q for q in expected}
    if (len(episodes)!=len(ids) or {e.case['run_id'] for e in episodes}!=set(ids)
        or len({e.source_commit for e in episodes})!=1
        or any(e.case!=ids.get(e.case['run_id']) or e.acceptance.get('training_eligible') is not True for e in episodes)):
        raise ValueError('identification_fit_inventory')


STATE_NAMES=['z']+[f'R{j}{i}' for i in range(2) for j in range(3)]+['vx','vy','vz','wx','wy','wz']
INPUT_NAMES=['ax','ay','az','alphax','alphay','alphaz']


def state_matrix(x):
    r=rotation(x[:,1:5])
    return np.c_[x[:,0],r[:,:,0],r[:,:,1],x[:,5:]]


def coverage(episodes):
    validate_fit_inventory(episodes);configs=list(dict.fromkeys(q['configuration'] for q in cases()));records={}
    for name in configs:
        group=[e for e in episodes if e.case['configuration']==name]
        # Main identifiability summaries exclude the repeated 128-control startup.
        x=np.concatenate([e.states[256:-1] for e in group]);u=np.concatenate([e.acceleration[256:] for e in group])
        ex=np.concatenate([np.repeat(pulse(e.case)[128:],2,axis=0) for e in group])
        targets=np.concatenate([(e.states[257:,5:]-e.states[256:-1,5:])*120 for e in group])
        physical=np.concatenate([continuous_rate(e.states[256:-1],e.acceleration[256:],e.context) for e in group])
        pwm=np.concatenate([e.arrays['pwm'][256:] for e in group]);s=state_matrix(x)
        records[name]={'fit_episode_ids':[e.case['run_id'] for e in group],
            'external_excitation':matrix_audit(ex,['roll','pitch','yaw','heave']),
            'actual_causal_acceleration':matrix_audit(u,INPUT_NAMES),
            'engineering_amplitude_causal_acceleration':matrix_audit(u,INPUT_NAMES,active_std_floor=1e-5),
            'state':matrix_audit(s,STATE_NAMES),'state_input_joint':matrix_audit(np.c_[s,u],STATE_NAMES+INPUT_NAMES),
            'per_episode_state':[dict(run_id=e.case['run_id'],**matrix_audit(state_matrix(e.states[256:]),STATE_NAMES)) for e in group],
            'below_deadzone_fraction_per_rotor':np.mean(np.abs(pwm)<float(np.float32(.02)),axis=0).tolist(),
            'pwm_minimum_headroom':float(1-np.max(np.abs(pwm))),
            'continuous_physics_rate_residual_rmse_6':np.sqrt(np.mean((targets-physical)**2,axis=0)).tolist(),
            'continuous_physics_scope':'Source continuous approximation, not an exact discrete backend or fitted model.'}
    # Describe each held-out configuration against only the other seven fit
    # configurations. Axis-aligned support is a diagnostic, not joint coverage.
    loco={}
    for name in configs:
        train=np.concatenate([state_matrix(e.states[256:]) for e in episodes if e.case['configuration']!=name])
        held=np.concatenate([state_matrix(e.states[256:]) for e in episodes if e.case['configuration']==name])
        lo=train.min(0);hi=train.max(0);outside=(held<lo-1e-6)|(held>hi+1e-6)
        excess=np.maximum(np.maximum(lo-held,held-hi),0.)
        loco[name]={'feature_names':STATE_NAMES,'other_configuration_minimum':lo.tolist(),
            'other_configuration_maximum':hi.tolist(),'outside_fraction_per_feature':outside.mean(0).tolist(),
            'any_feature_outside_fraction':float(outside.any(1).mean()),
            'dynamics_excluding_absolute_height_outside_fraction':float(outside[:,1:].any(1).mean()),
            'maximum_absolute_excess_per_feature':excess.max(0).tolist(),
            'absolute_tolerance':1e-6,'scope':'Excitation fit only; axis-aligned support does not certify interpolation.'}
    return {'status':'fit_coverage_descriptive_audit','training_role':'fit','source_commit':episodes[0].source_commit,
        'fit_episode_hashes':{e.case['run_id']:e.trace_sha256 for e in episodes},
        'primary_start_physics_index':256,'startup_preserved':True,'configurations':records,'leave_one_configuration_state_support':loco,
        'new_model_fits':0,'coverage_go':None,'model_handoff':False,
        'limits':'Ranks are empirical for these trajectories; they do not prove global excitation or cross-configuration generalization.'}
