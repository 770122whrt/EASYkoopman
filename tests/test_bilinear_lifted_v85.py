import numpy as np
import pytest
from dataclasses import replace
from test_prepared_projected_v40 import context
from koopman import bilinear_lifted_v85 as m
from koopman import lifted_propagation_v84 as fixed


def state(n=1):
    x=np.zeros((n,11));x[:,0]=5.5;x[:,1]=1
    return x


def test_bilinear_velocity_square_exact_integrator_and_memory():
    d=len(m.feature_names());A=np.eye(d);B=np.zeros((d,12));N=np.zeros((6,d,d));dt=1/120
    v=m.feature_names().index('v_x');square=m.feature_names().index('v_x_square')
    B[v,0]=dt;B[square,6]=dt*dt;N[0,square,v]=2*dt
    p=m.PreparedBilinear(A=A,B=B,context=context(),N=N)
    assert isinstance(p,fixed.PreparedLifted)
    x=state();x[0,5]=.2;z=m.lift(x);a=np.array([[.7,0,0,0,0,0.]])
    y=p.step(z,a,context());assert y[0,v]==pytest.approx(.2+dt*.7)
    assert y[0,square]==pytest.approx((.2+dt*.7)**2)
    # Carry an intentionally inconsistent hidden coordinate to prove no re-lifting.
    z[0,square]=.3;y=p.step(z,a,context())
    assert y[0,square]==pytest.approx(.3+2*dt*.2*.7+dt*dt*.7**2)
    with pytest.raises(ValueError,match='context'):p.step(z,a,replace(context(),mass=99))


def test_zero_transition_fit_preserves_identity_and_hash():
    rng=np.random.default_rng(85);x=state(100);x[:,5:]=rng.uniform(-.1,.1,(100,6));a=rng.normal(size=(100,6))
    r=m.fit_bilinear(x,x,a,[context()]*100,np.ones(100),ridge=1e-4)
    p=m.prepare_bilinear(r,context());np.testing.assert_allclose(p.step(m.lift(x),a,context()),m.lift(x),atol=1e-13)
    assert r['audit']['interaction_columns']==216
    assert r['audit']['context_modulated_interactions'] is False
    bad=dict(r);bad['ridge']=.1
    with pytest.raises(ValueError,match='hash'):m.prepare_bilinear(bad,context())


def test_height_shift_cannot_modify_other_outputs_even_with_interactions():
    rng=np.random.default_rng(9);x=state(80);x[:,5:]=rng.uniform(-.1,.1,(80,6));a=rng.normal(size=(80,6));y=x.copy();y[:,5]+=.01*a[:,0]
    r=m.fit_bilinear(x,y,a,[context()]*80,np.ones(80),ridge=1e-4);p=m.prepare_bilinear(r,context())
    shifted=x.copy();shifted[:,0]+=.2
    delta=p.step(m.lift(shifted),a,context())-p.step(m.lift(x),a,context())
    np.testing.assert_allclose(delta[:,1:],0,atol=1e-12);np.testing.assert_allclose(delta[:,0],.2,atol=1e-12)


def test_nonzero_fit_coefficients_reconstruct_runtime_and_training_rmse():
    rng=np.random.default_rng(85);x=state(160);x[:,5:]=rng.uniform(-.15,.15,(160,6))
    a=rng.uniform(-1,1,(160,6));y=x.copy();y[:,5:]+=.01*a
    c=[context()]*80+[replace(context(),mass=15)]*80;w=np.linspace(1,2,160)
    r=m.fit_bilinear(x,y,a,c,w,ridge=1e-6);z=m.lift(x);u=m.input_lift(a)
    coefficients=np.asarray(r['coefficients']);inter=np.asarray(r['interaction_coefficients'])
    assert np.linalg.norm(inter)>0
    predicted=[];direct=[]
    for start in (0,80):
        ctx=c[start];zz=z[start:start+80];uu=u[start:start+80]
        q=np.r_[1,(m.descriptors(ctx)-np.asarray(r['context_mean']))/np.asarray(r['context_scale'])*np.asarray(r['context_varying'])]
        mapping=np.einsum('p,pij->ij',q,coefficients)
        direct.append(zz+np.c_[zz[:,1:],uu]@mapping+(uu[:,:6,None]*zz[:,None,1:-1]).reshape(80,-1)@inter.reshape(-1,len(m.feature_names())))
        predicted.append(m.prepare_bilinear(r,ctx).step(zz,a[start:start+80],ctx))
    pred=np.concatenate(predicted)
    np.testing.assert_allclose(pred,np.concatenate(direct),atol=1e-13,rtol=1e-12)
    np.testing.assert_allclose(np.sqrt((w/w.sum())@((pred-m.lift(y))**2)),r['audit']['training_lift_rmse'],atol=1e-13)


def test_symbolic_step_matches_numeric():
    ca=pytest.importorskip('casadi');d=len(m.feature_names());rng=np.random.default_rng(3)
    A=np.eye(d);B=rng.normal(size=(d,12))*.01;N=rng.normal(size=(6,d,d))*.01
    p=m.PreparedBilinear(A=A,B=B,context=context(),N=N)
    z=ca.MX.sym('z',d);a=ca.MX.sym('a',6);f=ca.Function('bilinear_parity',[z,a],[p.symbolic_step(z,a)])
    zv=rng.normal(size=(1,d));av=rng.normal(size=(1,6))
    np.testing.assert_allclose(np.array(f(zv[0],av[0])).ravel(),p.step(zv,av,context())[0],atol=1e-12)
