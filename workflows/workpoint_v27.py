"""Known-plant static inversion for calibration; no trajectory or model fitting.

Commands still pass through the unchanged direct pre-TAM seam. A static inverse
is only a proposed input, never a hovering or continuous-data certificate.
"""
import ast
from functools import lru_cache
from pathlib import Path
import numpy as np
import torch
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, SUPPORTED_EMBODIMENTS, qualification_record
from workflows.control_seam_v23 import ControlKernel

EXPERIMENT = 'phase8.4-workpoint-calibration-v27-20260913'
ACCELERATION_TOLERANCE = np.array([.025, .025, .025, .1, .1, .1])
PULSE_ACCELERATION_4 = [4., 2., 1., .5]  # roll/pitch/yaw rad/s2; heave m/s2


@lru_cache(maxsize=1)
def _defaults():
    path = Path(__file__).resolve().parents[1] / 'easyuuv_nc/env/easyuuv_env.py'
    cls = next(n for n in ast.parse(path.read_text(encoding='utf8')).body
               if isinstance(n, ast.ClassDef) and n.name == 'EasyUUVEnvCfg')
    return {n.targets[0].id: ast.literal_eval(n.value) for n in cls.body
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id in ('volume', 'water_rho')}


def mechanics(name):
    if name not in SUPPORTED_EMBODIMENTS:
        raise ValueError('calibration_configuration')
    c = EMBODIMENT_CONFIGS[name]; d = _defaults()
    return {'mass_kg': float(np.float32(c['mass'])),
            'inertia_kg_m2': np.asarray(c['inertia_tensors'], dtype=np.float32).astype(float).tolist(),
            'volume_m3': float(np.float32(c.get('volume', d['volume']))),
            'cob_m': np.asarray(c['com_to_cob_offset'], dtype=np.float32).astype(float).tolist(),
            'water_density_kg_m3': float(d['water_rho']), 'gravity_m_s2': 9.81,
            'actuator_tau_s': c['dyn_time_constant'],
            'control_mask_4': list(qualification_record(name)['control_mask'])}


def required_wrench(m):
    buoyancy = m['water_density_kg_m3'] * m['volume_m3'] * m['gravity_m_s2']
    return np.r_[0., 0., m['mass_kg'] * m['gravity_m_s2'] - buoyancy,
                 -np.cross(m['cob_m'], [0., 0., buoyancy])]


def _steady(kernel, u):
    sent = kernel.command(u, pre_tam=True)
    speed = kernel.pwm_speed(torch.as_tensor(sent['pwm']).reshape(1, -1)).numpy()[0]
    wrench = kernel.B.numpy() @ (kernel.env.cfg.rotor_constant * np.abs(speed) * speed)
    return wrench.astype(float), sent


def _inverse_force(force, coefficient):
    """Monotone signed PWM curve, keeping the zero/deadzone alternatives."""
    target = np.sign(force) * np.sqrt(np.abs(force) / coefficient)
    def speed(p):
        if p >= .02: return -139*p*p + 500*p + 8.28
        if p <= -.02: return 161*p*p + 517.86*p - 5.72
        return 0.
    lo, hi = -1., 1.
    for _ in range(48):
        mid = (lo + hi) / 2
        if speed(mid) < target: lo = mid
        else: hi = mid
    return min((lo, hi, 0.), key=lambda p: abs(speed(p) - target))


def solve_control(name, target):
    m = mechanics(name); target = np.asarray(target, dtype=float)
    if target.shape != (6,) or not np.isfinite(target).all():
        raise ValueError('calibration_target_invalid')
    active = np.flatnonzero(m['control_mask_4'])
    if not m['control_mask_4'][2] and target[5] != 0:
        raise ValueError('calibration_uncontrollable_yaw')
    kernel = ControlKernel(name)
    scale = np.r_[[m['mass_kg']]*3, m['inertia_kg_m2']]
    allocation = np.stack([kernel.command(np.eye(4)[j], pre_tam=True)['pwm_raw'] for j in active], axis=1)
    force = np.linalg.lstsq(kernel.B.numpy(), target, rcond=None)[0]
    pwm = [_inverse_force(f, kernel.env.cfg.rotor_constant) for f in force]
    u = np.zeros(4); u[active] = np.linalg.lstsq(allocation, pwm, rcond=None)[0]
    u = np.clip(u, -.95, .95)
    def residual(command): return (_steady(kernel, command)[0] - target) / scale
    steps = 0
    # Bounded deterministic Newton inversion of the known curve; no data input.
    # Deadzone has flat/discontinuous pieces: a nonconverged residual is retained.
    for steps in range(64):
        r = residual(u)
        if np.max(np.abs(r)) < 1e-6: break
        h = 1e-3
        jac = np.stack([(residual(np.clip(u + np.eye(4)[j]*h, -.95, .95))
                         - residual(np.clip(u - np.eye(4)[j]*h, -.95, .95))) / (2*h)
                        for j in active], axis=1)
        delta = np.linalg.lstsq(jac, -r, rcond=1e-8)[0]
        candidates = [u.copy()]
        for fraction in (1., .5, .25, .125, .0625):
            v = u.copy(); v[active] += fraction * delta
            candidates.append(np.clip(v, -.95, .95))
        best = min(candidates, key=lambda v: np.linalg.norm(residual(v)))
        if np.array_equal(best, u): break
        u = best
    # Freeze the exact float32 commands consumed by the native collector.
    u = u.astype(np.float32); wrench, sent = _steady(kernel, u)
    if not np.any(wrench):
        u = np.zeros(4, dtype=np.float32); wrench, sent = _steady(kernel, u)
    error = (wrench - target) / scale
    margin = float(1 - np.max(np.abs(sent['pwm_raw'])))
    return {'command_4': u.astype(float).tolist(), 'target_wrench_6_n_nm': target.tolist(),
            'steady_wrench_6_n_nm': wrench.tolist(), 'acceleration_error_6': error.tolist(),
            'pwm_raw': sent['pwm_raw'].astype(float).tolist(), 'pwm_headroom': margin,
            'within_tolerance': bool(np.all(np.abs(error) <= ACCELERATION_TOLERANCE) and margin >= .05),
            'exact_equilibrium': bool(np.max(np.abs(error)) < 1e-6), 'iterations': steps + 1}


def calibrate(name):
    m = mechanics(name); target = required_wrench(m)
    trim = solve_control(name, target); pulses = []
    for axis, acceleration in enumerate(PULSE_ACCELERATION_4):
        if not m['control_mask_4'][axis]:
            pulses.append({'minus': trim, 'plus': trim, 'masked': True}); continue
        index = (3, 4, 5, 2)[axis]
        scale = m['mass_kg'] if index == 2 else m['inertia_kg_m2'][index - 3]
        delta = np.zeros(6); delta[index] = acceleration * scale
        pulses.append({'minus': solve_control(name, target - delta),
                       'plus': solve_control(name, target + delta), 'masked': False})
    return {'configuration': name, 'mechanics': m, 'trim': trim, 'pulses': pulses,
            'pulse_acceleration_4': PULSE_ACCELERATION_4,
            'all_static_targets_supported': bool(trim['within_tolerance'] and all(
                p[s]['within_tolerance'] for p in pulses for s in ('minus', 'plus'))),
            'method': 'known_source_steady_map_inverse_v1', 'model_fits': 0,
            'limits': 'Upright zero-speed static inverse only; no runtime feedback, no prewarmed rotor, no hovering claim.'}


def cases():
    return [{'run_id': f'c27-{name}-{stage}-{seed+i}', 'configuration': name,
             'stage': stage, 'seed': seed+i, 'intervals': n, 'role': 'calibration',
             'training_eligible': False, 'starting_z_m': 5.5, 'mode': 'direct_pre_tam_v24'}
            for stage, seed, n in [('trim', 8510, 128), ('excitation', 8520, 256)]
            for i, name in enumerate(SUPPORTED_EMBODIMENTS)]


def validate_case(q):
    if q not in cases(): raise ValueError('calibration_fixed_case')
    return q


def validate_calibration(c):
    name = c['configuration']; m = mechanics(name); target = required_wrench(m)
    if (c['mechanics'] != m or c['pulse_acceleration_4'] != PULSE_ACCELERATION_4
            or c['model_fits'] != 0 or len(c['pulses']) != 4):
        raise ValueError('calibration_static_contract')
    kernel = ControlKernel(name); scale = np.r_[[m['mass_kg']]*3, m['inertia_kg_m2']]
    records = [(c['trim'], target)]
    for axis, p in enumerate(c['pulses']):
        masked = not bool(m['control_mask_4'][axis])
        if p['masked'] != masked: raise ValueError('calibration_static_mask')
        index = (3, 4, 5, 2)[axis]; delta = np.zeros(6)
        if not masked: delta[index] = PULSE_ACCELERATION_4[axis]*scale[index]
        records.extend([(p['minus'], target-delta), (p['plus'], target+delta)])
    supported = []
    for record, desired in records:
        u = np.asarray(record['command_4'], dtype=float)
        if (u.shape != (4,) or not np.isfinite(u).all() or np.any(np.abs(u) > .95)
                or np.any(u[np.asarray(m['control_mask_4']) == 0])):
            raise ValueError('calibration_static_command')
        wrench, sent = _steady(kernel, u); error = (wrench-desired)/scale
        margin = float(1-np.max(np.abs(sent['pwm_raw'])))
        passed = bool(np.all(np.abs(error) <= ACCELERATION_TOLERANCE) and margin >= .05)
        # CPU LAPACK/torch float32 allocation differs at ~6e-6 N across hosts.
        # Only serialized arithmetic summaries use 1e-5; physical gates are
        # still recomputed above with the original, unchanged tolerances.
        for value, expected, atol in ((record['target_wrench_6_n_nm'], desired, 1e-6),
                                (record['steady_wrench_6_n_nm'], wrench, 1e-5),
                                (record['acceleration_error_6'], error, 1e-5),
                                (record['pwm_raw'], sent['pwm_raw'], 1e-6),
                                (record['pwm_headroom'], margin, 1e-6)):
            if not np.allclose(value, expected, rtol=0, atol=atol):
                raise ValueError('calibration_static_reconstruction')
        if record['within_tolerance'] is not passed: raise ValueError('calibration_static_gate')
        supported.append(passed)
    if c['all_static_targets_supported'] is not all(supported): raise ValueError('calibration_static_gate')
    return c


def commands(q, calibration):
    validate_case(q)
    validate_calibration(calibration)
    if (calibration['configuration'] != q['configuration']
            or calibration['trim']['within_tolerance'] is not True):
        raise ValueError('calibration_static_trim_rejected')
    a = np.tile(calibration['trim']['command_4'], (q['intervals'], 1)).astype(np.float32)
    if q['stage'] == 'excitation':
        if calibration['all_static_targets_supported'] is not True:
            raise ValueError('calibration_static_pulse_rejected')
        rng = np.random.default_rng(q['seed'])
        for axis, p in enumerate(calibration['pulses']):
            first = 'plus' if rng.integers(2) else 'minus'
            second = 'minus' if first == 'plus' else 'plus'
            start = 64 + 48*axis
            a[start:start+12] = p[first]['command_4']
            a[start+24:start+36] = p[second]['command_4']
    return a
