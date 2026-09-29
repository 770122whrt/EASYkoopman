"""Local bounded fallback candidate with explicit demand and physical rejection.

The static map is not a hull model or a stability certificate. A proposal never
issues a command or consumes startup permission: the future execution arbiter
must authenticate reset/history and enforce the once-only startup transition.
"""
from dataclasses import dataclass, replace
import numbers
import time

import numpy as np

from koopman.bounded_mpc_v44 import SupportDomain, COMMAND_ATOL, owned
from koopman.control_objective_v44 import control_mask, checked_reference
from koopman.command_prediction_v37 import validate_context
from koopman.physical_terms_v26 import validate_states
from koopman.projected_edmd_v24 import rotation
from koopman.prepared_allocation_v42 import PreparedDirectAllocation
from koopman.prepared_projected_v40 import _context_key
from koopman.prepared_commands_v45 import check_deadline, validate_deadline
from workflows.feedback_inverse_v28 import deadzone_distance, MINIMUM_DEADZONE_DISTANCE
from workflows.workpoint_v27 import ACCELERATION_TOLERANCE


@dataclass(frozen=True)
class FeedbackConfig:
    height_kp: float = 1.
    vertical_kd: float = 2.
    attitude_kp: float = 9.
    angular_kd: float = 6.
    vertical_acceleration_limit: float = 1.
    angular_acceleration_limit: float = 16.
    slew: float = .01
    timeout_ms: float = 10.
    iterations: int = 4

    def __post_init__(self):
        if type(self.iterations) is not int or not 1<=self.iterations<=8:
            raise ValueError('feedback_iteration_limit')
        values=[v for k,v in vars(self).items() if k!='iterations']
        if (any(isinstance(v,bool) or not isinstance(v,numbers.Real) for v in values)
                or not np.isfinite(values).all() or min(values)<=0
                or self.slew>.1 or self.timeout_ms>10000):
            raise ValueError('feedback_parameters_invalid')


def feedback_demand(state,reference,configuration,context,config):
    """Nominal gravity/restoring compensation plus bounded depth/attitude PD.

Heave is chosen for world vertical acceleration using the actual current tilt.
Unactuated lateral motion, drag and gyro are not claimed to be cancelled.
"""
    validate_context(configuration,context)
    x=validate_states(np.asarray(state,dtype=float)[None])[0]
    ref=checked_reference(reference);mask=control_mask(configuration)
    if not isinstance(config,FeedbackConfig):raise ValueError('feedback_parameters_invalid')
    q=x[1:5]/np.linalg.norm(x[1:5]);up=rotation(q)[2]
    if up[2]<.5-1e-12 or not 3.5<=ref[0]<=7.5 or rotation(ref[1:])[2,2]<.5-1e-12:
        raise ValueError('feedback_pose_limit')
    if mask[2]:
        # conjugate(current)*desired: shortest desired rotation in current body.
        qr=ref[1:]
        error=np.r_[q[0]*qr[0]+q[1:]@qr[1:], q[0]*qr[1:]-qr[0]*q[1:]-np.cross(q[1:],qr[1:])]
        error/=np.linalg.norm(error)
        nonzero=error[np.flatnonzero(error)]
        if nonzero[0]<0:error=-error
        angular=2*config.attitude_kp*error[1:]-config.angular_kd*x[8:]
    else:
        error=np.cross(up,rotation(ref[1:])[2])
        angular=-config.attitude_kp*error-config.angular_kd*x[8:]
    angular=np.clip(angular,-config.angular_acceleration_limit,config.angular_acceleration_limit)*mask[:3]
    vertical=float(np.clip(config.height_kp*(ref[0]-x[0])-config.vertical_kd*(up@x[5:8]),
                           -config.vertical_acceleration_limit,config.vertical_acceleration_limit))
    buoyancy=context.rho*context.volume*context.gravity
    target=np.zeros(6)
    target[2]=(context.mass*vertical+context.mass*context.gravity-buoyancy)/up[2]
    unmasked=-np.cross(context.cob,buoyancy*up)+context.inertia*angular
    target[3:]=unmasked*mask[:3]
    return dict(target_wrench=target,desired_vertical_acceleration=vertical,
                desired_angular_acceleration=angular,unallocated_torque=unmasked-target[3:],
                feedback_model='nominal_gravity_restoring_PD_no_drag_gyro_cancellation')


class PreparedSteadyMap:
    """Evaluate the original direct allocation, float32 PWM curve and wrench."""
    def __init__(self,configuration,context):
        validate_context(configuration,context)
        self.configuration=configuration;self.context_key=_context_key(context)
        self.allocator=PreparedDirectAllocation(configuration)
        self.mask=owned(control_mask(configuration))
        self.scale=owned(np.r_[[context.mass]*3,context.inertia])

    def evaluate(self,command):
        u=np.array(command,dtype=float,copy=True)
        if u.shape!=(4,) or not np.isfinite(u).all() or np.any(np.abs(u)>.95):
            raise ValueError('feedback_command_invalid')
        result=self.allocator.command(u,pre_tam=True)
        pwm=result['pwm'];speed=np.zeros_like(pwm)
        threshold=np.float32(.02);positive=pwm>=threshold;negative=pwm<=-threshold
        p=pwm[positive];n=pwm[negative]
        speed[positive]=(np.float32(-139)*(p*p)+np.float32(500)*p)+np.float32(8.28)
        speed[negative]=(np.float32(161)*(n*n)+np.float32(517.86)*n)-np.float32(5.72)
        force=self.allocator.rotor_constant*np.abs(speed)*speed
        wrench=(self.allocator.wrench_matrix@force).astype(float)
        return dict(result,speed=speed,wrench=wrench)

    def inspect(self,command,target,lower,upper):
        u=np.asarray(command,dtype=float);sent=self.evaluate(u)
        error=(sent['wrench']-target)/self.scale
        margin=float(1-np.max(np.abs(sent['pwm_raw'])))
        distance=deadzone_distance(sent['pwm_raw'])
        bound=bool(np.all(u>=lower-COMMAND_ATOL) and np.all(u<=upper+COMMAND_ATOL)
                   and np.all(np.abs(u*(1-self.mask))<=COMMAND_ATOL))
        legal=bool(bound and margin>=.05 and distance>MINIMUM_DEADZONE_DISTANCE)
        return dict(command=u.copy(),target_wrench=np.array(target,copy=True),steady_wrench=sent['wrench'],
                    acceleration_error=error,pwm_raw=sent['pwm_raw'],pwm_headroom=margin,
                    minimum_deadzone_distance_pwm=distance,
                    physical_residual_accepted=bool(np.all(np.abs(error)<=ACCELERATION_TOLERANCE)),
                    command_constraints_accepted=legal)

    def inverse(self,target,previous,lower,upper,config,*,deadline):
        """Small bounded Newton search; infeasibility is retained, never relabelled."""
        validate_deadline(deadline);check_deadline(deadline)
        target=np.array(target,dtype=float,copy=True);previous=np.asarray(previous,dtype=float)
        lower=np.asarray(lower,dtype=float);upper=np.asarray(upper,dtype=float)
        if (target.shape!=(6,) or previous.shape!=(4,) or lower.shape!=(4,) or upper.shape!=(4,)
                or not all(np.isfinite(a).all() for a in (target,previous,lower,upper))
                or np.any(lower>upper) or np.any(lower<-.95) or np.any(upper>.95)):
            raise ValueError('feedback_inverse_bounds')
        active=np.flatnonzero(self.mask);u=np.clip(previous,lower,upper)*self.mask
        evaluations=0
        def evaluate(command):
            nonlocal evaluations
            check_deadline(deadline);evaluations+=1
            record=self.inspect(np.asarray(command,dtype=np.float32),target,lower,upper)
            check_deadline(deadline)
            ratios=record['acceleration_error']/ACCELERATION_TOLERANCE
            score=(float(np.max(np.abs(ratios))),float(ratios@ratios))
            if not record['command_constraints_accepted']:score=(float('inf'),float('inf'))
            return score,record
        best_score,best=evaluate(u);iterations=0
        for iteration in range(config.iterations):
            if best['command_constraints_accepted'] and best['physical_residual_accepted']:break
            iterations=iteration+1;columns=[]
            for axis in active:
                plus=u.copy();minus=u.copy()
                plus[axis]=min(upper[axis],u[axis]+.001);minus[axis]=max(lower[axis],u[axis]-.001)
                _,a=evaluate(plus);_,b=evaluate(minus);step=plus[axis]-minus[axis]
                columns.append((a['acceleration_error']-b['acceleration_error'])/ACCELERATION_TOLERANCE/step if step>0 else np.zeros(6))
            jac=np.stack(columns,axis=1)
            delta=np.linalg.lstsq(jac,-best['acceleration_error']/ACCELERATION_TOLERANCE,rcond=1e-8)[0]
            check_deadline(deadline);following=u.copy();improved=False
            for fraction in (1.,.5,.25):
                trial=u.copy();trial[active]+=fraction*delta;trial=np.clip(trial,lower,upper)*self.mask
                score,record=evaluate(trial)
                if score<best_score:
                    best_score,best=score,record;following=trial;improved=True
            if not improved:break
            u=following
        accepted=best['command_constraints_accepted'] and best['physical_residual_accepted']
        check_deadline(deadline)
        return dict(status='ready' if accepted else 'no_command',reason=None if accepted else 'inverse_infeasible',
                    command=owned(best['command'],np.float32) if accepted else None,
                    inspection=best,iterations=iterations,evaluations=evaluations)


class BoundedFeedback:
    """Pure proposal policy. Runtime startup/history authentication is separate."""
    def __init__(self,domain,context,*,config=FeedbackConfig(),allow_diagnostic=False):
        if not isinstance(domain,SupportDomain) or (not domain._verified_fit and not allow_diagnostic):
            raise ValueError('feedback_fit_provenance_required')
        validate_context(domain.configuration,context)
        if _context_key(context)!=domain.context_key or not isinstance(config,FeedbackConfig):
            raise ValueError('feedback_context_or_parameters')
        self.domain=domain;self.context=replace(context);self.config=config
        self.steady=PreparedSteadyMap(domain.configuration,context);self._startup=None
        self._binding=(domain.configuration,domain.context_key,domain.model_id,domain.identity)

    def _binding_matches(self,support_id=None):
        identity=self.domain.identity if support_id is None else support_id
        return (self._binding==(self.domain.configuration,self.domain.context_key,self.domain.model_id,identity)
                and self.steady.configuration==self.domain.configuration
                and self.steady.context_key==self.domain.context_key==_context_key(self.context))

    @staticmethod
    def _same_pose_values(a,b,atol):
        # Raw quaternion signs are representational, not a new reset/reference.
        qa=a[1:5]/np.linalg.norm(a[1:5]);qb=b[1:5]/np.linalg.norm(b[1:5])
        return (np.allclose(np.r_[a[:1],a[5:]],np.r_[b[:1],b[5:]],rtol=0,atol=atol)
                and min(np.linalg.norm(qa-qb),np.linalg.norm(qa+qb))<=atol)

    def prepare_startup(self,state,reference):
        """Known-source inverse before READY, never in a low-level control tick."""
        from workflows.feedback_inverse_v31 import solve_feasible_control
        started=time.perf_counter();x=np.array(state,dtype=float,copy=True);ref=checked_reference(reference)
        if not self._binding_matches():raise ValueError('policy_binding_changed')
        if (x.shape!=(11,) or self.domain.check_states(x[None]) or np.max(np.abs(x[5:]))>1e-6
                or np.linalg.norm(x[2:5])>1e-6 or abs(x[0]-5.5)>1e-6):
            raise ValueError('feedback_startup_reset_state')
        demand=feedback_demand(x,ref,self.domain.configuration,self.context,self.config)
        source=solve_feasible_control(self.domain.configuration,demand['target_wrench'])
        u=np.asarray(source['command_4'],dtype=np.float32)
        inspection=self.steady.inspect(u,demand['target_wrench'],self.domain.command_lower,self.domain.command_upper)
        if not (inspection['physical_residual_accepted'] and inspection['command_constraints_accepted']):
            return dict(status='rejected',reason='startup_inverse_infeasible',command=None,inspection=inspection)
        self._startup=dict(state=owned(x),reference=owned(ref),command=owned(u,np.float32),
                           parameters=vars(self.config).copy(),context_key=self.domain.context_key)
        return dict(status='prepared',command=owned(u,np.float32),inspection=inspection,
                    prepare_ms=1000*(time.perf_counter()-started),actual_history_advanced=False,runtime_eligible=False)

    def decide(self,state,reference,*,previous):
        started=time.perf_counter();deadline=started+self.config.timeout_ms/1000
        result=dict(status='no_command',command=None,reason=None,startup_exception_requested=previous is None,
            runtime_eligible=False,actual_history_advanced=False,configuration=self.domain.configuration,
            context_key=self.domain.context_key,model_id=self.domain.model_id,support_id=self.domain.identity,
            demand=None,inspection=None,iterations=0,evaluations=0)
        def finish(reason):
            if reason is None and time.perf_counter()>=deadline:reason='timeout'
            if reason is not None:result.update(status='no_command',command=None)
            result.update(reason=reason,elapsed_ms=1000*(time.perf_counter()-started))
            return result
        try:
            check_deadline(deadline)
            if not self._binding_matches(result['support_id']):return finish('policy_binding_changed')
            x=np.array(state,dtype=float,copy=True);ref=checked_reference(reference)
            if x.shape!=(11,):return finish('state_invalid')
            rejected=self.domain.check_states(x[None])
            if rejected:return finish('state_'+rejected['reason'])
            demand=feedback_demand(x,ref,self.domain.configuration,self.context,self.config)
            result['demand']=demand;check_deadline(deadline)
            if previous is None:
                seed=self._startup
                if (seed is None or seed['context_key']!=self.domain.context_key
                        or seed['parameters']!=vars(self.config)
                        or not self._same_pose_values(x,seed['state'],1e-6)
                        or not self._same_pose_values(ref,seed['reference'],1e-12)):
                    return finish('startup_not_prepared_or_binding_mismatch')
                inspection=self.steady.inspect(seed['command'],demand['target_wrench'],self.domain.command_lower,self.domain.command_upper)
                result['inspection']=inspection;result['evaluations']=1;check_deadline(deadline)
                if not (inspection['physical_residual_accepted'] and inspection['command_constraints_accepted']):
                    return finish('startup_revalidation_failed')
                result.update(status='ready',command=owned(seed['command'],np.float32))
                return finish(None)
            old=np.asarray(previous,dtype=float)
            if (old.shape!=(4,) or not np.isfinite(old).all() or np.any(np.abs(old)>.95)
                    or np.any(np.abs(old*(1-self.steady.mask))>COMMAND_ATOL)):
                return finish('previous_command_invalid')
            lower=np.maximum(self.domain.command_lower,old-self.config.slew)
            upper=np.minimum(self.domain.command_upper,old+self.config.slew)
            inverse=self.steady.inverse(demand['target_wrench'],old,lower,upper,self.config,deadline=deadline)
            result.update(inverse)
            if inverse['status']!='ready':return finish(inverse['reason'])
            # Independent final re-evaluation, including float32 command rounding.
            inspection=self.steady.inspect(result['command'],demand['target_wrench'],lower,upper)
            result['inspection']=inspection;result['evaluations']+=1;check_deadline(deadline)
            if not (inspection['physical_residual_accepted'] and inspection['command_constraints_accepted']):
                return finish('final_physical_check_failed')
            return finish(None)
        except TimeoutError:return finish('timeout')
        except (ValueError,FloatingPointError,np.linalg.LinAlgError) as exc:
            return finish('invalid_or_numerical:'+str(exc))
