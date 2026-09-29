"""Optional compiled execution of v40's same lifted matrix and pose update.

No fitting, matrix simplification, fastmath, parallel reductions, or alternative
physics. Preparation warms the only kernel signature before control use. Input
and context checks remain in the public wrapper; the compiled kernel also keeps
the original predicted-velocity finiteness guard.
"""
from dataclasses import dataclass

import numpy as np
from numba import njit

from koopman.physical_terms_v26 import validate_states
from koopman.prepared_projected_v40 import _context_key, prepare_projected
from koopman.sparse_world_edmd_v30 import DT


@njit(fastmath=False, nogil=True)
def _rotation(q):
    norm = np.sqrt(q[0]*q[0]+q[1]*q[1]+q[2]*q[2]+q[3]*q[3])
    w, x, y, z = q[0]/norm, q[1]/norm, q[2]/norm, q[3]/norm
    r = np.empty((3, 3))
    r[0, 0] = 1-2*(y*y+z*z); r[0, 1] = 2*(x*y-w*z); r[0, 2] = 2*(x*z+w*y)
    r[1, 0] = 2*(x*y+w*z); r[1, 1] = 1-2*(x*x+z*z); r[1, 2] = 2*(y*z-w*x)
    r[2, 0] = 2*(x*z-w*y); r[2, 1] = 2*(y*z+w*x); r[2, 2] = 1-2*(x*x+y*y)
    return r


@njit(fastmath=False, nogil=True)
def _cross(a, b):
    out = np.empty(3)
    out[0] = a[1]*b[2]-a[2]*b[1]
    out[1] = a[2]*b[0]-a[0]*b[2]
    out[2] = a[0]*b[1]-a[1]*b[0]
    return out


@njit(fastmath=False, nogil=True, error_model='numpy')
def _step(states, acceleration, nonlinear, matrix, angular_damping,
          inertia, cob, drag, buoyancy_force, net_buoyancy, linear_coefficient, quadratic_coefficient):
    result = states.copy()
    dimension = matrix.shape[0]
    for row in range(len(states)):
        x, u = states[row], acceleration[row]
        r = _rotation(x[1:5])
        linear, quadratic = np.empty(6), np.empty(6)
        for j in range(6):
            linear[j] = linear_coefficient[j]*x[5+j]*drag
            quadratic[j] = quadratic_coefficient[j]*abs(x[5+j])*x[5+j]*drag
        restoring = _cross(cob, buoyancy_force*r[2])/inertia
        gyro = -_cross(x[8:11], inertia*x[8:11])/inertia
        features = np.empty(dimension)
        features[0] = x[0]
        for j in range(3):
            features[10+j] = r[j, 0]*x[5]+r[j, 1]*x[6]+r[j, 2]*x[7]
            features[13+j] = x[8+j]
            for k in range(3):
                features[1+3*j+k] = r[j, k]
                features[16+3*j+k] = r[k, j]*x[5+j]
        cursor = 25
        if nonlinear:
            for j in range(3):
                for k in range(3): features[25+3*j+k] = r[k, j]*quadratic[j]
                features[34+j] = quadratic[3+j]
            cursor = 37
        features[cursor:cursor+3] = 0.
        features[cursor+2] = net_buoyancy
        for j in range(3):
            features[cursor+3+j] = restoring[j]
            features[cursor+6+j] = gyro[j]
            features[cursor+9+j] = r[j, 0]*linear[0]+r[j, 1]*linear[1]+r[j, 2]*linear[2]
            features[cursor+12+j] = linear[3+j]
        features[cursor+15] = 1.
        following = np.zeros(6)
        # Execute the whole admitted readout, including zeros; no D/Q rewrite.
        for output in range(6):
            for j in range(dimension):
                following[output] += features[j]*matrix[j, 10+output]
        for j in range(3):
            following[j] += DT*(r[j, 0]*u[0]+r[j, 1]*u[1]+r[j, 2]*u[2])
            following[3+j] += DT*(1-angular_damping*DT)*u[3+j]
        nu = following.copy()
        for j in range(3):
            nu[j] = r[0, j]*following[0]+r[1, j]*following[1]+r[2, j]*following[2]
        if not np.isfinite(nu).all(): raise ValueError('physical_prediction_velocity')
        result[row, 0] += DT*(r[2, 0]*nu[0]+r[2, 1]*nu[1]+r[2, 2]*nu[2])
        theta = DT*nu[3:6]
        norm = np.sqrt(theta[0]*theta[0]+theta[1]*theta[1]+theta[2]*theta[2])
        argument = norm/(2*np.pi)
        sinc = 1. if argument == 0 else np.sin(np.pi*argument)/(np.pi*argument)
        dq = .5*sinc*theta
        real = np.cos(norm/2)
        q = x[1:5]
        quaternion = np.empty(4)
        quaternion[0] = q[0]*real-(q[1]*dq[0]+q[2]*dq[1]+q[3]*dq[2])
        quaternion[1:4] = q[0]*dq+real*q[1:4]+_cross(q[1:4], dq)
        qnorm = np.sqrt(quaternion[0]**2+quaternion[1]**2+quaternion[2]**2+quaternion[3]**2)
        result[row, 1:5] = quaternion/qnorm
        new_r = _rotation(result[row, 1:5])
        transform = np.empty((3, 3))
        for j in range(3):
            for k in range(3):
                transform[j, k] = new_r[0, j]*r[0, k]+new_r[1, j]*r[1, k]+new_r[2, j]*r[2, k]
        for j in range(3):
            result[row, 5+j] = transform[j, 0]*nu[0]+transform[j, 1]*nu[1]+transform[j, 2]*nu[2]
            result[row, 8+j] = transform[j, 0]*nu[3]+transform[j, 1]*nu[4]+transform[j, 2]*nu[5]
    return result


@dataclass(frozen=True)
class _CompiledProjected:
    _base: object

    def __call__(self, states, acceleration, context):
        b = self._base
        if _context_key(context) != b._key:
            raise ValueError('prepared_context_mismatch')
        x = validate_states(states)
        u = np.asarray(acceleration, dtype=float)
        if u.shape != (len(x), 6) or not np.isfinite(u).all():
            raise ValueError('sparse_input')
        # Own fixed-layout mutable arrays: readonly/strided caller inputs must
        # neither introduce an un-warmed JIT signature nor alias any output.
        return _step(np.array(x, dtype=float, copy=True, order='C'),
            np.array(u, dtype=float, copy=True, order='C'), b._family == 'nonlinear',
            b._matrix, b._angular_damping, b._inertia, b._cob, float(b._drag),
            float(b._buoyancy_force), float(b._net_buoyancy_acceleration), b._linear, b._quadratic)


def prepare_compiled(model, context):
    """Validate/freeze the original model, then compile/warm before use."""
    compiled = _CompiledProjected(prepare_projected(model, context))
    initial = np.zeros((1, 11)); initial[0, 1] = 1.
    compiled(initial, np.zeros((1, 6)), context)
    return compiled
