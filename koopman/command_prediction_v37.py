"""v37 actual-mass admission repair for the fixed direct pre-TAM predictor.

This composes the accepted actuator recurrence and a supplied stateless predictor.
It is not a new fitted model, a constant-B system, or a deployed MPC controller.
"""
import time
import numpy as np
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
from koopman.projected_edmd_v24 import PhysicalContext
from workflows.workpoint_v27 import mechanics
from workflows.control_seam_v23 import ControlKernel
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from workflows.identification_prediction_v32 import valid_predictions


def validate_context(configuration,context):
    """Reject a different body/physics context in this static-catalog interface.

    These are admission checks, not estimates of actual runtime parameters.
    Live use still requires the runtime readback/initialization evidence gate.
    """
    m=mechanics(configuration)
    expected=PhysicalContext(m['mass_kg'],m['inertia_kg_m2'],m['cob_m'],m['volume_m3'],
        EMBODIMENT_CONFIGS[configuration]['drag_multiplier'],rho=m['water_density_kg_m3'],gravity=m['gravity_m_s2'])
    # PhysX stores inverse mass, then getMass reciprocates it again. Admit
    # only the authored float32 value or this specific float32 roundtrip.
    # Do not replace the caller's observed mass used in acceleration/prediction.
    roundtrip=float(np.float32(1)/np.float32(np.float32(1)/np.float32(expected.mass)))
    if (not isinstance(context,PhysicalContext) or context.mass not in (expected.mass,roundtrip)
        or any(not np.array_equal(getattr(context,k),getattr(expected,k))
            for k in ('inertia','cob','volume','drag_multiplier','rho','beta','gravity'))):
        raise ValueError('command_context_mismatch')
    return m


def forecast_commands(initial_state,issued_control_history,planned_commands,configuration,context,predictor,*,origin_control,deadline=None):
    """Forecast1..128 held control commands, each with two physical substeps.

    History contains every PHYSICS command since a known-zero rotor reset and
    must end at origin_control. Matching the length is not authentication of
    history contents; callers must admit the source/history before invoking this.
    Every call owns its kernel, clock and rotor recurrence. Predictors must be
    stateless (the admitted frozen SparseModel or matched stateless baselines).
    """
    x=np.array(initial_state,dtype=float,copy=True);history=np.array(issued_control_history,dtype=float,copy=True)
    drive=np.array(planned_commands,dtype=float,copy=True)
    if (type(origin_control) is not int or origin_control<0 or history.ndim!=2 or history.shape!=(2*origin_control,4)
        or not np.isfinite(history).all() or np.any(np.abs(history)>.95)):
        raise ValueError('command_history_invalid')
    if (x.shape!=(11,) or not valid_predictions(x[None])[0] or drive.ndim!=2 or drive.shape[1]!=4
        or not 1<=len(drive)<=128 or not np.isfinite(drive).all() or np.any(np.abs(drive)>.95)
        or not callable(predictor)):
        raise ValueError('command_forecast_input_invalid')
    m=validate_context(configuration,context);kernel=ControlKernel(configuration)
    estimator=Float32PWMActuatorState(kernel.env._num_thrusters,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    def check_time():
        if deadline is not None and time.monotonic()>=deadline:raise TimeoutError('command_prediction_budget')
    for command in history:
        check_time();estimator.advance_pwm(kernel.command(command,pre_tam=True)['pwm'])
    initial_speed=estimator.current();initial_clock=estimator.elapsed_time
    scale=np.r_[[context.mass]*3,context.inertia];states=[];pwm_rows=[];speeds=[];inputs=[];applied=[];times=[];issued=[];failure=None
    for control,request in enumerate(drive):
        check_time();substep=0
        try:
            command=request.astype(np.float32);allocation=kernel.command(command,pre_tam=True);issued.append(command.copy())
            for substep in range(2):
                check_time();speed=estimator.advance_pwm(allocation['pwm'])
                wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed);acceleration=wrench/scale
                following=np.asarray(predictor(x[None],acceleration[None],context),dtype=float)
                if following.shape!=(1,11) or not valid_predictions(following)[0]:raise ValueError('command_prediction_invalid')
                x=following[0].copy();states.append(x.copy());pwm_rows.append(allocation['pwm'].copy());speeds.append(speed.copy())
                inputs.append(acceleration.copy());applied.append(allocation['virtual_control'].copy());times.append(estimator.elapsed_time)
        except (ValueError,FloatingPointError) as exc:
            failure={'control_index':control,'physics_substep':substep,'completed_physics_ticks':len(states),
                'exception':f'{type(exc).__name__}:{exc}'};break
    n=kernel.env._num_thrusters
    return {'complete':failure is None,'failure':failure,'completed_control_intervals':len(states)//2,
        'origin_control':origin_control,'origin_actuator_time_s':initial_clock,'origin_rotor_speed':initial_speed,
        'requested_commands':drive,'issued_commands':np.asarray(issued,dtype=np.float32).reshape(-1,4),
        'control_mask':np.array(m['control_mask_4']),'applied_control':np.asarray(applied,dtype=np.float32).reshape(-1,4),
        'predictions':np.asarray(states).reshape(-1,11),'pwm':np.asarray(pwm_rows,dtype=np.float32).reshape(-1,n),
        'rotor_speed':np.asarray(speeds).reshape(-1,n),'acceleration':np.asarray(inputs).reshape(-1,6),
        'physics_time_s':np.asarray(times),'input_contract':'bounded4D_direct_preTAM_held_two_substeps',
        'future_inputs':'planned_commands_and_own_rotor_recurrence','model_handoff':False}
