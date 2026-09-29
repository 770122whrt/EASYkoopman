"""Fit-only sparse physical velocity rows and complete finite lifted matrices."""
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,re
import numpy as np
from koopman.projected_edmd_v24 import PhysicalContext,_readonly
from koopman.sparse_world_edmd_v30 import feature_names,lift,input_effect,core_matrix,box_ridge,predict_projected,DT
from workflows.identification_protocol_v29 import cases
from workflows.identification_adapter_v29 import Episode


def _expected(configurations):
    supported={q['configuration'] for q in cases()}
    if not configurations or len(set(configurations))!=len(configurations) or not set(configurations)<=supported:
        raise ValueError('sparse_configurations')
    return {q['run_id']:q for q in cases() if q['role']=='fit' and q['configuration'] in configurations}


def validate_matrix(matrix,family,damping,quadratic,angular_damping):
    a=np.asarray(matrix,dtype=float);expected=core_matrix(family,damping,quadratic,angular_damping)
    if (a.shape!=expected.shape or not np.isfinite(a).all()
            or not np.array_equal(a[:,10:16],expected[:,10:16])
            or np.any(a[:-1,-1]) or a[-1,-1]!=1):raise ValueError('sparse_matrix_constraint')
    return a


@dataclass(frozen=True)
class SparseModel:
    family:str
    matrix:np.ndarray
    damping:np.ndarray
    quadratic:np.ndarray
    angular_damping:float
    audit:dict

    def __call__(self,states,acceleration,context):
        return predict_projected(states,acceleration,context,self.matrix,self.family,self.angular_damping)


def from_record(record):
    expected=_expected(record['configurations']);names=feature_names(record['family'])
    if (record['schema']!='sparse-world-edmd-v30' or record['feature_names']!=names
            or not re.fullmatch('[0-9a-f]{40}',record['fit_source'])
            or set(record['fit_episode_hashes'])!=set(expected)
            or any(not re.fullmatch('[0-9a-f]{64}',h) for h in record['fit_episode_hashes'].values())
            or record['audit']['training_role']!='fit' or record['audit']['full_lift_operator'] is not True):
        raise ValueError('sparse_model_record')
    matrix=validate_matrix(record['matrix'],record['family'],record['damping'],record['quadratic'],record['angular_damping'])
    return SparseModel(record['family'],_readonly(matrix),_readonly(record['damping']),_readonly(record['quadratic']),record['angular_damping'],record['audit'])


def fit_model(episodes,family,configurations,*,angular_damping=float(np.float32(.05))):
    expected=_expected(configurations);names=feature_names(family);index={n:i for i,n in enumerate(names)}
    if (len(episodes)!=len(expected) or {e.case['run_id'] for e in episodes}!=set(expected)
            or len({e.source_commit for e in episodes})!=1
            or any(e.case!=expected.get(e.case['run_id']) or e.acceptance.get('training_eligible') is not True for e in episodes)):
        raise ValueError('sparse_fit_inventory')
    ordered=sorted(episodes,key=lambda e:list(expected).index(e.case['run_id']));current=[];following=[];effects=[];weights=[]
    for e in ordered:
        if e.states.shape!=(641,11) or e.acceleration.shape!=(640,6):raise ValueError('sparse_fit_episode_shape')
        current.append(lift(e.states[:-1],e.context,family));following.append(lift(e.states[1:],e.context,family))
        effects.append(input_effect(e.states[:-1],e.acceleration,e.context,family,angular_damping))
        weights.append(np.r_[np.full(256,1/3),np.ones(384)])
    a=np.concatenate(current);b=np.concatenate(following);effect=np.concatenate(effects);weight=np.concatenate(weights)
    wn=weight/weight.sum();factor=1-angular_damping*DT
    zero=core_matrix(family,np.zeros(6),np.zeros(6),angular_damping)
    residual=(b-(a@zero+effect))[:,10:16]/DT
    columns=[-a[:,[index[f'axis_velocity_{j}_{k}'] for k in range(3)]] for j in range(3)]
    if family=='nonlinear':columns += [a[:,[index[f'axis_quadratic_{j}_{k}'] for k in range(3)]] for j in range(3)]
    design=np.stack(columns,axis=2).reshape(-1,len(columns))
    lower=[0]*len(columns);upper=[20]*3+([2]*3 if family=='nonlinear' else []);prior=[0]*3+([1]*3 if family=='nonlinear' else [])
    linear,linear_audit=box_ridge(design,residual[:,:3].reshape(-1),np.repeat(weight,3),lower,upper,prior)
    damping=np.zeros(6);quadratic=np.zeros(6);damping[:3]=linear[:3]
    if family=='nonlinear':quadratic[:3]=linear[3:]
    angular_audits=[]
    for j in range(3):
        cols=[-factor*a[:,13+j]]
        if family=='nonlinear':cols.append(factor*a[:,index[f'angular_quadratic_{j}']])
        coefficient,audit=box_ridge(np.stack(cols,axis=1),residual[:,3+j],weight,[0]*len(cols),[20]+([2] if len(cols)==2 else []),[0]+([1] if len(cols)==2 else []))
        damping[3+j]=coefficient[0]
        if family=='nonlinear':quadratic[3+j]=coefficient[1]
        angular_audits.append(audit)
    # Full finite matrix is fitted and retained. Its velocity columns are then
    # replaced by the constrained physical rows above, not a dense free fit.
    mean=wn@a;scale=np.maximum(np.sqrt(wn@((a-mean)**2)),1e-6)
    design=(a-mean)/scale;target=(b-effect-a)/scale;bias=wn@target
    gram=design.T@(wn[:,None]*design);ridge=1e-6
    coefficient=np.linalg.solve(gram+ridge*np.eye(len(names)),design.T@(wn[:,None]*(target-bias)))
    increment=coefficient*scale[None,:]/scale[:,None]
    matrix=np.eye(len(names))+increment;matrix[-1,:]+=bias*scale-mean@increment
    matrix[:,-1]=0.;matrix[-1,-1]=1.
    structured=core_matrix(family,damping,quadratic,angular_damping);matrix[:,10:16]=structured[:,10:16]
    validate_matrix(matrix,family,damping,quadratic,angular_damping)
    reconstruction=a@matrix+effect
    audit={'training_role':'fit','fit_episodes':len(ordered),'fit_physics_rows':len(a),
        'weighted_rows':float(weight.sum()),'startup_weight':1/3,'excitation_weight':1.,
        'full_lift_operator':True,'dimension':len(names),'mean_ridge':ridge,
        'state_observables':'z_R9_world_linear_velocity_body_omega_parameterized_physics',
        'prediction':'known_predicted_velocity_kinematic_projection_then_relift',
        'input_map':'known_state_dependent_instantaneous_lift_kick; approximate finite step',
        'linear_velocity_fit':linear_audit,'angular_velocity_fits':angular_audits,
        'weighted_lift_one_step_rmse':np.sqrt(wn@((b-reconstruction)**2)).tolist(),
        'fit_matrix_sha256':hashlib.sha256(a.tobytes()+b.tobytes()+effect.tobytes()+weight.tobytes()).hexdigest(),
        'no_claim_of_unprojected_spectral_stability':True}
    record={'schema':'sparse-world-edmd-v30','family':family,'configurations':list(configurations),
        'fit_source':ordered[0].source_commit,'fit_episode_hashes':{e.case['run_id']:e.trace_sha256 for e in ordered},
        'feature_names':names,'matrix':matrix.tolist(),'damping':damping.tolist(),'quadratic':quadratic.tolist(),
        'angular_damping':angular_damping,'audit':audit}
    return record,from_record(record)


def load_fit_cache(root):
    root=Path(root);directory=root/'docs/evidence/phase8_4/identification-fit-20260913-r17'
    read=lambda p:json.loads(p.read_text(encoding='utf8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inventory=read(directory/'cache-inventory.json')
    path=root/'docs/evidence/phase8_4/server-identification-20260913-r17/fit/acceptance.json';acceptance=read(path)
    if (sha(path)!=inventory['fit_acceptance_sha256'] or inventory['episodes']!=24 or inventory['roles']!=['fit']
            or inventory['source_commit']!=acceptance['source_commit'] or acceptance['training_eligible'] is not True):
        raise ValueError('sparse_fit_cache_admission')
    for name,h in inventory['files_sha256'].items():
        if Path(name).name!=name or sha(directory/name)!=h:raise ValueError('sparse_fit_cache_hash')
    episodes=[]
    for q in [q for q in cases() if q['role']=='fit']:
        meta=directory/(q['run_id']+'.json');arrays=directory/(q['run_id']+'.npz')
        if not {meta.name,arrays.name}<=set(inventory['files_sha256']):raise ValueError('sparse_fit_cache_inventory')
        m=read(meta)
        if (m['case']!=q or m['source_commit']!=inventory['source_commit']
                or m['trace_sha256']!=acceptance['trace_sha256'][q['run_id']] or sha(arrays)!=m['arrays_sha256']
                or m['backend']!={'linear_damping_s':0.,'angular_damping_s':float(np.float32(.05)),'gyroscopic_forces_enabled':True}):
            raise ValueError('sparse_fit_cache_binding')
        with np.load(arrays,allow_pickle=False) as z:a={k:_readonly(z[k]) for k in z.files}
        acceleration=a.pop('acceleration')
        episodes.append(Episode(q,m['source_commit'],m['trace_sha256'],a,acceleration,PhysicalContext(**m['context']),m['acceptance']))
    return episodes
