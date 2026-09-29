"""Fresh-role samples with ordered physics inputs and command-only rotor memory."""
from dataclasses import dataclass
from pathlib import Path
import copy
import hashlib
import json
import re
import numpy as np
from koopman.projected_edmd_v24 import PhysicalContext, _readonly
from workflows.actuator_replay_v28 import Float32PWMActuatorState
from workflows.control_seam_v23 import ControlKernel
from workflows.identification_protocol_v29 import validate_case


def causal_arrays(data,kernel):
    """Array extraction only. Public adapt_trace performs full acceptance first."""
    rows=data['substeps'];ds=data['decisions'];start=data['observed_start_boundary']
    count=kernel.env._num_thrusters
    initial=np.asarray(start['actuator_speed_n'],dtype=float)
    if initial.shape!=(1,count) or np.any(initial) or not rows or len(rows)!=2*len(ds):
        raise ValueError('identification_history_initial_or_count')
    commands=np.asarray([d['command_4'] for d in ds],dtype=np.float32)
    if commands.shape!=(len(ds),4) or not np.isfinite(commands).all() or np.any(np.abs(commands)>.95):
        raise ValueError('identification_commands')
    if [d['interval'] for d in ds]!=list(range(len(ds))):raise ValueError('identification_decision_order')
    states=[np.asarray(start['state_11'],dtype=float)[0]]
    issued=np.repeat(commands,2,axis=0);pwms=[];speeds=[np.zeros(count)];wrenches=[];times=[0.]
    estimator=Float32PWMActuatorState(count,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
    for i,row in enumerate(rows):
        before=np.asarray(row['before']['state_11'],dtype=float)
        after=np.asarray(row['state_after_physics_11'],dtype=float)
        if (row['control_index']!=i//2 or row['reset_generation']!=[1]
                or before.shape!=(1,11) or after.shape!=(1,11)
                or not np.isfinite(before).all() or not np.isfinite(after).all()
                or not np.allclose(before[0],states[-1],rtol=0,atol=1e-6)):
            raise ValueError('identification_history_continuity')
        sent=kernel.command(issued[i],pre_tam=True);speed=estimator.advance_pwm(sent['pwm'])
        states.append(after[0]);pwms.append(sent['pwm']);speeds.append(speed);times.append(estimator.elapsed_time)
        wrenches.append(kernel.B.numpy()@(kernel.env.cfg.rotor_constant*np.abs(speed)*speed))
    return {k:_readonly(v) for k,v in {'states':states,'issued_control':issued,'pwm':pwms,
                                      'causal_rotor_speed':speeds,'actuator_time_s':times,'wrench':wrenches}.items()}


@dataclass(frozen=True)
class Episode:
    case:dict
    source_commit:str
    trace_sha256:str
    arrays:dict
    acceleration:np.ndarray
    context:PhysicalContext
    acceptance:dict

    @property
    def states(self):return self.arrays['states']


def adapt_trace(data,case,source,trace_sha256,source_root):
    validate_case(case)
    if (data.get('status')!='completed_identification_pending_acceptance'
            or data.get('request')!=case or data.get('training_eligible') is not False
            or not re.fullmatch('[0-9a-f]{40}',source) or not re.fullmatch('[0-9a-f]{64}',trace_sha256)):
        raise ValueError('identification_adapter_identity')
    from workflows.validate_identification_v29 import validate_trace
    check=validate_trace(data,case,source,source_root)
    arrays=causal_arrays(data,ControlKernel(case['configuration']))
    telemetry=data['substeps'][0]['before']['telemetry'];backend=data['substeps'][0]['before']['backend']
    context=PhysicalContext(float(np.asarray(backend['mass_kg']).item()),
        np.asarray(backend['inertia_9']).reshape(3,3).diagonal(),np.asarray(telemetry['com_to_cob_offset_m'])[0],
        float(np.asarray(telemetry['volume_m3']).item()),float(np.asarray(telemetry['drag_multiplier']).item()),
        telemetry['water_density_kg_m3'],telemetry['dynamic_viscosity_pa_s'],9.81)
    acceleration=_readonly(arrays['wrench']/np.r_[[context.mass]*3,context.inertia])
    return Episode(copy.deepcopy(case),source,trace_sha256,arrays,acceleration,context,check)


def load_episode(path,case,source,expected_sha256,source_root):
    payload=Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=expected_sha256:raise ValueError('identification_trace_hash')
    return adapt_trace(json.loads(payload),case,source,expected_sha256,source_root)
