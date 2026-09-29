"""Bounded observation, contact and motion guards for the actual simulator."""
import copy
from typing import Any
import numpy as np
from koopman.physics_context import rotation
from workflows.free_water import screen_step,contact_screen
LIMITS={'linear_speed_m_s':1.5,'angular_speed_rad_s':3.,'tilt_rad':np.pi/3,'horizontal_displacement_m':2.,'vertical_displacement_m':2.}
TAIL_LIMITS={'linear_speed_m_s':.5,'angular_speed_rad_s':.5,'tilt_rad':np.pi/6}

def _copy(value):
    if hasattr(value, 'detach'):
        return value.detach().cpu().tolist()
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_copy(item) for item in value]
    return copy.deepcopy(value)


def _states(env):
    return [state_vector_from_env(env, index) for index in range(env.num_envs)]


def backend_readback(env):
    """Observe the actual rigid-body tensor API, independently of state11 caches.

    Getter results may alias reusable backend buffers: copy each immediately.
    No forward, update, setter, or simulation step is allowed here. Matching
    these readbacks does not prove equality of unexposed internal solver state.
    """
    robot = env._robot
    view = robot.root_physx_view
    result = {}
    fields = {'transform_actor_world_xyzw': 'get_transforms',
              'velocity_com_world_6': 'get_velocities',
              'mass_kg': 'get_masses', 'inverse_mass_per_kg': 'get_inv_masses',
              'inertia_9': 'get_inertias', 'inverse_inertia_9': 'get_inv_inertias',
              'com_local_pose_xyzw': 'get_coms', 'gravity_disabled': 'get_disable_gravities'}
    for label, name in fields.items():
        result[label] = _copy(getattr(view, name)())
    result['cache_state_world_wxyz_13'] = _copy(robot.data.root_state_w)
    result['cache_sim_timestamp_s'] = float(robot.data._sim_timestamp)
    result['gravity_world_m_s2'] = _copy(env.sim.cfg.gravity)
    for name in ('_external_force_b', '_external_torque_b', '_external_wrench_positions_b',
                 'has_external_wrench', 'uses_external_wrench_positions', '_use_global_wrench_frame'):
        if hasattr(robot, name):
            result[name] = _copy(getattr(robot, name))
    return result


class ControlTraceSession:
    """Observe before apply and after scene update, without moving control calls.

    Post-physics state is sampled at the next apply or at _get_dones BEFORE
    automatic reset. This ordering must be verified against the loaded runtime.
    Installs instance hooks only within the context; disabled mode installs none.
    GPU synchronization may affect wall time: real trace-on/off remains a gate.
    """

    def __init__(self, env, *, enabled=True, max_substeps=128, state_getter=None,
                 backend_readback_enabled=False):
        if isinstance(max_substeps, bool) or not isinstance(max_substeps, int) or max_substeps < 1:
            raise ValueError('trace_budget_invalid')
        self.env = env
        self.enabled = enabled
        self.max_substeps = max_substeps
        self.state_getter = state_getter or _states
        self.backend_readback_enabled = backend_readback_enabled
        self.substeps = []
        self.events = []
        self.generations = [0] * env.num_envs
        self.control_index = -1
        self.substep_index = 0
        self.pending = None
        self.originals = {}
        self.instance_values = {}
        self.active = False
        self.actuator_original = None
        self.actuator_instance_value = None
        self.actuator_had_instance_value = False

    def _snapshot(self):
        env = self.env
        result = {'state_11': _copy(self.state_getter(env)),
                  'telemetry': _copy(env.get_koopman_telemetry_snapshot()),
                  'actuator_speed_n': _copy(env.thruster_dynamics.state)}
        for name in ('old_actions', 'actions_i', '_actions', '_goal', 'PID_args',
                     '_thrust', '_moment', '_thruster_dynamics_time_s',
                     '_actions_d_filt', '_depth_integral_state',
                       '_last_motor_values_raw', '_last_motor_values_clipped', '_disturbance_audit_v86'):
            if hasattr(env, name):
                result[name] = _copy(getattr(env, name))
        if self.backend_readback_enabled:
            result['backend'] = backend_readback(env)
        return result

    def _actuator_update(self, command, end_time):
        if self.substeps:
            self.substeps[-1]['actuator_update'] = {
                'speed_command_n': _copy(command), 'end_time_s': _copy(end_time)}
        return self.actuator_original(command, end_time)

    def _pid(self, actions, actions_d, actions_i):
        if self.substeps:
            self.substeps[-1]['controller_inputs'] = {
                'actions': _copy(actions), 'actions_d': _copy(actions_d),
                'actions_i': _copy(actions_i)}
        return self.originals['_pid_control'](actions, actions_d, actions_i)

    def _finish_physics(self):
        if self.pending is not None:
            self.pending['state_after_physics_11'] = _copy(self.state_getter(self.env))
            if self.backend_readback_enabled:
                self.pending['backend_after_physics'] = backend_readback(self.env)
            self.pending = None

    def _pre(self, *args, **kwargs):
        if self.pending is not None:
            raise RuntimeError('trace_missing_end_of_interval_boundary')
        if len(self.substeps) >= self.max_substeps:
            raise RuntimeError('trace_substep_budget')
        self.control_index += 1
        self.substep_index = 0
        return self.originals['_pre_physics_step'](*args, **kwargs)

    def _apply(self, *args, **kwargs):
        self._finish_physics()
        if len(self.substeps) >= self.max_substeps:
            raise RuntimeError('trace_substep_budget')
        if self.control_index < 0:
            raise RuntimeError('trace_apply_before_pre')
        row = {'control_index': self.control_index, 'substep_index': self.substep_index,
               'reset_generation': list(self.generations),
               'physics_dt_s': float(self.env.sim.cfg.dt),
               'before': self._snapshot()}
        self.substeps.append(row)
        result = self.originals['_apply_action'](*args, **kwargs)
        row['command'] = self._snapshot()
        # No physics step has happened at this point.
        self.pending = row
        self.substep_index += 1
        return result

    def _dones(self, *args, **kwargs):
        self._finish_physics()
        result = self.originals['_get_dones'](*args, **kwargs)
        self._event({'kind': 'dones', 'control_index': self.control_index,
                     'reset_generation': list(self.generations), 'result': _copy(result)})
        return result

    def _event(self, value):
        if len(self.events) >= 2 * self.max_substeps + 2:
            raise RuntimeError('trace_event_budget')
        self.events.append(value)

    def _reset(self, env_ids=None, *args, **kwargs):
        if self.pending is not None:
            raise RuntimeError('trace_reset_before_physics_boundary')
        ids = list(range(self.env.num_envs)) if env_ids is None else _copy(env_ids)
        event = {'kind': 'reset', 'env_ids': ids, 'before': self._snapshot()}
        self._event(event)
        result = self.originals['_reset_idx'](env_ids, *args, **kwargs)
        for index in ids:
            self.generations[index] += 1
        event['after'] = self._snapshot()
        event['reset_generation'] = list(self.generations)
        return result

    def __enter__(self):
        if self.active:
            raise RuntimeError('trace_session_already_active')
        self.active = True
        if not self.enabled:
            return self
        if getattr(self.env, '_control_trace_v23_active', False):
            self.active = False
            raise RuntimeError('trace_session_already_active')
        hooks = {'_pre_physics_step': self._pre, '_apply_action': self._apply,
                 '_get_dones': self._dones, '_reset_idx': self._reset}
        if callable(getattr(self.env, '_pid_control', None)):
            hooks['_pid_control'] = self._pid
        # Resolve all methods before installing any hook.
        self.originals = {name: getattr(self.env, name) for name in hooks}
        self.instance_values = {name: self.env.__dict__[name] for name in hooks
                                if name in self.env.__dict__}
        self.env._control_trace_v23_active = True
        for name, hook in hooks.items():
            setattr(self.env, name, hook)
        actuator = self.env.thruster_dynamics
        if callable(getattr(actuator, 'update', None)):
            self.actuator_original = actuator.update
            self.actuator_had_instance_value = 'update' in actuator.__dict__
            self.actuator_instance_value = actuator.__dict__.get('update')
            actuator.update = self._actuator_update
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.enabled:
            if self.actuator_original is not None:
                if self.actuator_had_instance_value:
                    self.env.thruster_dynamics.update = self.actuator_instance_value
                else:
                    delattr(self.env.thruster_dynamics, 'update')
            for name in self.originals:
                if name in self.instance_values:
                    setattr(self.env, name, self.instance_values[name])
                else:
                    delattr(self.env, name)
            delattr(self.env, '_control_trace_v23_active')
        self.active = False
        # An interrupted apply must never be labeled a completed physics step.
        if exc is None and self.pending is not None:
            raise RuntimeError('trace_incomplete_physics_boundary')
        return False

class FreeWaterTraceSession(ControlTraceSession):
    def __init__(self, env, *, contact_getter, stop_on_rejection=True,
                 max_substeps=128, state_getter=None, geometry=None):
        if env.num_envs != 1 or not callable(contact_getter) or type(stop_on_rejection) is not bool:
            raise ValueError('free_water_contact_contract: single environment and explicit getter required')
        super().__init__(env, enabled=True, max_substeps=max_substeps,
                         state_getter=state_getter, backend_readback_enabled=True)
        self.contact_getter = contact_getter
        self.stop_on_rejection = stop_on_rejection
        self.contact_body_paths = None
        self.geometry = geometry

    def _finish_physics(self):
        row = self.pending
        super()._finish_physics()
        if row is None:
            return
        # Preserve the raw observation before validating it or stopping.
        contact = _copy(self.contact_getter())
        row['contact_after_physics_v26'] = contact
        try:
            paths = contact['body_paths']
            if (not isinstance(paths, list) or not paths
                    or any(not isinstance(p, str) or not p.startswith('/') for p in paths)
                    or len(set(paths)) != len(paths)):
                raise ValueError('body identity')
            forces = np.asarray(contact['normal_force_world_n'], dtype=float)
            if forces.shape != (len(paths), 3) or not np.isfinite(forces).all():
                raise ValueError('normal force shape or finite value')
            if float(contact['physics_dt_s']) != row['physics_dt_s']:
                raise ValueError('physics clock')
            if self.geometry is not None:
                if (paths != [self.geometry['body_path']]
                        or float(contact['sample_timestamp_s']) != row['backend_after_physics']['cache_sim_timestamp_s']):
                    raise ValueError('geometry binding or sample timestamp')
            if self.contact_body_paths is not None and paths != self.contact_body_paths:
                raise ValueError('body identity changed')
            self.contact_body_paths = list(paths)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'free_water_contact_contract: {exc}') from exc
        result = screen_step(row)
        if self.geometry is not None:
            from workflows.geometry import step_clearance
            margin = step_clearance(row, self.geometry)
            result['minimum_hull_clearance_m'] = margin
            if margin < self.geometry['minimum_clearance_m']:
                result['reasons'].append('hull_clearance_below_minimum')
                result['screen_pass'] = False
        # No calibrated sensor-noise threshold is invented for simulator output.
        # Any nonzero reported normal force fails this necessary screen.
        result['direct_contact_observed'] = bool(np.any(forces))
        if result['direct_contact_observed']:
            result['reasons'].append('measured_normal_contact')
            result['screen_pass'] = False
        row['free_water_screen_v26'] = result
        if self.stop_on_rejection and not result['screen_pass']:
            raise ValueError('free_water_screen_rejected: '+','.join(result['reasons']))

def state_metrics(x):
    x = np.asarray(x, dtype=float)
    if x.shape != (11,) or not np.isfinite(x).all() or abs(np.linalg.norm(x[1:5])-1) > 1e-3:
        raise ValueError('calibration_state_invalid')
    return {'linear_speed_m_s': float(np.linalg.norm(x[5:8])),
            'angular_speed_rad_s': float(np.linalg.norm(x[8:])),
            'tilt_rad': float(np.arccos(np.clip(rotation(x[1:5])[2, 2], -1, 1)))}


def domain_screen(row, geometry, starting_z):
    result = contact_screen(row, geometry)
    metrics = state_metrics(np.asarray(row['state_after_physics_11'])[0])
    pose = np.asarray(row['backend_after_physics']['transform_actor_world_xyzw'])[0]
    metrics.update(horizontal_displacement_m=float(np.linalg.norm(pose[:2])),
                   vertical_displacement_m=float(abs(pose[2]-starting_z)))
    labels = ('linear_speed_limit', 'angular_speed_limit', 'tilt_limit',
              'horizontal_displacement_limit', 'vertical_displacement_limit')
    for name, label in zip(LIMITS, labels):
        if metrics[name] > LIMITS[name]: result['reasons'].append(label)
    result['screen_pass'] = not result['reasons']; result['motion_metrics'] = metrics
    return result


def tail_gate(rows):
    if len(rows) < 64: raise ValueError('calibration_tail_incomplete')
    metrics = [state_metrics(np.asarray(r['state_after_physics_11'])[0]) for r in rows[-64:]]
    maximum = {k: max(m[k] for m in metrics) for k in TAIL_LIMITS}
    return {'eligible_for_excitation': all(maximum[k] <= TAIL_LIMITS[k] for k in maximum),
            'tail_physics_ticks': 64, 'maximum': maximum,
            'limits': dict(TAIL_LIMITS), 'claim': 'bounded motion only, not exact hovering'}


class CalibrationTraceSession(FreeWaterTraceSession):
    def __init__(self, env, *, starting_z, **kwargs):
        super().__init__(env, stop_on_rejection=True, **kwargs)
        self.starting_z = starting_z

    def _finish_physics(self):
        row = self.pending
        super()._finish_physics()
        if row is None: return
        result = domain_screen(row, self.geometry, self.starting_z)
        row['calibration_screen_v27'] = result
        if not result['screen_pass']:
            raise ValueError('calibration_motion_rejected:'+','.join(result['reasons']))

def _as_list(values: Any) -> list[float]:
    if hasattr(values, "detach"):
        values = values.detach().cpu().reshape(-1).tolist()
    elif hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, (int, float)):
        return [float(values)]
    result: list[float] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            result.extend(_as_list(value))
        else:
            result.append(float(value))
    return result


def state_vector_from_env(env: Any, env_index: int = 0) -> list[float]:
    data = env._robot.data
    return (
        _as_list(data.root_pos_w[env_index, 2])
        + _as_list(data.root_quat_w[env_index])
        + _as_list(data.root_lin_vel_b[env_index])
        + _as_list(data.root_ang_vel_b[env_index])
    )
