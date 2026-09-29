"""Physical velocity rows in a finite lifted operator; explicit input and projection.

World linear velocity is a fixed observable of state. Old-frame next velocity
is not used as a purported fixed Koopman observable. This is a projected,
controlled approximation, not a claim of global finite-dimensional closure.
"""
import numpy as np
from koopman.physics_context import rotation
from koopman.physical_terms import state_terms,validate_states
from koopman.physical_integration import advance_old_frame_velocity

DT=1/120


def feature_names(family):
    if family not in ('linear','nonlinear'):raise ValueError('sparse_dictionary')
    names=['z']+[f'R{i}{j}' for i in range(3) for j in range(3)]
    names += [f'vw{i}' for i in range(3)]+[f'wb{i}' for i in range(3)]
    names += [f'axis_velocity_{j}_{k}' for j in range(3) for k in range(3)]
    if family=='nonlinear':
        names += [f'axis_quadratic_{j}_{k}' for j in range(3) for k in range(3)]
        names += [f'angular_quadratic_{j}' for j in range(3)]
    for group in ('buoyancy_world','restoring_body','gyro_body','linear_world','linear_angular'):
        names += [f'{group}_{j}' for j in range(3)]
    return names+['constant']


def lift(states,context,family):
    x=validate_states(states);feature_names(family)
    r=rotation(x[:,1:5]);terms=state_terms(x,context)
    world=lambda v:np.einsum('nij,nj->ni',r,v)
    axis=lambda v:(r*v[:,None,:]).transpose(0,2,1).reshape(len(x),9)
    values=[x[:,:1],r.reshape(len(x),9),world(x[:,5:8]),x[:,8:],axis(x[:,5:8])]
    if family=='nonlinear':values += [axis(terms['quadratic_drag'][:,:3]),terms['quadratic_drag'][:,3:]]
    values += [np.tile([0,0,(context.rho*context.volume/context.mass-1)*context.gravity],(len(x),1)),
        terms['restoring'],terms['gyro'],world(terms['linear_drag'][:,:3]),terms['linear_drag'][:,3:],np.ones((len(x),1))]
    return np.concatenate(values,axis=1)




def core_matrix(family,damping,quadratic,angular_damping):
    names=feature_names(family);index={n:i for i,n in enumerate(names)}
    d=np.asarray(damping,dtype=float);q=np.asarray(quadratic,dtype=float)
    if (d.shape!=(6,) or q.shape!=(6,) or not np.isfinite(d).all() or not np.isfinite(q).all()
            or np.any(d<0) or np.any(d>20) or np.any(q<0) or np.any(q>2)
            or family=='linear' and np.any(q) or not 0<=angular_damping<120):raise ValueError('sparse_parameters')
    a=np.eye(len(names));a[:,10:16]=0.;factor=1-angular_damping*DT
    for k in range(3):
        output=10+k;a[output,output]=1.
        for group in ('buoyancy_world','linear_world'):a[index[f'{group}_{k}'],output]=DT
        for j in range(3):
            a[index[f'axis_velocity_{j}_{k}'],output]=-DT*d[j]
            if family=='nonlinear':a[index[f'axis_quadratic_{j}_{k}'],output]=DT*q[j]
        output=13+k;a[output,output]=factor*(1-DT*d[3+k])
        for group in ('restoring_body','gyro_body','linear_angular'):a[index[f'{group}_{k}'],output]=DT*factor
        if family=='nonlinear':a[index[f'angular_quadratic_{k}'],output]=DT*factor*q[3+k]
    return a


def predict_projected(states,acceleration,context,matrix,family,angular_damping):
    x=validate_states(states);a=np.asarray(matrix,dtype=float);dimension=len(feature_names(family))
    if a.shape!=(dimension,dimension) or not np.isfinite(a).all():raise ValueError('sparse_matrix')
    u=np.asarray(acceleration,dtype=float)
    if u.shape!=(len(x),6) or not np.isfinite(u).all() or not 0<=angular_damping<120:raise ValueError('sparse_input')
    old_r=rotation(x[:,1:5])
    # The explicit projection consumes these six rows; the complete matrix is
    # retained for full-lift/closure diagnostics, not multiplied wastefully here.
    following=lift(x,context,family)@a[:,10:16]
    following[:,:3]+=DT*np.einsum('nij,nj->ni',old_r,u[:,:3])
    following[:,3:]+=DT*(1-angular_damping*DT)*u[:,3:]
    old_frame_linear=np.einsum('nji,nj->ni',old_r,following[:,:3])
    return advance_old_frame_velocity(x,np.c_[old_frame_linear,following[:,3:]])
