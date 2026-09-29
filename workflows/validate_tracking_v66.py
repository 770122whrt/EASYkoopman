"""Recompute the inexact feedback residual record from actual boundary states."""
import numpy as np
from koopman.cached_checks_v53 import CachedTrackingMap
from koopman.bounded_feedback_v46 import FeedbackConfig,feedback_demand
from koopman.bounded_mpc_v44 import COMMAND_ATOL


def validate_tracking_audit(data, domain, context):
    records=data['inexact_feedback_audit'];intervals=data['intervals']
    if not 1 <= len(records) <= len(intervals):raise ValueError('inexact_audit_count')
    mapping=CachedTrackingMap(domain.configuration,context);config=FeedbackConfig()
    seen=set();unmet=0;limited=0;zero=0
    for item in records:
        index=item['physics_index']
        if type(index) is not int or index%2 or index in seen or not 0<=index<2*len(intervals):
            raise ValueError('inexact_audit_index')
        seen.add(index);i=index//2;row=intervals[i];r=item['result']
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
            if (bool(expected['command_constraints_accepted'])!=logged['command_constraints_accepted']
                or bool(expected['physical_residual_accepted'])!=logged['physical_residual_accepted']
                or not np.allclose(expected['acceleration_error'],logged['acceleration_error'],rtol=0,atol=1e-7)):
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
    if data['case']['controller']=='feedback' and seen!=set(range(0,2*len(intervals),2)):
        raise ValueError('inexact_feedback_audit_missing')
    return dict(decisions=len(records),static_residual_unmet=unmet,tracking_limited=limited,zero_progress=zero)
