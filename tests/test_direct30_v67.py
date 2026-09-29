import numpy as np
import pytest
import torch
from workflows.control_seam_v23 import ControlKernel

@pytest.mark.parametrize('configuration',['base','asymmetric','uuv4'])
def test_four_actual_substeps_hold_original_allocation(configuration):
    from easyuuv_nc.control_v67 import begin_interval,direct_pwm,reset_direct
    e=ControlKernel(configuration).env;e.cfg.control_input_mode='direct_pre_tam_v24';e.cfg.decimation=4;e.cfg.control_rate_hz_v67=30
    u=torch.tensor([[.03,-.04,.01,.04]])
    reset_direct(e,[0]);begin_interval(e,u)
    expected=ControlKernel(configuration).command(u,pre_tam=True)['pwm']
    for _ in range(4):np.testing.assert_allclose(direct_pwm(e).numpy()[0],expected,rtol=0,atol=1e-7)
    with pytest.raises(ValueError):direct_pwm(e)


def test_half_interval_cannot_be_replaced_or_relabelled():
    from easyuuv_nc.control_v67 import begin_interval,direct_pwm,reset_direct
    e=ControlKernel('base').env;e.cfg.control_input_mode='direct_pre_tam_v24';e.cfg.decimation=4;e.cfg.control_rate_hz_v67=30
    reset_direct(e,[0]);begin_interval(e,torch.zeros(1,4));direct_pwm(e);direct_pwm(e)
    with pytest.raises(ValueError):begin_interval(e,torch.ones(1,4)*.01)
    e.cfg.decimation=2
    with pytest.raises(ValueError):begin_interval(e,torch.zeros(1,4))
