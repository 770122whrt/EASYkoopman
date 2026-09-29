"""Load the frozen physical baseline and its admitted fit cache; never refit it."""
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,re
import numpy as np
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from koopman.physics_context import PhysicalContext,_readonly
from koopman.sparse_physics import feature_names,core_matrix,predict_projected

def cases():
    result=[]
    for i,name in enumerate(SUPPORTED_EMBODIMENTS):
        items=[('preflight',8710+i,'prbs',256)]
        items += [('fit',8720+3*i+j,f,320) for j,f in enumerate(('prbs','multisine','chirp'))]
        items += [('validation',8800+2*i+j,f,320) for j,f in enumerate(('prbs','multisine'))]
        for role,seed,family,n in items:
            result.append({'run_id':f'i29-{name}-{role}-{seed}-{family}',
                           'configuration':name,'role':role,'seed':seed,'excitation':family,
                           'intervals':n,'training_eligible':role=='fit',
                           'starting_z_m':5.5,'mode':'direct_pre_tam_v24'})
    return result

@dataclass(frozen=True)
class Episode:
    case:dict
    source_commit:str
    trace_sha256:str
    arrays:dict
    acceleration:np.ndarray
    context:PhysicalContext
    acceptance:dict

    @property
    def states(self):return self.arrays['states']

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
