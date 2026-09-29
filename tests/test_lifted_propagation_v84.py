"""Lifted recurrence must carry latent memory, not silently re-lift each step."""
import importlib
from dataclasses import replace
import numpy as np
import pytest
from test_prepared_projected_v40 import context


def api():
    assert importlib.util.find_spec('koopman.lifted_propagation_v84'), 'new lifted model is missing'
    return importlib.import_module('koopman.lifted_propagation_v84')


def state(n=1):
    x=np.zeros((n,11));x[:,0]=5.5;x[:,1]=1
    return x


def test_chart_roundtrip_sign_and_domain():
    m=api();x=state(3);x[:,1:5]=[[1,0,0,0],[np.cos(.1),np.sin(.1),0,0],[-1,0,0,0]]
    y=m.decode(m.coordinates(x));np.testing.assert_allclose(y[:,0],x[:,0])
    np.testing.assert_allclose(abs(np.sum(y[:,1:5]*x[:,1:5],axis=1)),1,atol=1e-14)
    x[0,1:5]=[0,1,0,0]
    with pytest.raises(ValueError,match='chart'):m.coordinates(x)


def test_nonlinear_features_and_inputs_are_not_raw_linear_model():
    m=api();x=state(2);x[:,8]=[-.2,.2]
    z=m.lift(x);assert z.shape[1]>11
    assert np.any(np.isclose(z[0],.04) & np.isclose(z[1],.04))
    a=np.array([[0,0,0,-2,0,0],[0,0,0,2,0,0.]])
    u=m.input_lift(a);assert u.shape==(2,12)
    np.testing.assert_array_equal(u[:,9],[4,4])


def test_latent_recurrence_does_not_relift_predicted_state():
    m=api();x=state();z=m.lift(x);dim=z.shape[1]
    A=np.eye(dim);B=np.zeros((dim,12))
    hidden=dim-2;A[4,hidden]=1;A[hidden,hidden]=.5
    z[0,hidden]=.1
    p=m.PreparedLifted(A,B,context())
    following=p.step(z,np.zeros((1,6)),context())
    np.testing.assert_allclose(following,z@A.T)
    again=p.step(following,np.zeros((1,6)),context())
    assert again[0,4]==pytest.approx(.15)
    assert abs(m.lift(m.decode(following[:,:10]))[0,hidden]-following[0,hidden])>1e-3
    with pytest.raises(ValueError,match='context'):
        p.step(z,np.zeros((1,6)),replace(context(),mass=99))


def test_zero_transition_fit_retains_identity_and_source_only_scaling():
    m=api();rng=np.random.default_rng(44);x=state(200)
    x[:,5:]=rng.uniform(-.1,.1,(200,6));a=rng.normal(size=(200,6))
    contexts=[context()]*len(x)
    r=m.fit_lifted(x,x,a,contexts,np.ones(len(x)),ridge=.001)
    p=m.prepare_lifted(r,context());z=m.lift(x)
    np.testing.assert_allclose(p.step(z,a,context()),z,atol=1e-13)
    altered=dict(r);altered['ridge']=.1
    with pytest.raises(ValueError,match='hash'):m.prepare_lifted(altered,context())


def test_height_translation_preserved_without_velocity_leak():
    m=api();rng=np.random.default_rng(4);x=state(100)
    x[:,5:]=rng.uniform(-.1,.1,(100,6));y=x.copy();y[:,0]+=.002
    r=m.fit_lifted(x,y,np.zeros((100,6)),[context()]*100,np.ones(100),ridge=.001)
    p=m.prepare_lifted(r,context());a=np.zeros((1,6));z=m.lift(x[:1])
    shifted=x[:1].copy();shifted[:,0]+=.2
    result=m.decode(p.step(m.lift(shifted),a,context())[:,:10])-m.decode(p.step(z,a,context())[:,:10])
    np.testing.assert_allclose(result[0,1:],0,atol=1e-12)
    assert result[0,0]==pytest.approx(.2)


def test_source_calibration_allows_smaller_positive_ridge_and_rejects_invalid():
    m=api();x=state(8);a=np.zeros((8,6));c=[context()]*8;w=np.ones(8)
    r=m.fit_lifted(x,x,a,c,w,ridge=1e-6)
    assert r['ridge']==1e-6
    for value in (0,-1,float('nan'),True):
        with pytest.raises(ValueError,match='fit_input'):m.fit_lifted(x,x,a,c,w,ridge=value)


def test_casadi_latent_step_matches_numpy_with_nonlinear_control_features():
    ca=pytest.importorskip('casadi');m=api();rng=np.random.default_rng(846)
    d=len(m.feature_names());A=np.eye(d)+rng.normal(0,.001,(d,d));B=rng.normal(0,.001,(d,12))
    p=m.PreparedLifted(A,B,context());z=ca.MX.sym('z',d);u=ca.MX.sym('u',6)
    f=ca.Function('lifted',[z,u],[p.symbolic_step(z,u)])
    latent=rng.normal(size=(3,d));a=rng.uniform(-2,2,(3,6))
    actual=np.stack([np.asarray(f(q,b)).ravel() for q,b in zip(latent,a)])
    np.testing.assert_allclose(actual,p.step(latent,a,context()),atol=1e-12)
