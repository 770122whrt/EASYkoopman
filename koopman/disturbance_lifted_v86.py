"""Full-latent Koopman and frozen physics + autonomous latent residual.

Only current observed state initializes z. The actuator uses acknowledged past
commands and planned controls. No plant disturbance parameter enters this API.
Hybrid coordinates: xi+ = xi(F_phys(x,u)) + R z; z+ = A z + B phi(u).
The hybrid is nonlinear, not a linear-QP model. No online parameter fitting.
"""
import hashlib
import numpy as np
from koopman import lifted_propagation_v84 as lk
from koopman.prepared_projected_v40 import _context_key, _immutable


def physical_identity(physical):
    b = physical._symbolic_base
    return hashlib.sha256(np.asarray(b._key, dtype=float).tobytes()+
        b._matrix.tobytes()+np.asarray([b._angular_damping],float).tobytes()).hexdigest()


def fit(states, following, inputs, context, physical, *, ridge):
    x = np.asarray(states, float); y = np.asarray(following, float); u = np.asarray(inputs, float)
    weights = np.ones(len(x))
    latent = lk.fit_lifted(x,y,u,[context]*len(x),weights,ridge=ridge)
    z = lk.lift(x); design = z[:,1:]
    target = lk.coordinates(y)-lk.coordinates(physical(x,u,context))
    scale = np.maximum(np.sqrt(np.mean(design**2,axis=0)),1e-6)
    a = design/scale
    coefficient = np.linalg.solve(a.T@a/len(x)+ridge*np.eye(a.shape[1]), a.T@target/len(x))/scale[:,None]
    residual = np.zeros((10,z.shape[1]));residual[:,1:] = coefficient.T
    return lk.seal(dict(schema='disturbance-full-latent-v86',lifted=latent,residual=residual.tolist(),
        physical_identity=physical_identity(physical),
        audit=dict(training_rows=len(x),latent_relift_inside_horizon=False,
                   initialization='current_state_only',parameter_updates_at_test=False,
                   physical_recalibrated=False,isaac_performance_established=False)))


def prepare(record, context, physical, *, kind):
    if record.get('content_sha256') != lk.seal(record)['content_sha256']:
        raise ValueError('v86_record_hash')
    if record.get('schema') != 'disturbance-full-latent-v86' or record['physical_identity'] != physical_identity(physical):
        raise ValueError('v86_physical_binding')
    return LiftedPredictor(lk.prepare_lifted(record['lifted'],context),physical,
                           kind=kind,residual=record['residual'])


class LiftedPredictor:
    def __init__(self, latent, physical, *, kind, residual):
        if kind not in ('koopman','hybrid') or latent._key != physical._key:
            raise ValueError('v86_kind_or_context')
        r = np.asarray(residual,float)
        if r.shape != (10,len(lk.feature_names())) or not np.isfinite(r).all():
            raise ValueError('v86_residual_shape')
        self.latent,self.physical,self.kind = latent,physical,kind
        self.residual = _immutable(r)
        self._symbolic_base = physical._symbolic_base

    def __call__(self, states, inputs, context):
        raise ValueError('forecast_session_required')

    def start_forecast(self, states, context):
        if _context_key(context) != self.latent._key:
            raise ValueError('v86_context')
        z = lk.lift(states)
        def advance(x,u,c):
            nonlocal z
            next_z = self.latent.step(z,u,c)
            if self.kind == 'koopman':
                y = lk.decode(next_z[:,:10])
            else:
                y = lk.decode(lk.coordinates(self.physical(x,u,c))+z@self.residual.T)
            z = next_z
            return y
        return advance

    def symbolic_initialize(self,x):
        import casadi as ca
        t = ca.vertcat(x[0]-5.5,x[2:5]/x[1],x[5:11]);w=t[7:10]
        return ca.vertcat(t,t[1:]**2,t[4:]*ca.fabs(t[4:]),w[0]*w[1],w[1]*w[2],w[2]*w[0],
            *[t[1+i]*w[j] for i in range(3) for j in range(3)],1.)

    def symbolic_advance(self,x,z,u,physical_step):
        import casadi as ca
        next_z = self.latent.symbolic_step(z,u)
        if self.kind == 'koopman':
            t = next_z[:10]
        else:
            p = physical_step(x,u)
            t = ca.vertcat(p[0]-5.5,p[2:5]/p[1],p[5:11])+ca.DM(self.residual)@z
        q = ca.vertcat(1.,t[1:4]);q /= ca.sqrt(ca.dot(q,q))
        return ca.vertcat(t[0]+5.5,q,t[4:10]),next_z
