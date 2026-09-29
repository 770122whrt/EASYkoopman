"""Frozen known mechanics and deterministic static control inversion."""
import ast
from functools import lru_cache
from pathlib import Path
import numpy as np
import torch
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, SUPPORTED_EMBODIMENTS, qualification_record
from workflows.control_kernel import ControlKernel
ACCELERATION_TOLERANCE=np.array([.025,.025,.025,.1,.1,.1])

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
