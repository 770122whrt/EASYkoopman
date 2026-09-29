"""Offline float32 dot-product replay with an explicit rounding-error bound.

The recorded and reconstructed wrench are checked independently against the
float64 sum of identical float32 products using gamma_(2*n). This only handles
evaluation order; command binding, residual consistency and every physical
acceptance threshold remain unchanged. No runtime collector imports this file.
"""
import numpy as np
from koopman.cached_checks_v53 import CachedTrackingMap
from koopman.bounded_feedback_v46 import FeedbackConfig,feedback_demand
from koopman.bounded_mpc_v44 import COMMAND_ATOL


def replay_recorded_residual(mapping,expected,logged):
    raw=np.asarray(logged['pwm_raw'],dtype=np.float32)
    if (raw.shape!=np.asarray(expected['pwm_raw']).shape or not np.isfinite(raw).all()
            or not np.allclose(raw,expected['pwm_raw'],rtol=0,atol=1e-7)
            or not np.array_equal(logged['command'],expected['command'])
            or not np.allclose(logged['target_wrench'],expected['target_wrench'],rtol=0,atol=1e-7)):
        raise ValueError('inexact_recorded_pwm_binding')
    pwm=np.clip(raw,-1,1);speed=np.zeros_like(pwm)
    positive=pwm>=np.float32(.02);negative=pwm<=-np.float32(.02)
    p=pwm[positive];n=pwm[negative]
    speed[positive]=(np.float32(-139)*(p*p)+np.float32(500)*p)+np.float32(8.28)
    speed[negative]=(np.float32(161)*(n*n)+np.float32(517.86)*n)-np.float32(5.72)
    force=mapping.allocator.rotor_constant*np.abs(speed)*speed
    wrench=(mapping.allocator.wrench_matrix@force).astype(float)
    error=(wrench-expected['target_wrench'])/mapping.scale
    matrix=mapping.allocator.wrench_matrix.astype(np.float64)
    products=matrix*force.astype(np.float64)[None,:]
    reference=products.sum(axis=1)
    unit_roundoff=np.finfo(np.float32).eps/2
    count=2*products.shape[1]
    gamma=count*unit_roundoff/(1-count*unit_roundoff)
    bound=np.maximum(1e-7,gamma*np.abs(products).sum(axis=1))
    logged_wrench=np.asarray(logged['steady_wrench'],dtype=float)
    logged_error=(logged_wrench-np.asarray(logged['target_wrench']))/mapping.scale
    from workflows.workpoint_v27 import ACCELERATION_TOLERANCE
    if (not np.isfinite(logged_wrench).all()
            or np.any(np.abs(wrench-reference)>bound)
            or np.any(np.abs(logged_wrench-reference)>bound)
            or not np.allclose(logged_error,logged['acceleration_error'],rtol=0,atol=1e-7)
            or bool(np.all(np.abs(logged_error)<=ACCELERATION_TOLERANCE))!=logged['physical_residual_accepted']
            or bool(np.all(np.abs(error)<=ACCELERATION_TOLERANCE))!=logged['physical_residual_accepted']):
        raise ValueError('inexact_recorded_residual_truth')


def validate_tracking_audit(data, domain, context):
    records=data['inexact_feedback_audit'];intervals=data['intervals']
    if not 1 <= len(records) <= len(intervals):raise ValueError('inexact_audit_count')
    mapping=CachedTrackingMap(domain.configuration,context);config=FeedbackConfig(slew=.02)
    seen=set();unmet=0;limited=0;zero=0
    for item in records:
        index=item['physics_index']
        if type(index) is not int or index%4 or index in seen or not 0<=index<4*len(intervals):
            raise ValueError('inexact_audit_index')
        seen.add(index);i=index//4;row=intervals[i];r=item['result']
        state=np.asarray(data['substeps'][index]['before']['state_11'][0])
        if not np.allclose(item['state'],state,rtol=0,atol=1e-7):raise ValueError('inexact_audit_state')
        ref=np.asarray(data['case']['reference'])
        if not np.array_equal(item['reference'],ref):raise ValueError('inexact_audit_reference')
        if r['status']!='ready' or r['target_rewritten'] is not False:raise ValueError('inexact_audit_status')
        packet=row['decision']['packet'];u=np.asarray(packet['command'])
        if not np.array_equal(u,r['command']):raise ValueError('inexact_audit_command')
        target=feedback_demand(state,ref,domain.configuration,context,config)['target_wrench']
        if not np.allclose(r['requested_wrench'],target,rtol=0,atol=1e-7):raise ValueError('inexact_audit_target')
        lower=domain.command_lower.copy();upper=domain.command_upper.copy()
        if i:
            old=np.asarray(intervals[i-1]['decision']['packet']['command'])
            if not np.array_equal(item['previous'],old):raise ValueError('inexact_audit_previous')
            lower=np.maximum(lower,old-config.slew);upper=np.minimum(upper,old+config.slew)
        elif item['previous'] is not None:raise ValueError('inexact_startup_previous')
        check=mapping.inspect(u,target,lower,upper)
        if not check['command_constraints_accepted']:raise ValueError('inexact_actual_constraints')
        static=mapping.inspect(r['static_command'],target,-.95*mapping.mask,.95*mapping.mask)
        if not static['command_constraints_accepted']:raise ValueError('inexact_static_constraints')
        expected_zero = bool(i and np.max(np.abs(u-old))<=COMMAND_ATOL)
        if r['zero_progress'] is not expected_zero:raise ValueError('inexact_zero_progress')
        for expected,logged in ((check,r['inspection']),(static,r['static_inspection'])):
            replay_recorded_residual(mapping,expected,logged)
            if (bool(expected['command_constraints_accepted'])!=logged['command_constraints_accepted']
                or bool(expected['physical_residual_accepted'])!=logged['physical_residual_accepted']):
                raise ValueError('inexact_residual_truth')
        expected_status='target_attained' if check['physical_residual_accepted'] else 'tracking_limited'
        if r['tracking_status']!=expected_status:raise ValueError('inexact_tracking_status')
        if not static['physical_residual_accepted']:
            unmet+=1
            if 'static_residual_unmet' not in r['limitations']:raise ValueError('inexact_unmet_not_recorded')
        limited+=int(expected_status=='tracking_limited');zero+=int(bool(r['zero_progress']))
    expected_indices={e['physics_index'] for e in data['arbitration_audit']
        if e['method']=='choose' and e.get('result',{}).get('status')=='fallback'}
    if seen!=expected_indices:raise ValueError('inexact_decision_audit_missing')
    if data['case']['controller']=='feedback' and seen!=set(range(0,4*len(intervals),4)):
        raise ValueError('inexact_feedback_audit_missing')
    return dict(decisions=len(records),static_residual_unmet=unmet,tracking_limited=limited,zero_progress=zero)
