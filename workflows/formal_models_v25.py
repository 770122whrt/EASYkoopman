"""Fixed model grid, causal trace reconstruction and strict operator loading."""
from dataclasses import dataclass,asdict,fields
import hashlib
import json
import numpy as np
from workflows.formal_contract_v25 import proposal,analysis_policy
from koopman.projected_edmd_v24 import PhysicalContext,Operator,observable,fit_operator,_readonly
from koopman.structured_edmd_v25 import StateOperator,fit_state_operator,remove_known_input


def json_value(value):
    def convert(item):
        if isinstance(item,np.ndarray):return item.tolist()
        if isinstance(item,np.generic):return item.item()
        raise TypeError(type(item).__name__)
    return json.loads(json.dumps(value,default=convert,allow_nan=False))


@dataclass
class Episode:
    case: dict
    trace_sha256: str
    states: np.ndarray
    acceleration: np.ndarray
    context: PhysicalContext


def model_specs():
    configs=proposal()['configurations']
    scopes=[('local-'+c,[c],[c]) for c in configs]+[('pooled',configs,configs)]
    scopes += [('heldout-'+c,[k for k in configs if k!=c],[c]) for c in configs]
    return [{'model_id':family+'__'+scope,'family':family,'scope':scope,
             'fit_configurations':train,'evaluation_configurations':evaluate}
            for family in analysis_policy()['families'] for scope,train,evaluate in scopes]


def reconstruct(data,case,source_commit,trace_sha256):
    from workflows.validate_formal_trace_v25 import validate_trace
    from workflows.control_seam_v23 import ControlKernel
    from workflows.pilot_control_v24 import commands
    from easyuuv_nc.control import ActuatorState
    validate_trace(data,case,source_commit)
    rows=data['substeps'];telemetry=rows[0]['before']['telemetry'];backend=rows[0]['before']['backend']
    context=PhysicalContext(float(np.asarray(backend['mass_kg']).item()),np.asarray(backend['inertia_9']).reshape(3,3).diagonal(),
                            np.asarray(telemetry['com_to_cob_offset_m'])[0],float(np.asarray(telemetry['volume_m3']).item()),
                            float(np.asarray(telemetry['drag_multiplier']).item()),telemetry['water_density_kg_m3'],telemetry['dynamic_viscosity_pa_s'],9.81)
    states=np.asarray([row['before']['state_11'][0] for row in rows]+[rows[-1]['state_after_physics_11'][0]])
    kernel=ControlKernel(case['configuration']);parameters=data['actuator_parameters']
    estimator=ActuatorState(parameters['count'],tau=parameters['tau_s'],dt=parameters['physics_dt_s'],clock=parameters['clock'])
    acceleration=[];factors=np.concatenate((np.full(3,context.mass),context.inertia))
    # Only the initial known-zero state and declared commands drive this sequence.
    # Actual state/actuator rows above are validation/training targets, never feedback here.
    for action in np.repeat(commands(case),2,axis=0):
        pwm=kernel.command(action,pre_tam=True)['pwm'];speed=estimator.advance_pwm(pwm)
        wrench=kernel.B.numpy()@(parameters['rotor_constant']*np.abs(speed)*speed)
        acceleration.append(wrench/factors)
    return Episode(case,trace_sha256,states,np.asarray(acceleration),context)


def training_matrices(spec,episodes):
    if spec not in model_specs():raise ValueError('formal_fit_spec')
    expected={case['run_id']:case for case in proposal()['entries']
              if case['role']=='fit' and case['configuration'] in spec['fit_configurations']}
    if (len(episodes)!=len(expected) or {e.case['run_id'] for e in episodes}!=set(expected)
            or any(e.case!=expected[e.case['run_id']] for e in episodes)):
        raise ValueError('formal_fit_role_inventory')
    ordered=sorted(episodes,key=lambda e:list(expected).index(e.case['run_id']))
    for episode in ordered:
        if (episode.states.shape!=(1025,11) or episode.acceleration.shape!=(1024,6)
                or not np.isfinite(episode.states).all() or not np.isfinite(episode.acceleration).all()):
            raise ValueError('formal_fit_episode_shape')
    dictionary,variant=spec['family'].split('_')
    if variant=='fixed':
        pairs=[remove_known_input(e.states[:-1],e.states[1:],e.acceleration,e.context,dictionary) for e in ordered]
    else:pairs=[(observable(e.states[:-1],e.context,dictionary),observable(e.states[1:],e.context,dictionary)) for e in ordered]
    a=np.concatenate([p[0] for p in pairs]);b=np.concatenate([p[1] for p in pairs]);u=np.concatenate([e.acceleration for e in ordered])
    return a,b,u,ordered


def fit_one(spec,episodes):
    a,b,u,ordered=training_matrices(spec,episodes)
    operator=fit_state_operator(a,b) if spec['family'].endswith('_fixed') else fit_operator(a,b,u)
    record=dict(spec,training_role='fit',status='fit_complete',
                fit_episode_hashes={e.case['run_id']:e.trace_sha256 for e in ordered},
                fit_matrix_sha256=hashlib.sha256(a.tobytes()+b.tobytes()+u.tobytes()).hexdigest(),operator=json_value(asdict(operator)))
    return record,operator


def load_operator(family,payload):
    if family not in analysis_policy()['families']:raise ValueError('formal_operator_family')
    dictionary,variant=family.split('_');dimension={'linear':25,'nonlinear':58}[dictionary]
    cls=StateOperator if variant=='fixed' else Operator
    if set(payload)!={field.name for field in fields(cls)}:raise ValueError('formal_operator_fields')
    shapes={'mean':(dimension,),'scale':(dimension,),'bias':(dimension,),
            'coefficient':(dimension if variant=='fixed' else dimension+6,dimension)}
    if variant=='free':shapes.update(input_mean=(6,),input_scale=(6,))
    converted={}
    for name,shape in shapes.items():
        value=np.asarray(payload[name],dtype=float)
        if value.shape!=shape or not np.isfinite(value).all():raise ValueError('formal_operator_shape_or_finite')
        if name.endswith('scale') and np.any(value<1e-6):raise ValueError('formal_operator_scale')
        converted[name]=_readonly(value)
    audit=payload['audit']
    if (audit.get('target_observables')!=dimension or audit.get('inputs')!=(0 if variant=='fixed' else 6)
            or audit.get('mean_ridge')!=.001 or not 1<=audit.get('regularized_condition',float('inf'))<=1e8
            or audit.get('fit_rows',0)<2):raise ValueError('formal_operator_audit')
    if variant=='fixed' and (audit.get('learned_force_coefficients')!=0 or audit.get('input_map')!='known_explicit_dtI_kick'
                            or audit.get('full_lift_operator') is not True):raise ValueError('formal_operator_known_force')
    converted['audit']=json_value(audit)
    return cls(**converted)
