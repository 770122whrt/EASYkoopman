"""Pure deployment-backend allocation preview, before reserving a ticket."""
import numpy as np
import torch
from easyuuv_nc.thrust_allocation import allocate,control_channels_to_wrench
from koopman.feedback_preview_v79 import audit_observed_pwm
from koopman.rate30_v67 import ExecutionLedger


def backend_pwm(runtime,command):
    a=np.asarray(command,dtype=np.float32)
    if a.shape!=(4,) or not np.isfinite(a).all() or np.any(np.abs(a)>.95):
        raise ValueError('backend_command')
    virtual=torch.as_tensor(a,device=runtime.device).reshape(1,4)*runtime._control_mask_4
    if runtime._use_config_alloc:
        raw=allocate(runtime._alloc_B,control_channels_to_wrench(virtual*runtime._alloc_channel_sign),
                     mode=runtime._alloc_mode,weight=runtime._alloc_weight)
    else:
        r,p,y,z=virtual.unbind(-1)
        raw=torch.stack((-r-p+z,r-p+z,-r+p+z,r+p+z,y,-y,-y,y),dim=-1)
    pwm=torch.clamp(raw,-1,1)
    return dict(pwm_raw=raw.detach().cpu().numpy()[0].copy(),pwm=pwm.detach().cpu().numpy()[0].copy())


class BackendLedger(ExecutionLedger):
    def __init__(self,*args,backend_check,**kwargs):
        super().__init__(*args,**kwargs)
        self.backend_check=backend_check;self.backend_audit=[]

    def reserve(self,capture,command,*,source,startup=False):
        actual=self.backend_check(command)
        checked=audit_observed_pwm(actual['pwm_raw'],actual['pwm'])
        self.backend_audit.append(dict(physics_index=capture.physics_index,
            command=np.asarray(command,dtype=np.float32).copy(),**actual,**checked))
        if not checked['accepted']:raise ValueError('pre_dispatch_'+str(checked['reason']))
        return super().reserve(capture,command,source=source,startup=startup)
