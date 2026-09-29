from dataclasses import replace
import numpy as np
import pytest
from koopman.projected_edmd_v24 import PhysicalContext
from workflows.workpoint_v27 import mechanics
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
from koopman.physical_prediction_v29 import known_step


def context(name):
    m=mechanics(name)
    return PhysicalContext(m['mass_kg'],m['inertia_kg_m2'],m['cob_m'],m['volume_m3'],EMBODIMENT_CONFIGS[name]['drag_multiplier'])


@pytest.mark.parametrize('name,observed',[('uuv6',29.69999885559082),('uuv6_angled',31.680002212524414)])
def test_actual_mass_roundtrip_is_admitted_and_preserved_in_every_substep(name,observed):
    from koopman.command_prediction_v37 import forecast_commands,validate_context
    c=replace(context(name),mass=observed);validate_context(name,c);seen=[]
    def predict(x,a,passed):
        assert passed is c;seen.append((passed.mass,a.copy()))
        return known_step(x,a,passed,angular_damping=float(np.float32(.05)),gyroscopic=True)
    x=np.array([5.5,1,0,0,0,0,0,0,0,0,0.]);h=np.zeros((0,4));u=np.array([[0,0,0,.2]])
    r=forecast_commands(x,h,u,name,c,predict,origin_control=0)
    assert r['complete'] and len(seen)==2 and all(v[0]==observed for v in seen)
    from workflows.control_seam_v23 import ControlKernel
    k=ControlKernel(name)
    for i,speed in enumerate(r['rotor_speed']):
        wrench=k.B.numpy()@(k.env.cfg.rotor_constant*np.abs(speed)*speed)
        np.testing.assert_array_equal(r['acceleration'][i,:3],wrench[:3]/observed)


def test_other_nearby_values_and_wrong_context_are_rejected():
    from koopman.command_prediction_v37 import validate_context
    c=context('uuv6');observed=29.69999885559082
    for mass in (float(np.nextafter(observed,np.inf)),c.mass*1.000001,22.701000213623047):
        with pytest.raises(ValueError,match='command_context'):validate_context('uuv6',replace(c,mass=mass))
    with pytest.raises(ValueError,match='command_context'):validate_context('base',replace(c,mass=observed))
    with pytest.raises(ValueError,match='command_context'):validate_context('uuv6',replace(c,inertia=np.array(c.inertia)*1.01))


def test_roundtrip_context_branches_remain_independent_and_mask_is_preserved():
    from koopman.command_prediction_v37 import forecast_commands
    c=replace(context('uuv6'),mass=29.69999885559082);x=np.array([5.5,1,0,0,0,0,0,0,0,0,0.]);h=np.tile([0,0,0,.1],(4,1))
    def model(x,a,c):return known_step(x,a,c,angular_damping=float(np.float32(.05)),gyroscopic=True)
    def run(u,name='uuv6',ctx=c):return forecast_commands(x,h,np.asarray(u),name,ctx,model,origin_control=2)
    a=run([[0,0,0,.2]]);run([[.1,0,0,-.1]]);again=run([[0,0,0,.2]])
    for key in ('predictions','rotor_speed','acceleration','physics_time_s'):np.testing.assert_array_equal(a[key],again[key])
    masked=run([[0,0,.5,0]],'uuv4',context('uuv4'));assert not np.any(masked['applied_control'])
