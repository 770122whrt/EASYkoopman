"""Two distinct prediction tests; a policy forecast has no future-truth argument."""
import time
import numpy as np
from workflows.evaluate_projected_edmd_v24 import squared_errors


def valid_predictions(x):
    return (np.isfinite(x).all(axis=1)&(np.abs(x[:,0])<=100)
            &np.all(np.abs(x[:,5:])<=100,axis=1)
            &(np.abs(np.linalg.norm(x[:,1:5],axis=1)-1)<=1e-3))


def conditional_rollout(states,acceleration,predictor,context,horizon,*,start_control=128):
    x=np.asarray(states,dtype=float);u=np.asarray(acceleration,dtype=float);steps=2*horizon
    if (x.ndim!=2 or x.shape[1]!=11 or u.shape!=(len(x)-1,6) or len(u)%2
            or type(horizon) is not int or horizon<1 or type(start_control) is not int or start_control<0
            or steps+2*start_control>len(u) or not np.isfinite(x).all() or not np.isfinite(u).all()):
        raise ValueError('identification_prediction_contract')
    origins=np.arange(2*start_control,len(u)-steps+1,2);prediction=x[origins].copy()
    alive=np.ones(len(origins),dtype=bool);first_failure=np.full(len(origins),-1,dtype=int)
    summed=np.zeros((len(origins),4));endpoint=np.zeros_like(summed);exceptions=[]
    for tick in range(steps):
        ids=np.flatnonzero(alive)
        if not len(ids):break
        try:
            with np.errstate(over='ignore',invalid='ignore',divide='ignore'):
                new=np.asarray(predictor(prediction[ids],u[origins[ids]+tick],context),dtype=float)
            if new.shape!=(len(ids),11):raise ValueError('identification_predictor_shape')
            prediction[ids]=new;good=valid_predictions(new)
        except (ValueError,FloatingPointError) as exc:
            exceptions.append({'tick':tick+1,'error':f'{type(exc).__name__}:{exc}'})
            good=np.zeros(len(ids),dtype=bool)
        bad=ids[~good];alive[bad]=False;first_failure[bad]=tick+1;ids=ids[good]
        if len(ids):
            error=squared_errors(x[origins[ids]+tick+1],prediction[ids]);summed[ids]+=error;endpoint[ids]=error
    complete=bool(alive.all())
    return {'horizon_control_intervals':horizon,'origins':len(origins),'origin_control_indices':(origins//2).tolist(),
        'failed_origins':int(np.sum(~alive)),'first_failure_physics_tick':first_failure.tolist(),'exceptions':exceptions,
        'endpoint_rmse':np.sqrt(endpoint.mean(0)).tolist() if complete else None,
        'path_rmse':np.sqrt(summed.mean(0)/steps).tolist() if complete else None,
        'complete_aggregate':complete,'conditional_future_recorded_inputs':True,
        'metrics':['z_m','rotation_rad','body_velocity_component_m_s','body_omega_component_rad_s']}


def policy_forecast(initial_state,issued_control_history,pulses,configuration,context,predictor,*,deadline=None):
    """Replay past issued commands, then generate every future command from own state.

    History is ordered PHYSICS commands ending at a control boundary. Replaying
    it carries both rotor state and float32 elapsed clock without telemetry.
    """
    from workflows.control_seam_v23 import ControlKernel
    from workflows.actuator_replay_v28 import Float32PWMActuatorState
    from workflows.feedback_v28 import FeedbackPolicy,validate_decision
    x=np.asarray(initial_state,dtype=float);history=np.asarray(issued_control_history,dtype=float);drive=np.asarray(pulses,dtype=float)
    if (x.shape!=(11,) or not valid_predictions(x[None])[0]
            or history.ndim!=2 or history.shape[1]!=4 or len(history)%2
            or drive.ndim!=2 or drive.shape[1]!=4 or not len(drive)
            or not np.isfinite(history).all() or np.any(np.abs(history)>.95) or not np.isfinite(drive).all()):
        raise ValueError('identification_policy_history')
    kernel=ControlKernel(configuration);policy=FeedbackPolicy(configuration)
    estimator=Float32PWMActuatorState(kernel.env._num_thrusters,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    for command in history:estimator.advance_pwm(kernel.command(command,pre_tam=True)['pwm'])
    origin_clock=estimator.elapsed_time;predictions=[];commands=[];failure=None
    scale=np.r_[[context.mass]*3,context.inertia]
    for control,external in enumerate(drive):
        if deadline is not None and time.monotonic()>=deadline:raise TimeoutError('identification_prediction_budget')
        try:
            decision=policy.decide(x,external)
            if not validate_decision(decision,x,external,configuration):raise ValueError('policy_allocation_rejected')
            command=np.asarray(decision['command_4']);commands.append(command)
            pwm=kernel.command(command,pre_tam=True)['pwm']
            for substep in range(2):
                speed=estimator.advance_pwm(pwm)
                wrench=kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed)
                following=np.asarray(predictor(x[None],(wrench/scale)[None],context))
                if following.shape!=(1,11) or not valid_predictions(following)[0]:raise ValueError('policy_prediction_invalid')
                x=following[0];predictions.append(x.copy())
        except (ValueError,FloatingPointError) as exc:
            failure={'control':control,'completed_physics_ticks':len(predictions),'exception':f'{type(exc).__name__}:{exc}'};break
    return {'complete':failure is None,'failure':failure,'predictions':np.asarray(predictions).reshape(-1,11),
        'commands':np.asarray(commands).reshape(-1,4),'origin_actuator_time_s':origin_clock,
        'future_inputs':'generated_from_own_predicted_state_and_fixed_external_drive'}
