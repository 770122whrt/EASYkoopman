"""Differentiable projection/actuator proxy for continuous-sequence optimization.

The admitted matrix and mechanics are unchanged. Command/PWM quantization is
omitted inside differentiation; every proposed solution needs the old exact
rollout before admission. This module never advances live actuator history.
"""
import math

import casadi as ca
import numpy as np

from koopman.command_state_v39 import _PredictionOrigin
from koopman.prepared_allocation_v42 import PreparedDirectAllocation
from koopman.prepared_projected_v40 import _PreparedProjected, _context_key


DT = 1 / 120


def rotation(q):
    q = q / ca.sqrt(ca.dot(q, q))
    w, x, y, z = (q[i] for i in range(4))
    return ca.vertcat(
        ca.horzcat(1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)),
        ca.horzcat(2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)),
        ca.horzcat(2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)))


def _pose_step(x, nu, old_rotation):
    theta = DT * nu[3:6]
    square = ca.dot(theta, theta)
    norm = ca.sqrt(square + 1e-30)
    # Analytic continuation makes the zero-angular-rate Jacobian finite.
    scale = ca.if_else(square < 1e-12,
                       .5-square/48+square*square/3840, ca.sin(norm/2)/norm)
    dq = scale*theta
    real = ca.cos(norm/2)
    q = x[1:5]
    q_next = ca.vertcat(q[0]*real-ca.dot(q[1:4], dq),
                       q[0]*dq+real*q[1:4]+ca.cross(q[1:4], dq))
    q_next /= ca.sqrt(ca.dot(q_next, q_next))
    transform = rotation(q_next).T @ old_rotation
    return ca.vertcat(x[0]+DT*(old_rotation[2, :] @ nu[:3]), q_next,
                      transform @ nu[:3], transform @ nu[3:6])


def _projected_step(b, x, applied):
    r = rotation(x[1:5]); v = x[5:8]; omega = x[8:11]
    linear = ca.DM(b._linear)*x[5:11]*b._drag
    quadratic = ca.DM(b._quadratic)*ca.fabs(x[5:11])*x[5:11]*b._drag
    restoring = ca.cross(ca.DM(b._cob), b._buoyancy_force*r[2, :].T)/ca.DM(b._inertia)
    gyro = -ca.cross(omega, ca.DM(b._inertia)*omega)/ca.DM(b._inertia)

    def axes(values):
        return ca.vertcat(*[r[k, j]*values[j] for j in range(3) for k in range(3)])

    pieces = [x[0], ca.vertcat(*[r[i, j] for i in range(3) for j in range(3)]),
              r @ v, omega, axes(v)]
    if b._family == 'nonlinear':
        pieces += [axes(quadratic[:3]), quadratic[3:6]]
    pieces += [ca.DM([0, 0, b._net_buoyancy_acceleration]), restoring, gyro,
               r @ linear[:3], linear[3:6], 1]
    following = ca.DM(b._matrix[:, 10:16]).T @ ca.vertcat(*pieces)
    following += ca.vertcat(DT*(r @ applied[:3]),
                           DT*(1-b._angular_damping*DT)*applied[3:6])
    return _pose_step(x, ca.vertcat(r.T @ following[:3], following[3:6]), r)


class SymbolicPlant:
    """A configuration-bound symbolic version of the frozen projected plant."""

    def __init__(self, predictor, configuration):
        b = getattr(predictor, '_symbolic_base', getattr(predictor, '_base', predictor))
        if not isinstance(b, _PreparedProjected):
            raise ValueError('symbolic_prepared_projected_required')
        self.base = b
        self.configuration = configuration
        self.allocator = PreparedDirectAllocation(configuration)
        a = self.allocator
        if a._inverse is None:
            matrix = np.array([[-1, -1, 0, 1], [1, -1, 0, 1],
                               [-1, 1, 0, 1], [1, 1, 0, 1],
                               [0, 0, 1, 0], [0, 0, -1, 0],
                               [0, 0, -1, 0], [0, 0, 1, 0]], dtype=float)
        else:
            embedding = np.zeros((6, 4))
            embedding[[3, 4, 5, 2], np.arange(4)] = a._sign
            if a._weights is not None:
                embedding *= a._weights[:, None]
            matrix = a._inverse.numpy().astype(float) @ embedding
        self.allocation_matrix = matrix * a._mask[None, :]
        x = ca.SX.sym('state', 11); u = ca.SX.sym('acceleration', 6)
        self.step = ca.Function('projected_step', [x, u], [_projected_step(b, x, u)])
        self._rollouts = {}

    def rollout_function(self, horizon):
        if type(horizon) is not int or not 1 <= horizon <= 64:
            raise ValueError('symbolic_horizon')
        if horizon in self._rollouts:
            return self._rollouts[horizon]
        n = self.allocator.wrench_matrix.shape[1]
        initial = ca.SX.sym('initial', 11)
        initial_speed = ca.SX.sym('initial_speed', n)
        controls = ca.SX.sym('controls', 4, horizon)
        alphas = ca.SX.sym('alphas', 4*horizon)
        state, speed = initial, initial_speed
        states, speeds, raws = [], [], []
        threshold = float(np.float32(.02))
        scale = ca.DM([self.base._key[0]]*3 + list(self.base._inertia))
        for k in range(horizon):
            raw = ca.DM(self.allocation_matrix) @ controls[:, k]
            pwm = ca.fmin(ca.fmax(raw, -1), 1)
            target = ca.if_else(pwm >= threshold, -139*pwm*pwm+500*pwm+8.28,
                     ca.if_else(pwm <= -threshold, 161*pwm*pwm+517.86*pwm-5.72, 0))
            raws.append(raw)
            for substep in range(4):
                alpha = alphas[4*k+substep]
                speed = alpha*speed+(1-alpha)*target
                force = self.allocator.rotor_constant*ca.fabs(speed)*speed
                acceleration = (ca.DM(self.allocator.wrench_matrix) @ force)/scale
                state = self.step(state, acceleration)
                states.append(state); speeds.append(speed)
        f = ca.Function('command_rollout', [initial, initial_speed, controls, alphas],
                        [ca.horzcat(*states), ca.horzcat(*speeds), ca.horzcat(*raws)])
        self._rollouts[horizon] = f
        return f

    def actuator_inputs(self, origin, horizon):
        if (not isinstance(origin, _PredictionOrigin)
                or origin._configuration != self.configuration
                or _context_key(origin._context) != self.base._key
                or origin.origin_control % 2):
            raise ValueError('symbolic_origin_mismatch')
        actuator = origin._actuator
        clock = actuator.elapsed_time
        alphas = []
        for _ in range(4*horizon):
            if actuator.clock == 'float32_accumulated_v1':
                next_clock = float(np.float32(np.float32(clock)+np.float32(actuator.dt)))
                alphas.append(math.exp(-(next_clock-clock)/actuator.tau))
                clock = next_clock
            else:
                alphas.append(actuator.alpha)
        return actuator.current().copy(), np.asarray(alphas)

    def forecast(self, origin, state, controls):
        commands = np.asarray(controls, dtype=float)
        x = np.asarray(state, dtype=float)
        if (commands.ndim != 2 or commands.shape[1] != 4 or x.shape != (11,)
                or not np.isfinite(commands).all() or not np.isfinite(x).all()
                or np.any(np.abs(commands) > .95) or abs(np.linalg.norm(x[1:5])-1) > 1e-3):
            raise ValueError('symbolic_input_invalid')
        f = self.rollout_function(len(commands))
        speed, alphas = self.actuator_inputs(origin, len(commands))
        states, speeds, raw = f(x, speed, commands.T, alphas)
        return dict(predictions=np.asarray(states).T, rotor_speed=np.asarray(speeds).T,
                    pwm_raw=np.asarray(raw).T, quantization='float64_proxy_requires_exact_validation')
