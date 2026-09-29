"""New formal catalog. Importing a protocol never authorizes collection."""
import hashlib
import json

import numpy as np

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from workflows.workpoint_v27 import mechanics

EXPERIMENT = 'phase8.4-projected-formal-v38'
ROLES = ('preflight', 'validation', 'test')


def cases(role=None):
    if role is not None and role not in ROLES:
        raise ValueError('formal_role')
    result = []
    for stage, seed0 in zip(ROLES, (9300, 9400, 9500)):
        families = ('prbs',) if stage == 'preflight' else ('prbs', 'multisine', 'chirp')
        for i, configuration in enumerate(SUPPORTED_EMBODIMENTS):
            for j, excitation in enumerate(families):
                seed = seed0 + len(families) * i + j
                result.append(dict(run_id=f'p38-{configuration}-{stage}-{seed}-{excitation}',
                    configuration=configuration, role=stage, seed=seed, excitation=excitation,
                    intervals=256 if stage == 'preflight' else 512, training_eligible=False,
                    starting_z_m=5.5, mode='direct_pre_tam_v24'))
    return result if role is None else [q for q in result if q['role'] == role]


def validate_case(q):
    if (not isinstance(q, dict) or type(q.get('seed')) is not int
            or type(q.get('intervals')) is not int or q.get('training_eligible') is not False
            or q not in cases()):
        raise ValueError('formal_case')
    return q


def protocol():
    return dict(experiment=EXPERIMENT, version='projected-formal-v38', cases=cases(),
        physics_dt_s=1/120, control_dt_s=1/60, startup_control_intervals=128,
        pulse_acceleration_4=[2., 1., .5, .25],
        excitation=dict(reference_excitation_intervals=192, prbs_pair_intervals=24,
            prbs_sign_intervals=12, prbs_first_four_pairs='seed_permuted_signed_hadamard4',
            multisine_reference_cycles_by_axis=[[1+j, 3+j, 5+j] for j in range(4)],
            chirp_reference_cycles_start_end_by_axis=[[1+j/4, 4+j] for j in range(4)],
            frequency_rule='fixed_physical_frequency_band_not_fixed_episode_cycle_count'),
        initialization='identity_pose_zero_velocity_zero_rotors_complete_history',
        model_fits=0, model_handoff=False,
        stage_access=dict(preflight='new_explicit_D23_bound_to_source_protocol_models_and_budget',
            validation='accepted_complete_eight_preflight',
            test='accepted_validation_and_recomputed_fixed_gate_GO_with_exact_source_model_data_binding'),
        resource_cap=dict(collector_seconds=5400, native_case_seconds=300, native_cases=56,
            analysis_seconds=3600, analysis_processes=4, disk_bytes=4*1024**3))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def pulse(q):
    validate_case(q)
    p = protocol()
    n = q['intervals'] - 128
    result = np.zeros((q['intervals'], 4), dtype=np.float32)
    rng = np.random.default_rng(q['seed'])
    phase = rng.uniform(-np.pi, np.pi, size=(4, 3))
    reference_time = np.arange(n, dtype=float) / 192
    if q['excitation'] == 'prbs':
        hadamard = np.array([[1,1,1,1], [1,-1,1,-1], [1,1,-1,-1], [1,-1,-1,1]])
        pairs = rng.choice([-1., 1.], size=((n+23)//24, 4))
        pairs[:4] = hadamard[rng.permutation(4)] * rng.choice([-1., 1.], size=4)
    for axis, amplitude in enumerate(p['pulse_acceleration_4']):
        if not mechanics(q['configuration'])['control_mask_4'][axis]:
            continue
        if q['excitation'] == 'prbs':
            signs = pairs[:, axis]
            value = np.repeat(np.column_stack((signs, -signs)).reshape(-1), 12)[:n]
        elif q['excitation'] == 'multisine':
            cycles = np.asarray(p['excitation']['multisine_reference_cycles_by_axis'][axis])
            value = np.sin(2*np.pi*reference_time[:, None]*cycles + phase[axis]).mean(1)
        else:
            low, high = p['excitation']['chirp_reference_cycles_start_end_by_axis'][axis]
            value = np.sin(2*np.pi*reference_time*(low + .5*(high-low)*np.arange(n)/n) + phase[axis, 0])
        result[128:, axis] = amplitude * value
    return result


def guarded_exit_code(native_exit, report, request, source):
    if type(native_exit) is not int:
        return 1
    if native_exit:
        return native_exit if native_exit > 0 else 128-native_exit
    try:
        validate_case(request)
        validate_case(report['request'])
    except (ValueError, KeyError, TypeError):
        return 1
    if (report.get('status') != 'completed_identification_pending_acceptance'
            or report.get('request') != request or report.get('source_commit') != source
            or report.get('training_eligible') is not False
            or type(report.get('model_fits')) is not int or report['model_fits'] != 0):
        return 1
    return 0
