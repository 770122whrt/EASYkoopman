"""Prepared frozen velocity dynamics with shared state geometry.

This keeps the same lifted velocity matrix and pose integration, with no fit
or model-form change. Fixed mechanics are bound at preparation; a different
runtime context is rejected. Arrays are owned immutable copies, and calls
have no state, so optimizer branches can safely share the prepared object.
"""
from dataclasses import dataclass, replace

import numpy as np

from koopman.physical_terms import validate_states
from koopman.physics_context import PhysicalContext, rotation
from koopman.sparse_physics import DT
from workflows.frozen_physics import SparseModel, validate_matrix


def _immutable(value):
    array = np.asarray(value, dtype=float)
    return np.frombuffer(array.tobytes(), dtype=float).reshape(array.shape)


def _context_key(context):
    if not isinstance(context, PhysicalContext):
        raise ValueError('prepared_context_invalid')
    return (context.mass, *context.inertia, *context.cob, context.volume,
            context.drag_multiplier, context.rho, context.beta, context.gravity)


def prepare_projected(model, context):
    """Prepare a validated matrix, keeping model provenance admission upstream."""
    if not isinstance(model, SparseModel):
        raise ValueError('prepared_model_invalid')
    _context_key(context)
    c = replace(context)  # revalidate mechanics and own their array values
    matrix = validate_matrix(model.matrix, model.family, model.damping,
                             model.quadratic, model.angular_damping)
    radii = np.sqrt(np.maximum(3/(2*c.mass)*(
        np.roll(c.inertia, 1)+np.roll(c.inertia, -1)-c.inertia), 1e-9))
    mean = radii.mean()
    rj, rk = np.roll(radii, 1), np.roll(radii, -1)
    # Keep the original multiplication order: drag_multiplier is applied last.
    linear = np.r_[np.full(3, -6*c.beta*np.pi*mean/c.mass),
                   -8*c.beta*np.pi*mean**3/c.inertia]
    quadratic = np.r_[-2*c.rho*rj*rk/c.mass,
                      -.5*c.rho*radii*(rj**4+rk**4)/c.inertia]
    return _PreparedProjected(model.family, _immutable(matrix), float(model.angular_damping),
        _context_key(c), _immutable(c.inertia), _immutable(c.cob), c.drag_multiplier,
        c.rho*c.volume*c.gravity, (c.rho*c.volume/c.mass-1)*c.gravity,
        _immutable(linear), _immutable(quadratic))


@dataclass(frozen=True)
class _PreparedProjected:
    _family: str
    _matrix: np.ndarray
    _angular_damping: float
    _key: tuple
    _inertia: np.ndarray
    _cob: np.ndarray
    _drag: float
    _buoyancy_force: float
    _net_buoyancy_acceleration: float
    _linear: np.ndarray
    _quadratic: np.ndarray

    def __call__(self, states, acceleration, context):
        if _context_key(context) != self._key:
            raise ValueError('prepared_context_mismatch')
        x = validate_states(states)
        u = np.asarray(acceleration, dtype=float)
        if u.shape != (len(x), 6) or not np.isfinite(u).all():
            raise ValueError('sparse_input')
        r = rotation(x[:, 1:5])
        v, w = x[:, 5:8], x[:, 8:]
        linear = self._linear*x[:, 5:]*self._drag
        quadratic = self._quadratic*np.abs(x[:, 5:])*x[:, 5:]*self._drag
        restoring = np.cross(self._cob, self._buoyancy_force*r[:, 2, :])/self._inertia
        gyro = -np.cross(w, self._inertia*w)/self._inertia

        def world(value):
            return np.einsum('nij,nj->ni', r, value)

        def axes(value):
            return (r*value[:, None, :]).transpose(0, 2, 1).reshape(len(x), 9)

        values = [x[:, :1], r.reshape(len(x), 9), world(v), w, axes(v)]
        if self._family == 'nonlinear':
            values += [axes(quadratic[:, :3]), quadratic[:, 3:]]
        values += [np.tile([0, 0, self._net_buoyancy_acceleration], (len(x), 1)),
                   restoring, gyro, world(linear[:, :3]), linear[:, 3:], np.ones((len(x), 1))]
        following = np.concatenate(values, axis=1) @ self._matrix[:, 10:16]
        following[:, :3] += DT*world(u[:, :3])
        following[:, 3:] += DT*(1-self._angular_damping*DT)*u[:, 3:]
        nu = np.c_[np.einsum('nji,nj->ni', r, following[:, :3]), following[:, 3:]]
        if not np.isfinite(nu).all():
            raise ValueError('physical_prediction_velocity')

        # Identical predicted-velocity pose update, reusing the old rotation.
        y = x.copy()
        y[:, 0] += DT*np.einsum('ni,ni->n', r[:, 2, :], nu[:, :3])
        theta = DT*nu[:, 3:]
        norm = np.linalg.norm(theta, axis=1, keepdims=True)
        dq = np.concatenate((np.cos(norm/2), .5*np.sinc(norm/(2*np.pi))*theta), axis=1)
        q = x[:, 1:5]
        a, b, c, d = q[:, :1], q[:, 1:], dq[:, :1], dq[:, 1:]
        quaternion = np.concatenate((a*c-np.sum(b*d, axis=1, keepdims=True),
                                     a*d+c*b+np.cross(b, d)), axis=1)
        y[:, 1:5] = quaternion/np.linalg.norm(quaternion, axis=1, keepdims=True)
        new_r = rotation(y[:, 1:5])
        transform = np.einsum('nji,njk->nik', new_r, r)
        y[:, 5:8] = np.einsum('nij,nj->ni', transform, nu[:, :3])
        y[:, 8:] = np.einsum('nij,nj->ni', transform, nu[:, 3:])
        return y
