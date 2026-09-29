"""Opt-in bounded observer for the loaded DirectRLEnv call sequence."""

import copy


def _copy(value):
    if hasattr(value, 'detach'):
        return value.detach().cpu().tolist()
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_copy(item) for item in value]
    return copy.deepcopy(value)


def _states(env):
    from workflows.koopman_logging import state_vector_from_env
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
                     '_last_motor_values_raw', '_last_motor_values_clipped'):
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
