"""Static inverse plus explicit bounded tracking; never a live command issuer.

The full static demand keeps the v46 residual limits. Rate/support constraints
apply to the actual proposal, whose residual is reported even when nonzero.
This distinction is not a stability certificate or a change to v46 evidence.
"""
import time

import numpy as np

from koopman.bounded_feedback_v46 import (BoundedFeedback, FeedbackConfig,
    PreparedSteadyMap, feedback_demand)
from koopman.bounded_mpc_v44 import COMMAND_ATOL, owned
from koopman.control_objective_v44 import checked_reference
from koopman.prepared_commands_v45 import check_deadline, validate_deadline
from workflows.workpoint_v27 import _inverse_force, ACCELERATION_TOLERANCE


SEED_FACTORS = (1., 1.0002, .9998)
LIMIT_FRACTIONS = (1., .999, .99, .9, .5)


class PreparedTrackingMap(PreparedSteadyMap):
    """Prepare geometry before READY; retain the exact source forward map."""
    def __init__(self, configuration, context):
        super().__init__(configuration, context)
        active = np.flatnonzero(self.mask)
        allocation = np.stack([self.allocator.command(np.eye(4)[j], pre_tam=True)['pwm_raw']
                               for j in active], axis=1)
        self.active = owned(active, np.int64)
        self.force_inverse = owned(np.linalg.pinv(self.allocator.wrench_matrix.astype(float)))
        self.allocation_inverse = owned(np.linalg.pinv(allocation.astype(float)))

    def static_inverse(self, target, previous, config, *, deadline):
        validate_deadline(deadline); check_deadline(deadline)
        target = np.array(target, dtype=float, copy=True)
        old = np.asarray(previous, dtype=float)
        if (target.shape != (6,) or old.shape != (4,) or not np.isfinite(target).all()
                or not np.isfinite(old).all() or not isinstance(config, FeedbackConfig)):
            raise ValueError('static_inverse_input')
        lower, upper = -.95*self.mask, .95*self.mask
        best = None; best_score = None; evaluations = 0

        def inspect(u):
            nonlocal best, best_score, evaluations
            check_deadline(deadline)
            record = self.inspect(np.asarray(u, dtype=np.float32), target, lower, upper)
            evaluations += 1; check_deadline(deadline)
            ratio = record['acceleration_error']/ACCELERATION_TOLERANCE
            score = (not record['command_constraints_accepted'], float(np.max(np.abs(ratio))), float(ratio@ratio))
            if best_score is None or score < best_score:
                best_score, best = score, record
            return record['physical_residual_accepted'] and record['command_constraints_accepted']

        accepted = inspect(np.clip(old, lower, upper))
        if not accepted:
            # This is a numerical seed, not an alternative actuator model.
            force = self.force_inverse@target
            pwm = [_inverse_force(f, self.allocator.rotor_constant) for f in force]
            check_deadline(deadline)
            seed = np.zeros(4); seed[self.active] = self.allocation_inverse@pwm
            for fraction in SEED_FACTORS:
                if inspect(np.clip(seed*fraction, lower, upper)):
                    accepted = True; break
        if accepted:
            return dict(status='ready', reason=None, command=owned(best['command'], np.float32),
                        inspection=best, iterations=0, evaluations=evaluations)
        # Fixed four-iteration refinement by default, now outside the slew box.
        result = self.inverse(target, best['command'], lower, upper, config, deadline=deadline)
        result['evaluations'] += evaluations
        if result['status'] != 'ready':result['reason'] = 'static_inverse_not_found'
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
    if not (static['physical_residual_accepted'] and static['command_constraints_accepted']):
        return reject('static_inverse_revalidation_failed')
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
        if fraction != 1:result['limitations'].append('deadzone_backoff')
        result.update(status='ready', command=owned(u, np.float32), inspection=record,
            alpha=alpha*fraction, zero_progress=bool(np.max(np.abs(u.astype(float)-old)) <= COMMAND_ATOL),
            tracking_status='target_attained' if record['physical_residual_accepted'] else 'tracking_limited')
        return result
    return reject('no_admissible_limited_command')


class TrackingFeedback(BoundedFeedback):
    """Pure fallback proposal with a separately qualified full-demand inverse."""
    def __init__(self, domain, context, *, config=FeedbackConfig(), allow_diagnostic=False):
        super().__init__(domain, context, config=config, allow_diagnostic=allow_diagnostic)
        self.steady = PreparedTrackingMap(domain.configuration, context)

    def decide(self, state, reference, *, previous):
        started = time.perf_counter(); deadline = started+self.config.timeout_ms/1000
        if previous is None:
            # Uses only the pre-READY seed and retains every reset/reference check.
            result = super().decide(state, reference, previous=None)
            if result['status'] == 'ready':
                result.update(requested_wrench=result['demand']['target_wrench'].copy(),
                    static_command=owned(result['command'], np.float32), static_inspection=result['inspection'],
                    static_reference_in_support=True, target_rewritten=False, tracking_status='target_attained',
                    alpha=1., limitations=['once_only_startup_permission_required'], zero_progress=False)
            if time.perf_counter() >= deadline:
                result.update(status='no_command', reason='timeout', command=None, tracking_status='no_command')
            result['elapsed_ms'] = 1000*(time.perf_counter()-started)
            return result
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
