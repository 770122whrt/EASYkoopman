"""Current bounded feedback with exact caching and auditable residuals.

The static inverse is a proposal only: it cannot issue commands, learn online,
or certify hull stability. Initialization and ongoing decisions retain their
separate reset, support, deadline and physical residual checks.
"""

from collections import OrderedDict

from dataclasses import dataclass, replace
import numbers
import time
import numpy as np
from koopman.support_domain import SupportDomain, COMMAND_ATOL, owned
from koopman.control_objective import control_mask, checked_reference
from koopman.command_context import validate_context
from koopman.physical_terms import validate_states
from koopman.physics_context import rotation
from koopman.allocation import PreparedDirectAllocation
from koopman.prepared_physics import _context_key
from koopman.command_plan import check_deadline, validate_deadline
from workflows.feedback_inverse import deadzone_distance, MINIMUM_DEADZONE_DISTANCE
from workflows.mechanics import ACCELERATION_TOLERANCE

from workflows.mechanics import _inverse_force

SEED_FACTORS = (1., 1.0002, .9998)
LIMIT_FRACTIONS = (1., .999, .99, .9, .5)

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

def _score(record):
    ratio = np.asarray(record['acceleration_error'], dtype=float)/ACCELERATION_TOLERANCE
    if ratio.shape != (6,) or not np.isfinite(ratio).all():
        raise ValueError('inexact_nonfinite_residual')
    return float(np.max(np.abs(ratio))), float(ratio@ratio)

class InexactTrackingMap:
    """Exact cached steady map with bounded inverse and explicit unmet residuals."""

    def __init__(self, configuration, context, *, cache_limit=128):
        if type(cache_limit) is not int or not 1 <= cache_limit <= 512:
            raise ValueError('map_cache_limit')
        validate_context(configuration, context)
        self.configuration = configuration
        self.context_key = _context_key(context)
        self.allocator = PreparedDirectAllocation(configuration)
        self.mask = owned(control_mask(configuration))
        self.scale = owned(np.r_[[context.mass] * 3, context.inertia])
        active = np.flatnonzero(self.mask)
        allocation = np.stack([self.allocator.command(np.eye(4)[j], pre_tam=True)['pwm_raw'] for j in active], axis=1)
        self.active = owned(active, np.int64)
        self.force_inverse = owned(np.linalg.pinv(self.allocator.wrench_matrix.astype(float)))
        self.allocation_inverse = owned(np.linalg.pinv(allocation.astype(float)))
        self._cache_limit = cache_limit
        self._cache = OrderedDict()
        self._cache_binding = self._binding_token()

    def _evaluate_uncached(self, command):
        u = np.array(command, dtype=float, copy=True)
        if u.shape != (4,) or not np.isfinite(u).all() or np.any(np.abs(u) > 0.95):
            raise ValueError('feedback_command_invalid')
        result = self.allocator.command(u, pre_tam=True)
        pwm = result['pwm']
        speed = np.zeros_like(pwm)
        threshold = np.float32(0.02)
        positive = pwm >= threshold
        negative = pwm <= -threshold
        p = pwm[positive]
        n = pwm[negative]
        speed[positive] = np.float32(-139) * (p * p) + np.float32(500) * p + np.float32(8.28)
        speed[negative] = np.float32(161) * (n * n) + np.float32(517.86) * n - np.float32(5.72)
        force = self.allocator.rotor_constant * np.abs(speed) * speed
        wrench = (self.allocator.wrench_matrix @ force).astype(float)
        return dict(result, speed=speed, wrench=wrench)

    def evaluate(self, command):
        if self._binding_token() != self._cache_binding:
            raise ValueError('map_cache_binding_changed')
        u = np.asarray(command, dtype=float)
        if u.shape != (4,) or not np.isfinite(u).all() or np.any(np.abs(u) > 0.95):
            raise ValueError('feedback_command_invalid')
        key = u.tobytes()
        if key not in self._cache:
            source = self._evaluate_uncached(u)
            self._cache[key] = {k: owned(v, v.dtype) if isinstance(v, np.ndarray) else v for k, v in source.items()}
            if len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)
        self._cache.move_to_end(key)
        return {k: v.copy() if isinstance(v, np.ndarray) else v for k, v in self._cache[key].items()}

    def _binding_token(self):
        a = self.allocator
        return (self.configuration, self.context_key, id(self.scale), id(self.mask), id(a), a.configuration, a.rotor_constant, id(a.wrench_matrix), id(a._mask), id(a._sign), id(a._weights), id(a._inverse), None if a._inverse is None else a._inverse._version)

    @property
    def cache_size(self):
        return len(self._cache)

    def inspect(self, command, target, lower, upper):
        u = np.asarray(command, dtype=float)
        sent = self.evaluate(u)
        error = (sent['wrench'] - target) / self.scale
        margin = float(1 - np.max(np.abs(sent['pwm_raw'])))
        distance = deadzone_distance(sent['pwm_raw'])
        bound = bool(np.all(u >= lower - COMMAND_ATOL) and np.all(u <= upper + COMMAND_ATOL) and np.all(np.abs(u * (1 - self.mask)) <= COMMAND_ATOL))
        legal = bool(bound and margin >= 0.05 and (distance > MINIMUM_DEADZONE_DISTANCE))
        return dict(command=u.copy(), target_wrench=np.array(target, copy=True), steady_wrench=sent['wrench'], acceleration_error=error, pwm_raw=sent['pwm_raw'], pwm_headroom=margin, minimum_deadzone_distance_pwm=distance, physical_residual_accepted=bool(np.all(np.abs(error) <= ACCELERATION_TOLERANCE)), command_constraints_accepted=legal)

    def inverse(self, target, previous, lower, upper, config, *, deadline):
        """Small bounded Newton search; infeasibility is retained, never relabelled."""
        validate_deadline(deadline)
        check_deadline(deadline)
        target = np.array(target, dtype=float, copy=True)
        previous = np.asarray(previous, dtype=float)
        lower = np.asarray(lower, dtype=float)
        upper = np.asarray(upper, dtype=float)
        if target.shape != (6,) or previous.shape != (4,) or lower.shape != (4,) or (upper.shape != (4,)) or (not all((np.isfinite(a).all() for a in (target, previous, lower, upper)))) or np.any(lower > upper) or np.any(lower < -0.95) or np.any(upper > 0.95):
            raise ValueError('feedback_inverse_bounds')
        active = np.flatnonzero(self.mask)
        u = np.clip(previous, lower, upper) * self.mask
        evaluations = 0

        def evaluate(command):
            nonlocal evaluations
            check_deadline(deadline)
            evaluations += 1
            record = self.inspect(np.asarray(command, dtype=np.float32), target, lower, upper)
            check_deadline(deadline)
            ratios = record['acceleration_error'] / ACCELERATION_TOLERANCE
            score = (float(np.max(np.abs(ratios))), float(ratios @ ratios))
            if not record['command_constraints_accepted']:
                score = (float('inf'), float('inf'))
            return (score, record)
        best_score, best = evaluate(u)
        iterations = 0
        for iteration in range(config.iterations):
            if best['command_constraints_accepted'] and best['physical_residual_accepted']:
                break
            iterations = iteration + 1
            columns = []
            for axis in active:
                plus = u.copy()
                minus = u.copy()
                plus[axis] = min(upper[axis], u[axis] + 0.001)
                minus[axis] = max(lower[axis], u[axis] - 0.001)
                _, a = evaluate(plus)
                _, b = evaluate(minus)
                step = plus[axis] - minus[axis]
                columns.append((a['acceleration_error'] - b['acceleration_error']) / ACCELERATION_TOLERANCE / step if step > 0 else np.zeros(6))
            jac = np.stack(columns, axis=1)
            delta = np.linalg.lstsq(jac, -best['acceleration_error'] / ACCELERATION_TOLERANCE, rcond=1e-08)[0]
            check_deadline(deadline)
            following = u.copy()
            improved = False
            for fraction in (1.0, 0.5, 0.25):
                trial = u.copy()
                trial[active] += fraction * delta
                trial = np.clip(trial, lower, upper) * self.mask
                score, record = evaluate(trial)
                if score < best_score:
                    best_score, best = (score, record)
                    following = trial
                    improved = True
            if not improved:
                break
            u = following
        accepted = best['command_constraints_accepted'] and best['physical_residual_accepted']
        check_deadline(deadline)
        return dict(status='ready' if accepted else 'no_command', reason=None if accepted else 'inverse_infeasible', command=owned(best['command'], np.float32) if accepted else None, inspection=best, iterations=iterations, evaluations=evaluations)

    def _static_inverse(self, target, previous, config, *, deadline):
        validate_deadline(deadline)
        check_deadline(deadline)
        target = np.array(target, dtype=float, copy=True)
        old = np.asarray(previous, dtype=float)
        if target.shape != (6,) or old.shape != (4,) or (not np.isfinite(target).all()) or (not np.isfinite(old).all()) or (not isinstance(config, FeedbackConfig)):
            raise ValueError('static_inverse_input')
        lower, upper = (-0.95 * self.mask, 0.95 * self.mask)
        best = None
        best_score = None
        evaluations = 0

        def inspect(u):
            nonlocal best, best_score, evaluations
            check_deadline(deadline)
            record = self.inspect(np.asarray(u, dtype=np.float32), target, lower, upper)
            evaluations += 1
            check_deadline(deadline)
            ratio = record['acceleration_error'] / ACCELERATION_TOLERANCE
            score = (not record['command_constraints_accepted'], float(np.max(np.abs(ratio))), float(ratio @ ratio))
            if best_score is None or score < best_score:
                best_score, best = (score, record)
            return record['physical_residual_accepted'] and record['command_constraints_accepted']
        accepted = inspect(np.clip(old, lower, upper))
        if not accepted:
            force = self.force_inverse @ target
            pwm = [_inverse_force(f, self.allocator.rotor_constant) for f in force]
            check_deadline(deadline)
            seed = np.zeros(4)
            seed[self.active] = self.allocation_inverse @ pwm
            for fraction in SEED_FACTORS:
                if inspect(np.clip(seed * fraction, lower, upper)):
                    accepted = True
                    break
        if accepted:
            return dict(status='ready', reason=None, command=owned(best['command'], np.float32), inspection=best, iterations=0, evaluations=evaluations)
        result = self.inverse(target, best['command'], lower, upper, config, deadline=deadline)
        result['evaluations'] += evaluations
        if result['status'] != 'ready':
            result['reason'] = 'static_inverse_not_found'
        return result

    def static_inverse(self, target, previous, config, *, deadline):
        result = self._static_inverse(target, previous, config, deadline=deadline)
        if result['status'] == 'ready' or result.get('reason') != 'static_inverse_not_found':
            return result
        candidate = result.get('inspection') or {}
        if not candidate.get('command_constraints_accepted') or 'command' not in candidate:
            return result
        check_deadline(deadline)
        checked = self.inspect(candidate['command'], target, -0.95 * self.mask, 0.95 * self.mask)
        if not checked['command_constraints_accepted']:
            return result
        past = self.inspect(previous, target, -0.95 * self.mask, 0.95 * self.mask)
        if past['command_constraints_accepted'] and _score(past) < _score(checked):
            checked = past
        _score(checked)
        check_deadline(deadline)
        result = dict(result)
        result.update(status='ready', reason=None, command=owned(checked['command'], np.float32), inspection=checked, evaluations=result['evaluations'] + 2, static_target_status='target_attained' if checked['physical_residual_accepted'] else 'best_found_static_residual_unmet')
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

class InexactTrackingFeedback:
    """One current fallback policy; history authentication belongs to execution."""

    def __init__(self, domain, context, *, config=FeedbackConfig(), allow_diagnostic=False):
        if not isinstance(domain, SupportDomain) or (not domain._verified_fit and (not allow_diagnostic)):
            raise ValueError('feedback_fit_provenance_required')
        validate_context(domain.configuration, context)
        if _context_key(context) != domain.context_key or not isinstance(config, FeedbackConfig):
            raise ValueError('feedback_context_or_parameters')
        self.domain = domain
        self.context = replace(context)
        self.config = config
        self.steady = InexactTrackingMap(domain.configuration, context)
        self._startup = None
        self._binding = (domain.configuration, domain.context_key, domain.model_id, domain.identity)
        self.audit = []
        self.physics_index = lambda: None

    def _binding_matches(self, support_id=None):
        identity = self.domain.identity if support_id is None else support_id
        return self._binding == (self.domain.configuration, self.domain.context_key, self.domain.model_id, identity) and self.steady.configuration == self.domain.configuration and (self.steady.context_key == self.domain.context_key == _context_key(self.context))

    @staticmethod
    def _same_pose_values(a, b, atol):
        qa = a[1:5] / np.linalg.norm(a[1:5])
        qb = b[1:5] / np.linalg.norm(b[1:5])
        return np.allclose(np.r_[a[:1], a[5:]], np.r_[b[:1], b[5:]], rtol=0, atol=atol) and min(np.linalg.norm(qa - qb), np.linalg.norm(qa + qb)) <= atol

    def prepare_startup(self, state, reference):
        """Known-source inverse before READY, never in a low-level control tick."""
        from workflows.feedback_inverse import solve_feasible_control
        started = time.perf_counter()
        x = np.array(state, dtype=float, copy=True)
        ref = checked_reference(reference)
        if not self._binding_matches():
            raise ValueError('policy_binding_changed')
        if x.shape != (11,) or self.domain.check_states(x[None]) or np.max(np.abs(x[5:])) > 1e-06 or (np.linalg.norm(x[2:5]) > 1e-06) or (abs(x[0] - 5.5) > 1e-06):
            raise ValueError('feedback_startup_reset_state')
        demand = feedback_demand(x, ref, self.domain.configuration, self.context, self.config)
        source = solve_feasible_control(self.domain.configuration, demand['target_wrench'])
        u = np.asarray(source['command_4'], dtype=np.float32)
        inspection = self.steady.inspect(u, demand['target_wrench'], self.domain.command_lower, self.domain.command_upper)
        if not (inspection['physical_residual_accepted'] and inspection['command_constraints_accepted']):
            return dict(status='rejected', reason='startup_inverse_infeasible', command=None, inspection=inspection)
        self._startup = dict(state=owned(x), reference=owned(ref), command=owned(u, np.float32), parameters=vars(self.config).copy(), context_key=self.domain.context_key)
        return dict(status='prepared', command=owned(u, np.float32), inspection=inspection, prepare_ms=1000 * (time.perf_counter() - started), actual_history_advanced=False, runtime_eligible=False)

    def _startup_decision(self, state, reference, *, previous):
        started = time.perf_counter()
        deadline = started + self.config.timeout_ms / 1000
        result = dict(status='no_command', command=None, reason=None, startup_exception_requested=previous is None, runtime_eligible=False, actual_history_advanced=False, configuration=self.domain.configuration, context_key=self.domain.context_key, model_id=self.domain.model_id, support_id=self.domain.identity, demand=None, inspection=None, iterations=0, evaluations=0)

        def finish(reason):
            if reason is None and time.perf_counter() >= deadline:
                reason = 'timeout'
            if reason is not None:
                result.update(status='no_command', command=None)
            result.update(reason=reason, elapsed_ms=1000 * (time.perf_counter() - started))
            return result
        try:
            check_deadline(deadline)
            if not self._binding_matches(result['support_id']):
                return finish('policy_binding_changed')
            x = np.array(state, dtype=float, copy=True)
            ref = checked_reference(reference)
            if x.shape != (11,):
                return finish('state_invalid')
            rejected = self.domain.check_states(x[None])
            if rejected:
                return finish('state_' + rejected['reason'])
            demand = feedback_demand(x, ref, self.domain.configuration, self.context, self.config)
            result['demand'] = demand
            check_deadline(deadline)
            seed = self._startup
            if seed is None or seed['context_key'] != self.domain.context_key or seed['parameters'] != vars(self.config) or (not self._same_pose_values(x, seed['state'], 1e-06)) or (not self._same_pose_values(ref, seed['reference'], 1e-12)):
                return finish('startup_not_prepared_or_binding_mismatch')
            inspection = self.steady.inspect(seed['command'], demand['target_wrench'], self.domain.command_lower, self.domain.command_upper)
            result['inspection'] = inspection
            result['evaluations'] = 1
            check_deadline(deadline)
            if not (inspection['physical_residual_accepted'] and inspection['command_constraints_accepted']):
                return finish('startup_revalidation_failed')
            result.update(status='ready', command=owned(seed['command'], np.float32))
            return finish(None)
        except TimeoutError:
            return finish('timeout')
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            return finish('invalid_or_numerical:' + str(exc))

    def _startup_tracking_decision(self, state, reference, *, previous):
        started = time.perf_counter()
        deadline = started + self.config.timeout_ms / 1000
        result = self._startup_decision(state, reference, previous=None)
        if result['status'] == 'ready':
            result.update(requested_wrench=result['demand']['target_wrench'].copy(), static_command=owned(result['command'], np.float32), static_inspection=result['inspection'], static_reference_in_support=True, target_rewritten=False, tracking_status='target_attained', alpha=1.0, limitations=['once_only_startup_permission_required'], zero_progress=False)
        if time.perf_counter() >= deadline:
            result.update(status='no_command', reason='timeout', command=None, tracking_status='no_command')
        result['elapsed_ms'] = 1000 * (time.perf_counter() - started)
        return result

    def decide(self, state, reference, *, previous):
        if len(self.audit) >= 128:
            raise ValueError('inexact_tracking_audit_budget')
        result = self._decide(state, reference, previous=previous)
        from copy import deepcopy
        keys = ('status', 'reason', 'command', 'requested_wrench', 'static_command', 'static_inspection', 'inspection', 'tracking_status', 'target_rewritten', 'limitations', 'zero_progress', 'elapsed_ms')
        self.audit.append(dict(physics_index=self.physics_index(), state=owned(state), reference=owned(reference), previous=None if previous is None else owned(previous), result=deepcopy({k: result.get(k) for k in keys})))
        return result

    def _decide(self, state, reference, *, previous):
        started = time.perf_counter()
        deadline = started + self.config.timeout_ms / 1000
        if previous is None:
            return self._startup_tracking_decision(state, reference, previous=None)
        result = dict(status='no_command', command=None, reason=None, startup_exception_requested=False, runtime_eligible=False, actual_history_advanced=False, configuration=self.domain.configuration, context_key=self.domain.context_key, model_id=self.domain.model_id, support_id=self.domain.identity, demand=None, inspection=None, static_inspection=None, requested_wrench=None, tracking_status='no_command', target_rewritten=False, iterations=0, evaluations=0)

        def finish(reason):
            if reason is None and time.perf_counter() >= deadline:
                reason = 'timeout'
            if reason is not None:
                result.update(status='no_command', command=None, tracking_status='no_command')
            result.update(reason=reason, elapsed_ms=1000 * (time.perf_counter() - started))
            return result
        try:
            check_deadline(deadline)
            if not self._binding_matches(result['support_id']):
                return finish('policy_binding_changed')
            x = np.array(state, dtype=float, copy=True)
            ref = checked_reference(reference)
            if x.shape != (11,):
                return finish('state_invalid')
            rejected = self.domain.check_states(x[None])
            if rejected:
                return finish('state_' + rejected['reason'])
            demand = feedback_demand(x, ref, self.domain.configuration, self.context, self.config)
            result.update(demand=demand, requested_wrench=demand['target_wrench'].copy())
            old = np.asarray(previous, dtype=float)
            if old.shape != (4,) or not np.isfinite(old).all() or np.any(np.abs(old) > 0.95) or np.any(np.abs(old * (1 - self.steady.mask)) > COMMAND_ATOL):
                return finish('previous_command_invalid')
            inverse = self.steady.static_inverse(demand['target_wrench'], old, self.config, deadline=deadline)
            result.update(static_inspection=inverse['inspection'], iterations=inverse['iterations'], evaluations=inverse['evaluations'])
            if inverse['status'] != 'ready':
                return finish(inverse['reason'])
            limited = limit_tracking_command(self.steady, demand['target_wrench'], inverse['command'], old, self.domain.command_lower, self.domain.command_upper, self.config.slew, deadline=deadline)
            limited['evaluations'] += inverse['evaluations']
            result.update(limited)
            return finish(limited['reason'])
        except TimeoutError:
            return finish('timeout')
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
            return finish('invalid_or_numerical:' + str(exc))
