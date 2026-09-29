"""Admission and causal inputs for fresh disturbance traces, separate from fitting."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS
from koopman.projected_edmd_v24 import PhysicalContext
from koopman.physical_control_v76 import PhysicalPredictor
from workflows.identify_sparse_world_v30 import from_record
from workflows.workpoint_v27 import mechanics
from workflows.protocol_v86 import cases, protocol, excitation

ROOT=Path(__file__).resolve().parents[1]
PHYSICAL_PATH='docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion/pooled__physical.json'
PHYSICAL_SHA256='82d7f0c1c20faa3299d5b3f9f81a64c5a66888c255a6ceb953bba5384c8cd0f3'


def context():
    m=mechanics('base')
    return PhysicalContext(m['mass_kg'],m['inertia_kg_m2'],m['cob_m'],m['volume_m3'],
                           EMBODIMENT_CONFIGS['base']['drag_multiplier'])


def frozen_physics():
    payload=(ROOT/PHYSICAL_PATH).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=PHYSICAL_SHA256:raise ValueError('v86_frozen_physics_changed')
    record=json.loads(payload)
    return record,PhysicalPredictor(from_record(record),context(),identified=True)


def verify_manifest(path,*,spec=None):
    expected_protocol=protocol() if spec is None else spec.protocol()
    payload=Path(path).read_bytes();m=json.loads(payload)
    if m['protocol']!=expected_protocol or m['physical_sha256']!=PHYSICAL_SHA256:
        raise ValueError('v86_manifest_protocol')
    required={'easyuuv_nc/env/easyuuv_env.py','easyuuv_nc/disturbance_v86.py',
              'workflows/collect_disturbance_data_v86.py','workflows/protocol_v86.py',
              'easyuuv_nc/data/embodiment/embodiment.usd'}
    if spec is not None:required.update({'workflows/protocol_v87.py','workflows/collect_disturbance_data_v87.py'})
    if not required<=set(m['files']):raise ValueError('v86_manifest_sources')
    for name,digest in m['files'].items():
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('v86_manifest_source:'+name)
    frozen_physics()
    return hashlib.sha256(payload).hexdigest()


def validate_trace(report, receipt, manifest_sha,*,spec=None):
    try:
        inventory=cases() if spec is None else spec.cases()
        version='v86' if spec is None else spec.VERSION
        q=report['case'];rows=report['substeps']
        if (report['schema']!='disturbance-data-'+version or q not in inventory
                or report['status']!='completed_pending_independent_acceptance'
                or receipt['native_exit']!=0 or receipt['trace_sha256']!=report['_file_sha256']
                or report['source_manifest_sha256']!=manifest_sha
                or report['cleanup_errors'] or not report['cleanup_completed']['environment']
                or not report['cleanup_completed']['simulation_app'] or len(rows)!=4*q['controls']
                or report['effective_hidden_drag_fraction']!=q['hidden_drag_fraction']):
            raise ValueError('identity_or_completion')
        from workflows.runtime_episode_v59 import check_runtime_context
        from workflows.calibration_trace_v27 import domain_screen
        from workflows.validate_control_trace_v23 import compare_values, validate_clock_step
        from workflows.control_seam_v23 import ControlKernel
        from workflows.actuator_replay_v28 import Float32PWMActuatorState
        from workflows.feedback_v31 import validate_decision
        from koopman.lifted_propagation_v84 import coordinates
        from koopman.physical_terms_v26 import state_terms
        from workflows.validate_effects_v67 import check_state_backend,validate_interval
        start=report['observed_start_boundary'];c=context()
        check_runtime_context(start,'base',c)
        compare_values(start['state_11'][0],[5.5,1,0,0,0,0,0,0,0,0,0])
        if np.any(start['actuator_speed_n']):raise ValueError('nonzero_initial_rotors')
        if len(report['decisions'])!=q['controls']:raise ValueError('decision_count')
        signal=excitation(q) if spec is None else spec.excitation(q)
        kernel=ControlKernel('base')
        actuator=Float32PWMActuatorState(kernel.env._num_thrusters,tau=kernel.tau,dt=1/120,clock='float32_accumulated_v1')
        scale=np.r_[[c.mass]*3,c.inertia];x=[start['state_11'][0]];inputs=[];commands=[]
        for i,row in enumerate(rows):
            j=i//4;decision=report['decisions'][j]
            if (row['control_index']!=j or row['substep_index']!=i%4
                    or row['reset_generation']!=[1] or row['physics_dt_s']!=1/120):
                raise ValueError('clock_or_reset')
            compare_values(row['before']['state_11'][0],x[-1])
            check_state_backend(row['before']['state_11'],row['before']['backend'])
            check_state_backend(row['state_after_physics_11'],row['backend_after_physics'])
            validate_clock_step([0] if i==0 else rows[i-1]['actuator_update']['end_time_s'],
                                row['actuator_update']['end_time_s'])
            if not np.isclose(row['backend_after_physics']['cache_sim_timestamp_s']-
                              row['before']['backend']['cache_sim_timestamp_s'],1/120,rtol=0,atol=1e-12):
                raise ValueError('physics_sample_time')
            if i%4==0 and not validate_decision(decision,np.asarray(x[-1]),signal[j],'base'):
                raise ValueError('causal_collection_decision')
            if i%4==0:validate_interval(rows[i:i+4],configuration='base')
            check_runtime_context(row['before'],'base',c)
            if not domain_screen(row,report['geometry'],5.5)['screen_pass']:raise ValueError('motion_or_contact')
            command=np.asarray(decision['command_4'],dtype=np.float32)
            if np.any(abs(command)>.95):raise ValueError('command_bound')
            sent=kernel.command(command,pre_tam=True);t=row['command']['telemetry']
            np.testing.assert_allclose(sent['virtual_control'],t['virtual_control_4'][0],rtol=0,atol=1e-6)
            np.testing.assert_allclose(sent['pwm'],t['motor_pwm_n'][0],rtol=0,atol=1e-6)
            speed=actuator.advance_pwm(sent['pwm'])
            np.testing.assert_allclose(speed,row['command']['actuator_speed_n'][0],rtol=1e-5,atol=2e-4)
            audit=row['command']['_disturbance_audit_v86']
            if audit['fraction']!=q['hidden_drag_fraction']:raise ValueError('disturbance_not_applied')
            quadratic=state_terms(np.asarray(x[-1])[None],c)['quadratic_drag']*scale
            np.testing.assert_allclose(audit['quadratic_wrench_b'],quadratic,rtol=1e-5,atol=1e-4)
            np.testing.assert_allclose(audit['extra_wrench_b'],q['hidden_drag_fraction']*quadratic,rtol=1e-5,atol=1e-4)
            # Inputs are computed only from issued commands and frozen mechanics.
            inputs.append((kernel.B.numpy()@(kernel.env.cfg.rotor_constant*abs(speed)*speed))/scale)
            commands.append(command);x.append(row['state_after_physics_11'][0])
        x=np.asarray(x);coordinates(x)
        return dict(case=q,states=x,inputs=np.asarray(inputs),commands=np.asarray(commands),
                    trace_sha256=report['_file_sha256'])
    except (KeyError,TypeError,IndexError,AssertionError,ValueError) as exc:
        raise ValueError('v86_trace:'+str(exc)) from exc


def load_episode(directory,manifest_sha,*,spec=None):
    directory=Path(directory);p=directory/'trace.json.gz'
    with gzip.open(p,'rt',encoding='utf8') as f:report=json.load(f)
    report['_file_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    receipt=json.loads((directory/'native-exit.json').read_text())
    return validate_trace(report,receipt,manifest_sha,spec=spec)
