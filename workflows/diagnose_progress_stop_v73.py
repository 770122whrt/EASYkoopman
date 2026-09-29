"""Read-only diagnosis of a feedback progress stop, not an isolation permit."""
import numpy as np
from koopman.runtime_coordinator_v52 import ProgressGuard
from koopman.rate30_v67 import RUNTIME_CONFIG
from koopman.cached_checks_v53 import CachedTrackingMap
from koopman.bounded_mpc_v44 import COMMAND_ATOL
from workflows.control_seam_v23 import ControlKernel
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from workflows.validate_effects_v67 import (same, check_runtime_context,
    check_state_backend, contact_screen, domain_screen, compare_values)
from workflows.validate_tracking_v73 import validate_tracking_audit


def diagnose(data, domain, context):
    case=data['case']; rows=data['substeps']; intervals=data['intervals']
    if (case['controller']!='feedback' or data['exception']!='ValueError:runtime_persistent_zero_progress'
            or data['cleanup_errors'] or not all(data['cleanup_completed'][k] for k in ('environment','simulation_app'))
            or len(rows)%4 or len(intervals)!=len(rows)//4+1):
        raise ValueError('progress_stop_binding')
    final=data['runtime_final']; stats=final['stats']
    if (stats['requests'] or stats['mpc_activations'] or final['physics_index']!=len(rows)
            or stats['dispatches']!=len(rows)//4 or stats['confirmed_controls']!=len(rows)//4
            or not final['stopped'] or final['pending']):
        raise ValueError('progress_stop_final')
    terminal=intervals[-1]
    if (terminal['physics_index']!=len(rows) or terminal['status']!='stopped'
            or terminal['decision']!={'status':'stop','reason':'persistent_zero_progress',
                'packet':None,'actual_history_advanced':False}):
        raise ValueError('progress_terminal_interval')
    # The final boundary stopped before any command was proposed or dispatched.
    # Audit only issued commands, while explicitly validating that stop above.
    feedback=validate_tracking_audit(dict(data,intervals=intervals[:-1]),domain,context)
    mapping=CachedTrackingMap(case['configuration'],context)
    kernel=ControlKernel(case['configuration'])
    estimator=Float32PWMActuatorState(kernel.env._num_thrusters,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    maximum=np.zeros(4)
    for j,row in enumerate(rows):
        same(row['before']['state_11'],data['reset_record']['snapshot']['state_11'] if not j else rows[j-1]['state_after_physics_11'],label='progress_state_seam')
        command=np.asarray(intervals[j//4]['decision']['packet']['command'],dtype=np.float32)
        sent=kernel.command(command,pre_tam=True); speed=estimator.advance_pwm(sent['pwm'])
        wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed)
        telemetry=row['command']['telemetry']
        maximum=np.maximum(maximum,[np.max(np.abs(command-np.asarray(telemetry['virtual_control_4'])[0])),
            np.max(np.abs(sent['pwm']-np.asarray(telemetry['motor_pwm_n'])[0])),
            np.max(np.abs(speed-np.asarray(row['command']['actuator_speed_n'])[0])),
            np.max(np.abs(wrench-np.asarray(telemetry['applied_wrench_6'])[0]))])
        check_runtime_context(row['before'],case['configuration'],context)
        check_state_backend(row['before']['state_11'],row['before']['backend'])
        check_state_backend(row['state_after_physics_11'],row['backend_after_physics'])
        if domain.check_states(np.asarray(row['before']['state_11'])) or domain.check_states(np.asarray(row['state_after_physics_11'])):
            raise ValueError('progress_stop_has_support_failure')
        for actual,key in ((contact_screen(row,data['geometry']),'free_water_screen_v26'),
                (domain_screen(row,data['geometry'],5.5),'calibration_screen_v27')):
            compare_values(actual,row[key])
            if not actual['screen_pass']:raise ValueError('progress_stop_has_physical_failure')
    if not np.isfinite(maximum).all() or np.any(maximum>[1e-6,1e-6,1e-3,1e-3]):
        raise ValueError('progress_stop_command_reconstruction')
    guard=ProgressGuard(case['configuration'],config=RUNTIME_CONFIG); records=[]
    audit=data['inexact_feedback_audit']
    for i in range(len(rows)//4+1):
        state=rows[4*i]['before']['state_11'][0] if 4*i<len(rows) else rows[-1]['state_after_physics_11'][0]
        result=guard.observe(i,state,case['reference'],reference_id=case['reference_id'],
            last_tracking=None if not i else audit[i-1]['result'])
        if i<len(rows)//4 and result['status']!='continue':raise ValueError('progress_stopped_earlier')
        records.append(dict(control_index=i,**result))
    if result!={'status':'stop','reason':'persistent_zero_progress'}:
        raise ValueError('progress_stop_not_reproduced')
    terminal=intervals[-1]
    if terminal['physics_index']!=len(rows) or terminal['status']!='stopped':raise ValueError('progress_terminal_interval')
    last=audit[-1]['result']; old=np.asarray(audit[-1]['previous']); full=np.asarray(last['static_command'])
    lower=np.maximum(domain.command_lower,old-.02); upper=np.minimum(domain.command_upper,old+.02)
    delta=full-old; factors=[]
    for axis in np.flatnonzero(delta):
        available=(upper[axis]-old[axis]) if delta[axis]>0 else (lower[axis]-old[axis])
        factors.append(dict(axis=int(axis),factor=max(0.,float(available/delta[axis]))))
    alternative=np.clip(full,lower,upper).astype(np.float32)
    alt=mapping.inspect(alternative,last['requested_wrench'],lower,upper)
    return dict(status='feedback_progress_stop_diagnosed_not_isolated',physical_steps=len(rows),
        complete_episode=False,configuration_isolation_authorized=False,arbitration_digest_replay_performed=False,
        mpc_activations=stats['mpc_activations'],feedback_audit=feedback,
        maximum_control_pwm_speed_wrench_errors=maximum.tolist(),progress_guard=records,
        command_lower=domain.command_lower.tolist(),command_upper=domain.command_upper.tolist(),
        last_actual_command=last['command'],last_static_command=last['static_command'],
        last_command_delta=float(np.max(np.abs(np.asarray(last['command'])-old))),zero_progress_atol=COMMAND_ATOL,
        common_interpolation_factors=factors,actual_acceleration_error=last['inspection']['acceleration_error'],
        alternative_axiswise_command=alternative.tolist(),alternative_constraints_accepted=alt['command_constraints_accepted'],
        alternative_acceleration_error=alt['acceleration_error'].tolist(),
        alternative_claim='One recorded-state static diagnostic only; not deployed and not a closed-loop repair')
