"""Training-only common control envelope, separate from frozen plant parameters."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import numpy as np
from koopman.bounded_mpc_v44 import SupportDomain
from koopman.control_objective_v44 import state_features,control_mask
from koopman.lifted_propagation_v84 import coordinates,seal
from workflows.disturbance_protocol import get_protocol

cases = get_protocol('v87').cases

MODEL_SHA='5857a0e8d09cd04e33112b457b6a60f8b4147f3819815634edb6149ac95e137e'
RULE='union_old_and_train_plus_20pct_span_with_fixed_floor_v88'


@dataclass(frozen=True)
class TrainingSupportDomain(SupportDomain):
    support_record_sha256: str = ''
    support_training_sources: tuple = ()

    def record(self):
        return dict(super().record(),schema='common-training-support-v88',
            support_record_sha256=self.support_record_sha256,
            support_training_sources=list(self.support_training_sources))


def bounds(old,stats):
    lo=np.asarray(stats['feature_min'],float);hi=np.asarray(stats['feature_max'],float)
    ul=np.asarray(stats['command_min'],float);uh=np.asarray(stats['command_max'],float)
    if (lo.shape!=(11,) or hi.shape!=(11,) or ul.shape!=(4,) or uh.shape!=(4,)
            or not all(np.isfinite(a).all() for a in (lo,hi,ul,uh))
            or np.any(lo>hi) or np.any(ul>uh)):
        raise ValueError('v88_training_statistics')
    floor=np.full(11,.02);floor[3]=.002
    pad=np.maximum(floor,.2*(hi-lo))
    lower=np.minimum(old.state_lower,lo-pad);upper=np.maximum(old.state_upper,hi+pad)
    # Norm/tilt constraints are still separately checked, not approximated by boxes.
    hardlo=np.r_[3.5,-1.,-1.,.5,[-1.5]*3,[-3.]*3,0.]
    hardhi=np.r_[7.5,1.,1.,1.,[1.5]*3,[3.]*3,.6]
    lower=np.maximum(lower,hardlo);upper=np.minimum(upper,hardhi)
    upad=np.maximum(.002,.2*(uh-ul))
    command_lower=np.maximum(-.95,np.minimum(old.command_lower,ul-upad))
    command_upper=np.minimum(.95,np.maximum(old.command_upper,uh+upad))
    mask=control_mask('base');command_lower[mask==0]=command_upper[mask==0]=0.
    if np.any(lo<lower-1e-12) or np.any(hi>upper+1e-12) or np.any(ul<command_lower) or np.any(uh>command_upper):
        raise ValueError('v88_training_exceeds_hard_limits')
    return dict(state_lower=lower.tolist(),state_upper=upper.tolist(),
                command_lower=command_lower.tolist(),command_upper=command_upper.tolist())


def derive_record(old,episodes,model_sha,training_hashes):
    expected=[q for q in cases() if q['role']=='train']
    if (not old._verified_fit or old.configuration!='base' or [e['case'] for e in episodes]!=expected
            or {e['case']['run_id']:e['trace_sha256'] for e in episodes}!=training_hashes
            or len(set(training_hashes.values()))!=16):raise ValueError('v88_training_inventory')
    states=np.concatenate([e['states'] for e in episodes])
    commands=np.concatenate([e['commands'] for e in episodes])
    coordinates(states)
    if (commands.ndim!=2 or commands.shape[1]!=4 or not np.isfinite(commands).all()
            or np.max(np.linalg.norm(states[:,5:8],axis=1))>1.5
            or np.max(np.linalg.norm(states[:,8:],axis=1))>3):raise ValueError('v88_training_hard_limits')
    features=state_features(states,control_mask('base'))
    stats=dict(feature_min=features.min(0).tolist(),feature_max=features.max(0).tolist(),
        command_min=commands.min(0).tolist(),command_max=commands.max(0).tolist())
    return seal(dict(schema='frozen-common-support-v88',rule=RULE,model_sha256=model_sha,
        old_support_identity=old.identity,training_trace_hashes=training_hashes,
        training_statistics=stats,physical_recalibrated=False,model_fits=0,
        **bounds(old,stats)))


def restore_domain(record,old,model_sha,training_hashes):
    if record.get('content_sha256')!=seal(record)['content_sha256']:raise ValueError('v88_support_hash')
    if (record.get('schema')!='frozen-common-support-v88' or record.get('rule')!=RULE
            or record.get('model_sha256')!=model_sha or record.get('old_support_identity')!=old.identity
            or record.get('training_trace_hashes')!=training_hashes or len(set(training_hashes.values()))!=16
            or record.get('physical_recalibrated') is not False or record.get('model_fits')!=0
            or not old._verified_fit):raise ValueError('v88_support_identity')
    calculated=bounds(old,record['training_statistics'])
    if any(record.get(k)!=v for k,v in calculated.items()):raise ValueError('v88_support_bounds')
    d=TrainingSupportDomain('base',old.context_key,old.model_id,
        *(np.asarray(calculated[k]) for k in ('state_lower','state_upper','command_lower','command_upper')),
        old.fit_sources,record['content_sha256'],tuple(sorted(training_hashes.items())))
    # Legacy solver's admission flag means verified training provenance; physical
    # fit sources remain unchanged, additional support sources are explicit above.
    object.__setattr__(d,'_verified_fit',True)
    return d


def load_domain(path,expected_sha,old,model):
    from workflows.fit_disturbance import load_record
    payload=Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=expected_sha:raise ValueError('v88_support_file_hash')
    if hashlib.sha256(Path(model).read_bytes()).hexdigest()!=MODEL_SHA:raise ValueError('v88_frozen_model')
    learned,_=load_record(model)
    return restore_domain(json.loads(payload),old,MODEL_SHA,learned['fit_episode_hashes'])
