import ast
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple
import numpy as np
import pytest
import torch
from koopman.projected_edmd_v24 import PhysicalContext


def api():
    assert importlib.util.find_spec('koopman.physical_terms_v26'), 'physical state terms not implemented'
    from koopman import physical_terms_v26
    return physical_terms_v26


def context():return PhysicalContext(23,[.3,1.1,1.2],[.01,-.02,.03],.024,1.3)


def states(n=12):
    rng=np.random.default_rng(261);x=rng.normal(size=(n,11));x[:,1:5]/=np.linalg.norm(x[:,1:5],axis=1,keepdims=True)
    return x


def source_model():
    # Execute the actual force class on CPU; this is not a fake Isaac runtime.
    source=Path(__file__).resolve().parents[1]/'easyuuv_nc/env/rigid_body_hydrodynamics.py'
    cls=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef))
    def apply(q,v):
        v=v.to(q.dtype)
        cross=torch.cross(q[:,1:],v,dim=-1)
        return v+2*(q[:,:1]*cross+torch.cross(q[:,1:],cross,dim=-1))
    def conjugate(q):return q*torch.tensor([1,-1,-1,-1],dtype=q.dtype)
    ns={'dataclass':dataclass,'Tuple':Tuple,'torch':torch,'quat_apply':apply,'quat_conjugate':conjugate}
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(source),'exec'),ns)
    return ns['HydrodynamicForceModels']


def test_terms_match_actual_hydrodynamic_source_with_rotation_and_inertia():
    m=api();x=states();c=context();terms=m.state_terms(x,c);n=len(x)
    t=lambda v:torch.tensor(v,dtype=torch.float64)
    model=source_model()(n,'cpu');mass=t(np.full((n,1),c.mass));inertia=t(np.tile(c.inertia,(n,1)))
    force,torque=model.calculate_buoyancy_forces(t(x[:,1:5]),c.rho,t(np.full((n,1),c.volume)),c.gravity,t(np.tile(c.cob,(n,1))))
    ld,la=model.calculate_linear_viscous_forces(t(x[:,5:8]),t(x[:,8:11]),inertia,mass,c.beta)
    qd,qa=model.calculate_quadratic_drag_forces(t(x[:,5:8]),t(x[:,8:11]),inertia,mass,c.rho)
    gravity=model.calculate_buoyancy_forces(t(x[:,1:5]),1.,mass, c.gravity,t(np.zeros((n,3))))[0]
    np.testing.assert_allclose(terms['net_buoyancy'],(force-gravity).numpy()/c.mass,atol=2e-14)
    np.testing.assert_allclose(terms['restoring'],torque.numpy()/c.inertia,atol=2e-13)
    np.testing.assert_allclose(terms['linear_drag'],np.concatenate((ld.numpy()/c.mass,la.numpy()/c.inertia),1)*c.drag_multiplier,atol=2e-15)
    np.testing.assert_allclose(terms['quadratic_drag'],np.concatenate((qd.numpy()/c.mass,qa.numpy()/c.inertia),1)*c.drag_multiplier,atol=2e-13)


def test_drag_is_dissipative_and_frame_gyro_terms_do_no_instantaneous_work():
    terms=api().state_terms(states(),context());nu=states()[:,5:];mass=np.r_[np.full(3,context().mass),context().inertia]
    assert np.all(np.sum(nu*mass*(terms['linear_drag']+terms['quadratic_drag']),1)<=0)
    conservative=np.concatenate((terms['transport'],terms['gyro']),1)
    np.testing.assert_allclose(np.sum(nu*mass*conservative,1),0,atol=3e-14)


def test_force_input_is_same_axis_and_not_learned_or_frame_rotated_twice():
    m=api();x=states();c=context();base=m.continuous_rate(x,np.zeros((len(x),6)),c)
    for j in range(6):
        a=np.zeros((len(x),6));a[:,j]=.31
        np.testing.assert_allclose(m.continuous_rate(x,a,c)-base,a,atol=2e-14)


def test_no_velocity_no_drag_transport_or_gyro():
    x=states();x[:,5:]=0;t=api().state_terms(x,context())
    for name in ('linear_drag','quadratic_drag','transport','gyro'):np.testing.assert_array_equal(t[name],0)


@pytest.mark.parametrize('bad',[np.ones((2,10)),np.full((2,11),np.nan),np.zeros((2,11))])
def test_invalid_state_rejected(bad):
    with pytest.raises(ValueError,match='physical_state_invalid'):api().state_terms(bad,context())


def test_invalid_input_rejected():
    with pytest.raises(ValueError,match='physical_input_invalid'):api().continuous_rate(states(),np.zeros((2,6)),context())
