"""Reconstruct prediction inputs using commands alone, not future telemetry."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from workflows.control_seam_v23 import ControlKernel
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from workflows.identify_sparse_world_v30 import load_fit_cache
from koopman.command_prediction_v37 import validate_context


def replay_inputs(configuration,context,commands,*,origin,horizon):
    drive=np.asarray(commands,dtype=float)
    if (drive.ndim!=2 or drive.shape[1]!=4 or not np.isfinite(drive).all()
            or np.any(abs(drive)>.95) or type(origin) is not int or type(horizon) is not int
            or origin<0 or origin%2 or horizon<1 or origin+horizon>len(drive)):
        raise ValueError('causal_replay_input')
    used=drive[:origin+horizon].astype(np.float32)
    if not np.array_equal(used[1::2],used[:len(used)//2*2:2]):raise ValueError('causal_replay_hold')
    validate_context(configuration,context)
    kernel=ControlKernel(configuration)
    actuator=Float32PWMActuatorState(kernel.env._num_thrusters,tau=kernel.tau,dt=1/120,
                                    clock='float32_accumulated_v1')
    scale=np.r_[[context.mass]*3,context.inertia];result=[]
    for i,command in enumerate(used):
        speed=actuator.advance_pwm(kernel.command(command,pre_tam=True)['pwm'])
        if i>=origin:
            result.append((kernel.B.numpy()@(kernel.env.cfg.rotor_constant*abs(speed)*speed))/scale)
    return np.asarray(result)


def run(root,output):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();rows=[]
    for e in load_fit_cache(root):
        if time.monotonic()-started>180:raise TimeoutError('causal_replay_budget')
        # Reset/history origin is the certified zero-rotor fit trace. Neither
        # cached rotor speeds nor measured states are passed into reconstruction.
        a=replay_inputs(e.case['configuration'],e.context,e.arrays['issued_control'],origin=0,horizon=640)
        delta=abs(a-e.acceleration)
        rows.append(dict(configuration=e.case['configuration'],episode=e.case['run_id'],
            source_trace_sha256=e.trace_sha256,max_component_difference=float(delta.max()),
            component_max_difference=delta.max(axis=0).tolist(),passed=bool(np.all(delta<=1e-8))))
    result=dict(status='passed' if all(r['passed'] for r in rows) else 'failed',
        tolerance_acceleration=1e-8,rows=rows,seconds=time.monotonic()-started,
        uses_future_states=False,uses_future_rotor_telemetry=False,
        known_plan='historical issued commands supplied as replay plan',
        original_hold_physics=2,new_30Hz_control_claim=False,physics_runs=0,model_fits=0)
    (output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(Path('.'),a.output)
