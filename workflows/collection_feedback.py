"""Causal collection feedback using frozen mechanics and bounded branch inversion."""
import numpy as np
from koopman.physics_context import rotation
from workflows.mechanics import mechanics,_steady,ACCELERATION_TOLERANCE
from workflows.control_kernel import ControlKernel
from workflows.feedback_inverse import solve_feasible_control,deadzone_distance,MINIMUM_DEADZONE_DISTANCE
from workflows.observation_trace import state_metrics

def parameters():
    # Common natural frequency 3 rad/s and critical damping in acceleration
    # coordinates; feedback bounded independently of the physical test pulse.
    return {'attitude_kp_s2': 9., 'angular_kd_s': 6.,
            'angular_feedback_limit_rad_s2': 16.,
            'height_kp_s2': 0., 'vertical_kd_s': 0.,
            'vertical_feedback_limit_m_s2': 1., 'starting_z_m': 5.5,
            'pulse_acceleration_4': [4., 2., 1., .5],
            'minimum_pwm_headroom': .05,
            'inverse_refinement': 'all_controllable_axes_branch_seeds_and_post_crossing_refinement_v31',
            'minimum_deadzone_distance_pwm': MINIMUM_DEADZONE_DISTANCE,
            'allocation_acceleration_tolerance_6': ACCELERATION_TOLERANCE.tolist(),
            'sample_period_s': 1/60, 'physics_period_s': 1/120,
            'history': 'identity_pose_zero_velocity_zero_rotors_all_startup_recorded',
            'state_input': 'current_boundary_z_quaternion_body_velocity_body_omega',
            'architecture': 'pose_restoring_compensation_bounded_pd_known_steady_inverse_v1'}


def target_terms(x, excitation, name):
    x = np.asarray(x, dtype=float); excitation = np.asarray(excitation, dtype=float)
    state_metrics(x)
    if excitation.shape != (4,) or not np.isfinite(excitation).all():
        raise ValueError('feedback_pulse_invalid')
    p = parameters(); m = mechanics(name); mask = np.asarray(m['control_mask_4'])
    q = x[1:5]/np.linalg.norm(x[1:5]); R = rotation(q)
    # Shortest quaternion error about the fixed identity reference. q and -q
    # must give the same physical action (including the exact pi tie).
    nonzero = q[np.flatnonzero(q)]
    if nonzero[0] < 0: q = -q
    feedback = np.zeros(4)
    feedback[:3] = np.clip(-p['attitude_kp_s2']*2*q[1:] - p['angular_kd_s']*x[8:],
                          -p['angular_feedback_limit_rad_s2'], p['angular_feedback_limit_rad_s2'])
    vz = (R @ x[5:8])[2]
    feedback[3] = np.clip(-p['height_kp_s2']*(x[0]-p['starting_z_m']) - p['vertical_kd_s']*vz,
                         -p['vertical_feedback_limit_m_s2'], p['vertical_feedback_limit_m_s2'])
    feedback *= mask; excitation = excitation*mask
    up = R.T @ np.array([0., 0., 1.])
    B = m['water_density_kg_m3']*m['volume_m3']*m['gravity_m_s2']
    restoring = np.cross(m['cob_m'], B*up)
    # Only body heave is actuated. The unallocated lateral gravity/buoyancy
    # demand is logged explicitly; we do not claim six-DOF equilibrium.
    gravity_balance = (m['mass_kg']*m['gravity_m_s2']-B)*up
    target = np.zeros(6)
    target[2] = gravity_balance[2] + m['mass_kg']*(feedback[3]*up[2]+excitation[3])
    torque_unmasked = -restoring + np.asarray(m['inertia_kg_m2'])*(feedback[:3]+excitation[:3])
    target[3:] = torque_unmasked*mask[:3]
    return {'state_available_11': x.tolist(), 'pulse_acceleration_4': excitation.tolist(),
            'feedback_acceleration_4': feedback.tolist(), 'restoring_torque_3_nm': restoring.tolist(),
            'unallocated_lateral_force_2_n': gravity_balance[:2].tolist(),
            'unallocated_torque_3_nm': (torque_unmasked-target[3:]).tolist(),
            'target_wrench_6_n_nm': target.tolist()}


def validate_decision(d, state_available, excitation, name):
    """Recompute causal demand and the actual source map, not a solver label.

    The iterative inverse can differ across CPU/LAPACK builds. Acceptance
    checks the issued command's physical residual; it never reoptimizes it.
    """
    expected = target_terms(state_available, excitation, name)
    for key, value in expected.items():
        np.testing.assert_allclose(d[key], value, rtol=0, atol=1e-6, err_msg=key)
    u = np.asarray(d['command_4'], dtype=float); m = mechanics(name)
    if (u.shape != (4,) or not np.isfinite(u).all() or np.any(np.abs(u) > .95)
            or np.any(u[np.asarray(m['control_mask_4']) == 0])):
        raise ValueError('feedback_command_invalid')
    if d['allocation']['command_4'] != d['command_4']: raise ValueError('feedback_inverse_identity')
    kernel = ControlKernel(name); wrench, sent = _steady(kernel, u)
    scale = np.r_[[m['mass_kg']]*3, m['inertia_kg_m2']]
    error = (wrench-np.asarray(expected['target_wrench_6_n_nm']))/scale
    margin = float(1-np.max(np.abs(sent['pwm_raw'])))
    a = d['allocation']
    for key, value, atol in [('target_wrench_6_n_nm', expected['target_wrench_6_n_nm'], 1e-6),
                             ('steady_wrench_6_n_nm', wrench, 1e-5),
                             ('acceleration_error_6', error, 1e-5), ('pwm_raw', sent['pwm_raw'], 1e-6),
                             ('pwm_headroom', margin, 1e-6)]:
        np.testing.assert_allclose(a[key], value, rtol=0, atol=atol, err_msg=key)
    supported = bool(np.all(np.abs(error) <= ACCELERATION_TOLERANCE) and margin >= .05)
    if a['within_tolerance'] is not supported: raise ValueError('feedback_allocation_gate_binding')
    return supported and deadzone_distance(sent['pwm_raw']) > MINIMUM_DEADZONE_DISTANCE

class FeedbackPolicy:
    def __init__(self,name):self.name=name;self.mechanics=mechanics(name)
    def decide(self,state_available,excitation):
        terms=target_terms(state_available,excitation,self.name)
        allocation=solve_feasible_control(self.name,terms['target_wrench_6_n_nm'])
        return dict(terms,command_4=allocation['command_4'],allocation=allocation)
