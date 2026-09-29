"""Bounded best-found static tracking; residual failure is explicit, never success.

An opt-in strategy revision for actuator deadzones. It changes neither requested
wrenches nor acceptance tolerances, physical limits, deadlines or prefix history.
"""
from dataclasses import replace
import time
import numpy as np
from koopman.cached_checks_v53 import CachedTrackingMap, CachedTrackingFeedback
from koopman.bounded_feedback_v46 import FeedbackConfig, feedback_demand
from koopman.bounded_feedback_v47 import LIMIT_FRACTIONS
from koopman.bounded_mpc_v44 import COMMAND_ATOL, SupportDomain, owned
from koopman.control_objective_v44 import checked_reference
from koopman.prepared_commands_v45 import check_deadline, validate_deadline
from koopman.prepared_projected_v40 import _context_key
from workflows.workpoint_v27 import ACCELERATION_TOLERANCE


def _score(record):
    ratio = np.asarray(record['acceleration_error'], dtype=float)/ACCELERATION_TOLERANCE
    if ratio.shape != (6,) or not np.isfinite(ratio).all():
        raise ValueError('inexact_nonfinite_residual')
    return float(np.max(np.abs(ratio))), float(ratio@ratio)


class InexactTrackingMap(CachedTrackingMap):
    def static_inverse(self, target, previous, config, *, deadline):
        result = super().static_inverse(target, previous, config, deadline=deadline)
        if result['status'] == 'ready' or result.get('reason') != 'static_inverse_not_found':
            return result
        candidate = result.get('inspection') or {}
        if not candidate.get('command_constraints_accepted') or 'command' not in candidate:
            return result
        check_deadline(deadline)
        checked = self.inspect(candidate['command'], target, -.95*self.mask, .95*self.mask)
        if not checked['command_constraints_accepted']:return result
        past = self.inspect(previous, target, -.95*self.mask, .95*self.mask)
        if past['command_constraints_accepted'] and _score(past) < _score(checked):checked = past
        _score(checked); check_deadline(deadline)
        result = dict(result)
        result.update(status='ready', reason=None, command=owned(checked['command'], np.float32),
            inspection=checked, evaluations=result['evaluations']+2,
            static_target_status='target_attained' if checked['physical_residual_accepted']
                else 'best_found_static_residual_unmet')
        return result


def limit_tracking_command(steady, target, full, previous, lower, upper, slew, *, deadline):
    """One common interpolation factor; each issued candidate is re-evaluated.

    A support-boundary hold is explicit zero progress. An execution layer must
    still bound persistent tracking error; no success/stability is inferred.
    """
    validate_deadline(deadline); check_deadline(deadline)
    target = np.array(target, dtype=float, copy=True)
    full, old, lower, upper = [np.array(a, dtype=float, copy=True) for a in (full, previous, lower, upper)]
    result = dict(status='no_command', reason=None, command=None, requested_wrench=target,
                  target_rewritten=False, static_command=None, static_inspection=None, inspection=None,
                  tracking_status='no_command', alpha=None, limitations=[], zero_progress=False,
                  static_reference_in_support=False, evaluations=0)
    def reject(reason):
        result['reason'] = reason
        return result
    if (target.shape != (6,) or any(a.shape != (4,) for a in (full, old, lower, upper))
            or not all(np.isfinite(a).all() for a in (target, full, old, lower, upper))
            or not np.isfinite(slew) or not 0 < slew <= .1 or np.any(lower > upper)
            or np.any(lower < -.95) or np.any(upper > .95)):
        return reject('tracking_limiter_input')
    if np.any(np.abs(full) > .95) or np.any(np.abs(old) > .95):
        return reject('tracking_limiter_command_bounds')
    static = steady.inspect(full, target, -.95*steady.mask, .95*steady.mask)
    result.update(static_inspection=static, static_command=owned(full, np.float32), evaluations=1)
    check_deadline(deadline)
    if not static['command_constraints_accepted']:
        return reject('static_inverse_revalidation_failed')
    if not static['physical_residual_accepted']:
        result['limitations'].append('static_residual_unmet')
    past = steady.inspect(old, target, lower, upper); result['evaluations'] += 1
    check_deadline(deadline)
    if not past['command_constraints_accepted']:
        return reject('previous_command_not_admissible')
    result['static_reference_in_support'] = bool(np.all(full >= lower-COMMAND_ATOL)
                                                 and np.all(full <= upper+COMMAND_ATOL))
    delta = full-old
    moving = np.abs(delta) > 0
    slew_alpha = min(1., float(np.min(slew/np.abs(delta[moving])))) if moving.any() else 1.
    support_alpha = 1.
    for axis in np.flatnonzero(moving):
        available = (upper[axis]-old[axis]) if delta[axis] > 0 else (lower[axis]-old[axis])
        support_alpha = min(support_alpha, max(0., float(available/delta[axis])))
    alpha = min(slew_alpha, support_alpha)
    if slew_alpha < 1:result['limitations'].append('slew')
    if support_alpha < 1:result['limitations'].append('support')
    actual_lower = np.maximum(lower, old-slew)
    actual_upper = np.minimum(upper, old+slew)
    for fraction in LIMIT_FRACTIONS:
        check_deadline(deadline)
        u = np.asarray(old+(alpha*fraction)*delta, dtype=np.float32)
        record = steady.inspect(u, target, actual_lower, actual_upper)
        result['evaluations'] += 1; check_deadline(deadline)
        if not record['command_constraints_accepted']:
            continue
        chosen_alpha = alpha*fraction
        if not static['physical_residual_accepted'] and _score(past) < _score(record):
            u = np.asarray(old, dtype=np.float32)
            record = steady.inspect(u, target, actual_lower, actual_upper)
            result['evaluations'] += 1; check_deadline(deadline)
            if not record['command_constraints_accepted']:continue
            chosen_alpha = 0.
            result['limitations'].append('hold_has_lower_static_residual')
        if fraction != 1:result['limitations'].append('deadzone_backoff')
        result.update(status='ready', command=owned(u, np.float32), inspection=record,
            alpha=chosen_alpha, zero_progress=bool(np.max(np.abs(u.astype(float)-old)) <= COMMAND_ATOL),
            tracking_status='target_attained' if record['physical_residual_accepted'] else 'tracking_limited')
        return result
    return reject('no_admissible_limited_command')

class InexactTrackingFeedback(CachedTrackingFeedback):
    def __init__(self, domain, context, **kwargs):
        super().__init__(domain, context, **kwargs)
        self.steady = InexactTrackingMap(domain.configuration, context)
        self.audit = []
        self.physics_index = lambda: None

    def decide(self, state, reference, *, previous):
        if len(self.audit) >= 128:raise ValueError('inexact_tracking_audit_budget')
        result = self._decide(state, reference, previous=previous)
        from copy import deepcopy
        keys = ('status','reason','command','requested_wrench','static_command','static_inspection',
                'inspection','tracking_status','target_rewritten','limitations','zero_progress','elapsed_ms')
        self.audit.append(dict(physics_index=self.physics_index(),state=owned(state),
            reference=owned(reference),previous=None if previous is None else owned(previous),
            result=deepcopy({k:result.get(k) for k in keys})))
        return result

    def _decide(self, state, reference, *, previous):
        started = time.perf_counter(); deadline = started+self.config.timeout_ms/1000
        if previous is None:
            return super().decide(state, reference, previous=None)
        result = dict(status='no_command', command=None, reason=None, startup_exception_requested=False,
            runtime_eligible=False, actual_history_advanced=False, configuration=self.domain.configuration,
            context_key=self.domain.context_key, model_id=self.domain.model_id, support_id=self.domain.identity,
            demand=None, inspection=None, static_inspection=None, requested_wrench=None,
            tracking_status='no_command', target_rewritten=False, iterations=0, evaluations=0)
        def finish(reason):
            if reason is None and time.perf_counter() >= deadline:reason = 'timeout'
            if reason is not None:result.update(status='no_command', command=None, tracking_status='no_command')
            result.update(reason=reason, elapsed_ms=1000*(time.perf_counter()-started))
            return result
        try:
            check_deadline(deadline)
            if not self._binding_matches(result['support_id']):return finish('policy_binding_changed')
            x = np.array(state, dtype=float, copy=True); ref = checked_reference(reference)
            if x.shape != (11,):return finish('state_invalid')
            rejected = self.domain.check_states(x[None])
            if rejected:return finish('state_'+rejected['reason'])
            demand = feedback_demand(x, ref, self.domain.configuration, self.context, self.config)
            result.update(demand=demand, requested_wrench=demand['target_wrench'].copy())
            old = np.asarray(previous, dtype=float)
            if (old.shape != (4,) or not np.isfinite(old).all() or np.any(np.abs(old) > .95)
                    or np.any(np.abs(old*(1-self.steady.mask)) > COMMAND_ATOL)):
                return finish('previous_command_invalid')
            inverse = self.steady.static_inverse(demand['target_wrench'], old, self.config, deadline=deadline)
            result.update(static_inspection=inverse['inspection'], iterations=inverse['iterations'],
                          evaluations=inverse['evaluations'])
            if inverse['status'] != 'ready':return finish(inverse['reason'])
            limited = limit_tracking_command(self.steady, demand['target_wrench'], inverse['command'], old,
                self.domain.command_lower, self.domain.command_upper, self.config.slew, deadline=deadline)
            limited['evaluations'] += inverse['evaluations']
            result.update(limited)
            return finish(limited['reason'])
        except TimeoutError:return finish('timeout')
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            return finish('invalid_or_numerical:'+str(exc))

class InexactRecoveryBaseline:
    def __init__(self,domain,context,*,config=FeedbackConfig(),allow_diagnostic=False):
        if (not isinstance(domain,SupportDomain) or (not domain._verified_fit and not allow_diagnostic)
                or _context_key(context)!=domain.context_key or not isinstance(config,FeedbackConfig)):
            raise ValueError('recovery_setup_binding')
        self.domain=domain;self.context=replace(context);self.config=config
        self.steady=InexactTrackingMap(domain.configuration,self.context)

    def build(self,state,reference,previous,prefix,*,horizon,deadline):
        result=dict(status='no_baseline',reason=None,commands=None,tracking=[],requested_wrench=None,
            static_command=None,target_rewritten=False,future_feedback_assumed=False,actual_history_advanced=False)
        def reject(reason):result.update(status='no_baseline',reason=reason,commands=None);return result
        try:
            check_deadline(deadline)
            old=np.array(previous,dtype=float,copy=True);p=np.array(prefix,dtype=np.float32,copy=True)
            x=np.array(state,dtype=float,copy=True);ref=checked_reference(reference)
            if (type(horizon) is not int or not 2<=horizon<=128 or p.ndim!=2 or p.shape[1]!=4
                    or not 1<=len(p)<horizon or old.shape!=(4,) or not np.isfinite(old).all()
                    or not np.isfinite(p).all() or x.shape!=(11,)):
                return reject('recovery_input')
            if self.domain.check_states(x[None]):return reject('recovery_initial_state')
            target=feedback_demand(x,ref,self.domain.configuration,self.context,self.config)['target_wrench']
            result['requested_wrench']=owned(target)
            # Prefix commands have already been chosen by the parent. Never clip
            # or replace them silently to make a prediction feasible.
            commands=[];prior=old
            for u in np.vstack([old,p]):
                check_deadline(deadline)
                record=self.steady.inspect(u,target,self.domain.command_lower,self.domain.command_upper)
                if not record['command_constraints_accepted']:return reject('recovery_prefix_constraints')
                if np.any(np.abs(u-prior)>self.config.slew+COMMAND_ATOL):return reject('recovery_prefix_slew')
                prior=u
            commands.extend(p)
            inverse=self.steady.static_inverse(target,prior,self.config,
                deadline=min(deadline,time.perf_counter()+self.config.timeout_ms/1000))
            if inverse['status']!='ready':return reject('recovery_'+inverse['reason'])
            full=inverse['command'];result['static_command']=owned(full,np.float32)
            for _ in range(horizon-len(p)):
                check_deadline(deadline)
                limited=limit_tracking_command(self.steady,target,full,prior,self.domain.command_lower,
                    self.domain.command_upper,self.config.slew,deadline=deadline)
                if limited['status']!='ready':return reject('recovery_'+limited['reason'])
                prior=limited['command'];commands.append(prior)
                result['tracking'].append(dict(status=limited['tracking_status'],alpha=limited['alpha'],
                    zero_progress=limited['zero_progress'],limitations=limited['limitations'],
                    acceleration_error=owned(limited['inspection']['acceleration_error'])))
            check_deadline(deadline)
            result.update(status='ready',commands=owned(commands,np.float32));return result
        except TimeoutError:return reject('timeout')
        except (ValueError,TypeError,FloatingPointError,np.linalg.LinAlgError) as exc:
            return reject('recovery_invalid:'+str(exc))

def portable_inexact_factory(spec):
    from koopman.compiled_recovery_v64 import portable_compiled_factory
    solver = portable_compiled_factory(spec)
    old = solver.baseline
    solver.baseline = InexactRecoveryBaseline(old.domain, old.context, config=old.config)
    return solver


def replace_feedback_before_first_dispatch(session):
    runtime = session.runtime
    if runtime.ledger.physics_index != 0 or runtime.stats['dispatches'] != 0:
        raise ValueError('inexact_feedback_requires_fresh_reset')
    old = runtime.feedback
    new = InexactTrackingFeedback(old.domain, old.context, config=old.config)
    new.physics_index = lambda: runtime.ledger.physics_index
    new._startup = old._startup
    runtime.feedback = new
