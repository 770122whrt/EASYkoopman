"""Frozen fresh-role feedback-identification pilot; no simulation on import."""
import hashlib
import json
import numpy as np
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from workflows.workpoint_v27 import mechanics

EXPERIMENT='phase8.4-repaired-feedback-validation-v32-20260913-r19'
REMOTE_ROOT='/root/EASYkoopman-phase8-4-validation-20260913-r19'
TRANSFER_ROOT='/root/phase84-transfer-20260913/validation-r19'


def cases():
    return [{'run_id':f'i32-{name}-validation-{8900+2*i+j}-{family}',
             'configuration':name,'role':'validation','seed':8900+2*i+j,'excitation':family,
             'intervals':320,'training_eligible':False,'starting_z_m':5.5,'mode':'direct_pre_tam_v24'}
            for i,name in enumerate(SUPPORTED_EMBODIMENTS) for j,family in enumerate(('prbs','multisine'))]


def validate_case(q):
    if not isinstance(q,dict) or type(q.get('training_eligible')) is not bool or q not in cases():
        raise ValueError('identification_case')
    return q


def protocol():
    return {'experiment':EXPERIMENT,'version':'repaired-feedback-validation-v32',
            'cases':cases(),'physics_dt_s':1/120,'control_dt_s':1/60,'startup_control_intervals':128,
            'pulse_acceleration_4':[2.,1.,.5,.25],
            'excitation':{'prbs_pair_intervals':24,'prbs_sign_intervals':12,
                          'prbs_first_four_pairs':'seed_permuted_signed_hadamard4',
                          'multisine_cycles_by_axis':[[1+j,3+j,5+j] for j in range(4)],
                          'chirp_cycles_start_end_by_axis':[[1+j/4,4+j] for j in range(4)]},
            'initialization':'identity_pose_zero_velocity_zero_rotors_complete_history',
            'validation_access':'after_r18_failure_pullback_v31_source_regression_and_new_source_model_evaluation_freeze',
            'resource_cap':{'collector_seconds':5400,'native_case_seconds':300,'native_processes_total_including_prior':54,
                            'analysis_seconds':3600,'disk_bytes':4*1024**3},
            'model_handoff':False,'test_access':False}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def pulse(q):
    validate_case(q);p=protocol();n=q['intervals']-128
    result=np.zeros((q['intervals'],4),dtype=np.float32)
    rng=np.random.default_rng(q['seed']);phase=rng.uniform(-np.pi,np.pi,size=(4,3))
    t=np.arange(n,dtype=float)/n
    if q['excitation']=='prbs':
        # Guarantee full controllable-axis input rank without choosing seeds
        # after observing data. Random remaining pairs retain independent drive.
        h=np.array([[1,1,1,1],[1,-1,1,-1],[1,1,-1,-1],[1,-1,-1,1]],dtype=float)
        pairs=rng.choice([-1.,1.],size=((n+23)//24,4))
        pairs[:4]=h[rng.permutation(4)]*rng.choice([-1.,1.],size=4)
    for axis,amplitude in enumerate(p['pulse_acceleration_4']):
        if not mechanics(q['configuration'])['control_mask_4'][axis]:continue
        if q['excitation']=='prbs':
            signs=pairs[:,axis]
            value=np.repeat(np.column_stack((signs,-signs)).reshape(-1),12)[:n]
        elif q['excitation']=='multisine':
            cycles=np.asarray(p['excitation']['multisine_cycles_by_axis'][axis])
            value=np.sin(2*np.pi*t[:,None]*cycles+phase[axis]).sum(1)/3
        else:
            low,high=p['excitation']['chirp_cycles_start_end_by_axis'][axis]
            value=np.sin(2*np.pi*(low*t+.5*(high-low)*t*t)+phase[axis,0])
        result[128:,axis]=amplitude*value
    return result


def guarded_exit_code(native_exit,report,request,source):
    if native_exit:return native_exit if native_exit>0 else 128-native_exit
    try:validate_case(request)
    except ValueError:return 1
    if (not isinstance(report,dict) or report.get('status')!='completed_identification_pending_acceptance'
            or report.get('request')!=request or report.get('source_commit')!=source
            or report.get('training_eligible') is not False or report.get('model_fits')!=0):
        return 1
    return 0
