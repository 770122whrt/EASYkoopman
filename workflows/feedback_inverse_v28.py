"""Bounded source-map refinement when a deadzone blocks a full Newton step.

Retains the original feasibility limits and numerically robust feasible solutions.
No rollout data, fit or relaxed physical tolerances enter the algorithm.
"""
import itertools
import numpy as np
import torch
from workflows.workpoint_v27 import solve_control, mechanics, _steady, ACCELERATION_TOLERANCE
from workflows.control_seam_v23 import ControlKernel

MINIMUM_DEADZONE_DISTANCE = 2e-6


def deadzone_distance(raw):
    return float(np.min(np.abs(np.abs(np.asarray(raw, dtype=float))-float(np.float32(.02)))))


def batch_source_map(kernel, commands):
    """Vectorize the actual source PID-disabled PWM statements, not a new map."""
    value = torch.as_tensor(commands, dtype=torch.float32)
    if value.ndim != 2 or value.shape[1] != 4 or not torch.isfinite(value).all() or torch.any(value.abs()>1):
        raise ValueError('feedback_batch_command')
    saved = kernel.env.cfg.cascade_control; count = kernel.env.num_envs
    kernel.env.cfg.cascade_control = False; kernel.env.num_envs = len(value)
    try:
        pwm = kernel.env._pid_control(value, torch.zeros_like(value), torch.zeros_like(value))
        raw = kernel.env._last_motor_values_raw.numpy().copy()
    finally:
        kernel.env.cfg.cascade_control = saved; kernel.env.num_envs = count
    speed = kernel.pwm_speed(pwm)
    wrench = (kernel.env.cfg.rotor_constant*speed.abs()*speed) @ kernel.B.T
    return wrench.numpy(), raw


def solve_feasible_control(name, target):
    original = solve_control(name, target)
    if original['within_tolerance'] and deadzone_distance(original['pwm_raw']) > MINIMUM_DEADZONE_DISTANCE:
        return original
    m = mechanics(name); target = np.asarray(target, dtype=float)
    active = np.flatnonzero(m['control_mask_4']); kernel = ControlKernel(name)
    scale = np.r_[[m['mass_kg']]*3, m['inertia_kg_m2']]
    u = np.asarray(original['command_4'], dtype=float)
    mapping = np.stack([kernel.command(np.eye(4)[j], pre_tam=True)['pwm_raw'] for j in active], axis=1)
    def residual(v): return (_steady(kernel, v)[0]-target)/scale/ACCELERATION_TOLERANCE
    def objective(v):
        r = residual(v)
        raw = kernel.command(v, pre_tam=True)['pwm_raw']
        if (np.max(np.abs(raw)) > .95 or deadzone_distance(raw) <= MINIMUM_DEADZONE_DISTANCE):
            return (float('inf'), float('inf'))
        return (float(np.max(np.abs(r))), float(np.linalg.norm(r)))
    u = min([u]+[np.clip(u*f,-.95,.95) for f in (1.0002,.9998,1.001,.999)], key=objective)
    masks = [np.ones(len(active))]
    masks += [1-row for row in np.eye(len(active))]
    masks += list(np.eye(len(active)))
    for iteration in range(48):
        r = residual(u)
        if objective(u)[0] <= 1: break
        h = 1e-3
        jac = np.stack([(residual(np.clip(u+np.eye(4)[j]*h,-.95,.95))
                         -residual(np.clip(u-np.eye(4)[j]*h,-.95,.95)))/(2*h)
                        for j in active], axis=1)
        delta = np.linalg.lstsq(jac, -r, rcond=1e-8)[0]
        candidates = [u.copy()]
        for mask in masks:
            for fraction in (1., .5, .25, .125, .0625):
                v = u.copy(); v[active] += fraction*delta*mask
                candidates.append(np.clip(v,-.95,.95))
        # The PWM map is piecewise smooth. Include nearest physical deadzone
        # boundaries as escape candidates, without modifying the deadzone.
        raw = kernel.command(u, pre_tam=True)['pwm_raw']
        for row, pwm in zip(mapping, raw):
            norm = float(row@row)
            if norm == 0: continue
            for edge in (-.020004, -.019996, .019996, .020004):
                v = u.copy(); v[active] += (edge-pwm)*row/norm
                candidates.append(np.clip(v,-.95,.95))
        best = min(candidates, key=objective)
        if np.array_equal(best, u): break
        u = best
    # Crossing several adjacent deadzone faces can require a coordinated
    # perturbation even when every one-dimensional step is worse. These two
    # fixed local grids are bounded (at most 2*5**4 candidates), source-only,
    # and run only after the block refinement cannot satisfy the old gates.
    for step in (.001, .005):
        if objective(u)[0] <= 1: break
        candidates = [u.copy()]
        for offsets in itertools.product((-2*step,-step,0.,step,2*step), repeat=len(active)):
            v=u.copy();v[active]+=offsets;candidates.append(np.clip(v,-.95,.95))
        u = min(candidates, key=objective)
    dense_points = 0
    if objective(u)[0] > 1:
        # Common bounded search over roll/pitch/heave, retaining the current
        # yaw allocation. All candidate wrenches still come from actual source.
        # A small region around zero covers coordinated low-PWM branch changes;
        # larger workpoints use the same region relative to the current inverse.
        axes = [j for j in (0,1,3) if j in active]
        center = np.zeros(len(axes)) if np.max(np.abs(u[axes])) < .075 else u[axes]
        grid = np.linspace(-.06,.06,61,dtype=np.float32)
        points = np.stack(np.meshgrid(*([grid]*len(axes)),indexing='ij'),axis=-1).reshape(-1,len(axes))
        candidates = np.tile(u,(len(points),1)).astype(np.float32)
        candidates[:,axes] = (points+center)*1.0002
        candidates = np.clip(candidates,-.95,.95); dense_points = len(candidates)
        best = u.copy(); best_score = objective(u)
        for start in range(0,len(candidates),8192):
            group = candidates[start:start+8192]
            wrench, raw = batch_source_map(kernel,group)
            ratios = np.abs((wrench-target)/scale)/ACCELERATION_TOLERANCE
            score = ratios.max(axis=1)
            margin = np.min(np.abs(np.abs(raw.astype(float))-float(np.float32(.02))),axis=1)
            score[(np.max(np.abs(raw),axis=1)>.95)|(margin<=MINIMUM_DEADZONE_DISTANCE)] = np.inf
            # Re-evaluate candidate winners through the scalar source map;
            # batch arithmetic is a search aid, never an acceptance shortcut.
            for i in np.argsort(score)[:4]:
                if not np.isfinite(score[i]):continue
                exact = objective(group[i])
                if exact < best_score:best,best_score=group[i].copy(),exact
        u = best
    u = u.astype(np.float32); wrench, sent = _steady(kernel, u)
    error = (wrench-target)/scale; margin = float(1-np.max(np.abs(sent['pwm_raw'])))
    return {'command_4':u.astype(float).tolist(),'target_wrench_6_n_nm':target.tolist(),
            'steady_wrench_6_n_nm':wrench.tolist(),'acceleration_error_6':error.tolist(),
            'pwm_raw':sent['pwm_raw'].astype(float).tolist(),'pwm_headroom':margin,
            'within_tolerance':bool(np.all(np.abs(error)<=ACCELERATION_TOLERANCE) and margin>=.05),
            'exact_equilibrium':bool(np.max(np.abs(error))<1e-6),
            'iterations':original['iterations']+iteration+1,
            'refinement':'branch_robust_block_local_and_batched_source_grid_v2',
            'minimum_deadzone_distance_pwm':deadzone_distance(sent['pwm_raw']),
            'dense_source_grid_points':dense_points}
