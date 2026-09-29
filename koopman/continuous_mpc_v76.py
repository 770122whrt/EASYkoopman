"""Continuous nonlinear sequence optimization, with independent exact admission.

Offline/synchronous effects interface only. No live tickets, guessed-direction
candidate enumeration, model fitting, or real-time qualification is implied.
"""
import time

import casadi as ca
import numpy as np

from koopman.bounded_mpc_v44 import SupportDomain, COMMAND_ATOL
from koopman.control_objective_v44 import ObjectiveWeights, checked_reference, control_mask, trajectory_cost
from koopman.continuous_prediction_v76 import SymbolicPlant, rotation
from koopman.prepared_commands_v45 import PreparedCommands
from workflows.feedback_inverse_v28 import MINIMUM_DEADZONE_DISTANCE


def _angle(vector, scalar):
    return 2*ca.atan2(ca.sqrt(ca.dot(vector, vector)+1e-30), ca.sqrt(scalar*scalar+1e-30))


def _state_features(x, mask):
    r = rotation(x[1:5])
    angle = _angle(x[2:5], x[1]) if mask[2] else 0.
    return ca.vertcat(x[0], r[2, :].T, x[5:11], angle)


def _tracking(x, ref, mask, weights):
    q = x[1:5]/ca.sqrt(ca.dot(x[1:5], x[1:5]))
    r = rotation(q); desired = ref[1:5]
    if mask[2]:
        vector = desired[0]*q[1:4]-q[0]*desired[1:4]-ca.cross(desired[1:4], q[1:4])
        angle = _angle(vector, ca.dot(q, desired))
    else:
        up, target = r[2, :].T, rotation(desired)[2, :].T
        cross = ca.cross(up, target)
        angle = ca.atan2(ca.sqrt(ca.dot(cross, cross)+1e-30), ca.dot(up, target))
    return (weights.depth*(x[0]-ref[0])**2 + weights.attitude*angle**2
            + weights.vertical_speed*(r[2, :] @ x[5:8])**2
            + weights.angular_speed*ca.dot(x[8:11]*ca.DM(mask[:3]), x[8:11]*ca.DM(mask[:3])))


class ContinuousMPC:
    """Jointly optimize all controllable channels at every future 30Hz interval."""

    def __init__(self, domain, predictor, *, horizon=10, weights=ObjectiveWeights(),
                 max_iterations=160, solve_seconds=30., allow_diagnostic=False):
        if not isinstance(domain, SupportDomain) or (not domain._verified_fit and not allow_diagnostic):
            raise ValueError('continuous_fit_provenance_required')
        if (type(horizon) is not int or not 1 <= horizon <= 64
                or type(max_iterations) is not int or not 1 <= max_iterations <= 2000
                or not np.isfinite(solve_seconds) or not 0 < solve_seconds <= 300
                or not isinstance(weights, ObjectiveWeights)):
            raise ValueError('continuous_config_invalid')
        self.domain, self.predictor, self.horizon, self.weights = domain, predictor, horizon, weights
        self.plant = SymbolicPlant(predictor, domain.configuration)
        if self.plant.base._key != domain.context_key:
            raise ValueError('continuous_context_mismatch')
        self.mask = control_mask(domain.configuration)
        self.axes = np.flatnonzero(self.mask)
        self.max_iterations, self.solve_seconds = max_iterations, solve_seconds
        self._build()

    def _build(self):
        h = self.horizon; axes = self.axes; domain = self.domain; weights = self.weights
        n = self.plant.allocator.wrench_matrix.shape[1]
        decisions = ca.MX.sym('control_sequence', len(axes), h)
        params = ca.MX.sym('parameters', 11+n+4*h+4+5)
        x = params[:11]; speed = params[11:11+n]
        alpha = params[11+n:11+n+4*h]
        previous = params[11+n+4*h:15+n+4*h]; ref = params[-5:]
        embed = np.eye(4)[:, axes]
        commands = ca.DM(embed) @ decisions
        states, speeds, raw = self.plant.rollout_function(h)(x, speed, commands, alpha)
        constraints, lower, upper = [], [], []

        def constrain(value, lo, hi):
            value = ca.vec(value)
            constraints.append(value)
            lower.extend(np.broadcast_to(lo, (value.numel(),)).tolist())
            upper.extend(np.broadcast_to(hi, (value.numel(),)).tolist())

        objective = 0
        feature_lower = domain.state_lower.copy()
        feature_upper = domain.state_upper.copy()
        # Unit-quaternion rotations already satisfy these mathematical bounds.
        # At rest their zero-gradient active barriers defeat strict interior
        # convergence, while adding no restriction to the feasible set.
        for j in (1, 2, 3):
            if feature_lower[j] <= -1: feature_lower[j] = -np.inf
            if feature_upper[j] >= 1: feature_upper[j] = np.inf
        for k in range(4*h):
            state = states[:, k]
            features = _state_features(state, self.mask)
            constrain(features, feature_lower, feature_upper)
            constrain(state[0], 3.5, 7.5)
            constrain(ca.dot(state[5:8], state[5:8]), -np.inf, 1.5**2)
            constrain(ca.dot(state[8:11], state[8:11]), -np.inf, 3.**2)
            constrain(features[3], .5, np.inf)
            tracking = _tracking(state, ref, self.mask, weights)
            objective += tracking/120
        objective += weights.terminal*tracking
        for k in range(h):
            delta = commands[:, k]-(previous if k == 0 else commands[:, k-1])
            constrain(delta, -.02, .02)
            constrain(raw[:, k], -.95, .95)
            constrain(ca.fabs(ca.fabs(raw[:, k])-float(np.float32(.02))),
                      MINIMUM_DEADZONE_DISTANCE, np.inf)
            # Original 60Hz-grid cost: 2 held effort entries, one change entry.
            objective += weights.effort*ca.dot(commands[:, k], commands[:, k])/30
            objective += weights.slew*ca.dot(delta, delta)/60
        problem = dict(x=ca.vec(decisions), p=params, f=objective, g=ca.vertcat(*constraints))
        self._solver = ca.nlpsol('continuous_v76', 'ipopt', problem, {
            'print_time': False, 'error_on_fail': False,
            'ipopt.print_level': 0, 'ipopt.sb': 'yes',
            'ipopt.max_iter': self.max_iterations, 'ipopt.max_cpu_time': self.solve_seconds,
            'ipopt.tol': 1e-8, 'ipopt.constr_viol_tol': 1e-9,
            'ipopt.bound_relax_factor': 0., 'ipopt.hessian_approximation': 'limited-memory'})
        self._evaluate = ca.Function('evaluate_sequence', [decisions, params],
                                     [objective, ca.vertcat(*constraints)])
        self._lower_g, self._upper_g = np.asarray(lower), np.asarray(upper)

    def check(self, origin, state, commands, previous, reference):
        """Independent float32 allocation + old forecast + original state gates."""
        a = np.asarray(commands, dtype=float)
        result = dict(feasible=False, reason=None, cost=None, predictions=None)
        if (a.ndim != 2 or a.shape[1] != 4 or not 1 <= len(a) <= self.horizon
                or not np.isfinite(a).all() or np.any(np.abs(a) > .95)):
            result['reason'] = 'command_bound'; return result
        a = a.astype(np.float32)
        domain = self.domain
        checks = [('command_mask', np.any(np.abs(a*(1-self.mask)) > COMMAND_ATOL)),
                  ('command_support', np.any((a < domain.command_lower-COMMAND_ATOL) |
                                              (a > domain.command_upper+COMMAND_ATOL))),
                  ('command_slew', np.any(np.abs(np.diff(np.vstack([previous, a.astype(float)]), axis=0)) > .02+COMMAND_ATOL))]
        for reason, bad in checks:
            if bad: result['reason'] = reason; return result
        micro = np.repeat(a, 2, axis=0)
        prepared = PreparedCommands(origin, micro[None], allocator=self.plant.allocator)
        raw = prepared.pwm_raw[0].astype(float)
        if np.max(np.abs(raw)) > .95+COMMAND_ATOL:
            result['reason'] = 'raw_pwm_saturation'; return result
        if np.min(np.abs(np.abs(raw)-float(np.float32(.02)))) <= MINIMUM_DEADZONE_DISTANCE:
            result['reason'] = 'raw_pwm_deadzone_margin'; return result
        prediction = origin.forecast(state, micro, self.predictor)
        if not prediction['complete']:
            result['reason'] = 'prediction_failed'; return result
        bad = domain.check_states(prediction['predictions'])
        if bad:
            result.update(reason='predicted_'+bad['reason'], rejection=bad); return result
        result.update(feasible=True, predictions=prediction['predictions'],
                      cost=trajectory_cost(prediction['predictions'], micro, previous, reference,
                                           self.mask, self.weights))
        return result

    def solve(self, *, origin, initial_state, baseline, previous, reference, committed_prefix=0):
        start = time.perf_counter()
        result = dict(status='no_plan', reason=None, commands=None, predictions=None,
                      cost=None, baseline_cost=None, exact_feasible=False,
                      runtime_eligible=False, search_kind='continuous_nonlinear_program',
                      decision_variables=len(self.axes)*self.horizon, solver=None,
                      candidate_commands=None, candidate_failure=None, selected_source=None)

        def finish(reason=None):
            result['reason'] = reason; result['elapsed_seconds'] = time.perf_counter()-start
            return result

        try:
            x = np.asarray(initial_state, dtype=float)
            base = np.asarray(baseline, dtype=float); old = np.asarray(previous, dtype=float)
            ref = checked_reference(reference)
            if (x.shape != (11,) or base.shape != (self.horizon, 4) or old.shape != (4,)
                    or not all(np.isfinite(v).all() for v in [x, base, old])
                    or type(committed_prefix) is not int or not 0 <= committed_prefix <= self.horizon):
                return finish('request_input_invalid')
            if self.domain.check_states(x[None]): return finish('initial_state_out_of_support')
            speed, alphas = self.plant.actuator_inputs(origin, self.horizon)
            baseline_check = self.check(origin, x, base, old, ref)
            result['baseline_check'] = {k: v for k, v in baseline_check.items() if k != 'predictions'}
            result['baseline_cost'] = baseline_check['cost']
            if committed_prefix:
                prefix_check = self.check(origin, x, base[:committed_prefix], old, ref)
                if not prefix_check['feasible']: return finish('committed_prefix_infeasible')
            lower = np.tile(self.domain.command_lower[self.axes], (self.horizon, 1)).T.copy()
            upper = np.tile(self.domain.command_upper[self.axes], (self.horizon, 1)).T.copy()
            lower[:, :committed_prefix] = upper[:, :committed_prefix] = base[:committed_prefix, self.axes].T
            parameters = np.r_[x, speed, alphas, old, ref]
            initial = np.clip(base[:, self.axes].T, lower, upper)
            solved = self._solver(x0=initial.reshape(-1, order='F'), p=parameters,
                                  lbx=lower.reshape(-1, order='F'), ubx=upper.reshape(-1, order='F'),
                                  lbg=self._lower_g, ubg=self._upper_g)
            stats = self._solver.stats()
            result['solver'] = dict(return_status=stats['return_status'], success=bool(stats['success']),
                                    iterations=int(stats.get('iter_count', -1)), global_optimum_claimed=False,
                                    timed_out=stats['return_status'] in ('Maximum_CpuTime_Exceeded', 'Maximum_WallTime_Exceeded'))
            candidate = np.asarray(solved.get('x', []), dtype=float).ravel()
            checked = dict(feasible=False, reason='candidate_unavailable', cost=None, predictions=None)
            if candidate.size == len(self.axes)*self.horizon and np.isfinite(candidate).all():
                answer = np.zeros((self.horizon, 4))
                answer[:, self.axes] = candidate.reshape((len(self.axes), self.horizon), order='F').T
                result['candidate_commands'] = answer.copy()
                # Recompute constraints from the iterate; returned g is not trusted.
                _, values = self._evaluate(answer[:, self.axes].T, parameters)
                values = np.asarray(values).ravel()
                result['constraint_violation'] = (float(max(0., np.max(self._lower_g-values),
                    np.max(values-self._upper_g))) if np.isfinite(values).all() else None)
                result['command_bound_violation'] = float(max(0.,
                    np.max(lower.ravel(order='F')-candidate), np.max(candidate-upper.ravel(order='F'))))
                checked = self.check(origin, x, answer, old, ref)
                if committed_prefix and not np.array_equal(answer[:committed_prefix].astype(np.float32),
                                                           base[:committed_prefix].astype(np.float32)):
                    checked = dict(feasible=False, reason='committed_prefix_changed', cost=None, predictions=None)
            else:
                result['candidate_failure'] = 'nonfinite_or_invalid_shape'
            result['solution_check'] = {k: v for k, v in checked.items() if k != 'predictions'}
            if checked['feasible'] and (not baseline_check['feasible'] or checked['cost'] < baseline_check['cost']):
                status = 'optimized' if baseline_check['feasible'] else 'recovered'
                chosen, check = answer, checked
                result['selected_source'] = 'solver_candidate'
            elif baseline_check['feasible']:
                status, chosen, check = 'baseline_retained', base, baseline_check
                result['selected_source'] = 'baseline'
            else:
                return finish('no_exact_feasible_solution_found')
            result.update(status=status, commands=chosen.astype(np.float32), predictions=check['predictions'],
                          cost=check['cost'], exact_feasible=True)
            return finish()
        except (ValueError, RuntimeError, FloatingPointError) as exc:
            result['exception'] = str(exc)
            return finish('numerical_or_input_failure')
