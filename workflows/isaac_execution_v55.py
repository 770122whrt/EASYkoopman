"""Opt-in actual-boundary bridge; local fixtures do not qualify Isaac execution.

Wrap the existing environment's reset/apply/dones hooks without moving physics,
adding a reset, or changing the plant. A known completed substep is acknowledged
even if its safety observation fails. Ambiguous execution is terminal, never
retried. The external collector still owns source/mechanics qualification and
worker preparation, and must measure the entire simulator cycle on the server.
"""
import copy
import time

import numpy as np

from koopman.execution_ledger_v48 import BoundaryObservation, ResetObservation
from koopman.runtime_coordinator_v52 import SafetyObservation
from workflows.calibration_trace_v27 import CalibrationTraceSession
from workflows.control_trace_v23 import _copy
from workflows.free_water_runtime_v26 import clearance


class IsaacExecutionSession(CalibrationTraceSession):
    def __init__(self, env, *, episode_id, reset_id, geometry, contact_getter,
                 max_substeps=128, state_getter=None):
        if (env.num_envs != 1 or env.cfg.control_input_mode != 'direct_pre_tam_v24'
                or env.cfg.decimation != 2 or float(env.sim.cfg.dt) != 1/120):
            raise ValueError('execution_bridge_direct_clock_contract')
        if any(not isinstance(v, str) or not v.strip() for v in (episode_id, reset_id)):
            raise ValueError('execution_bridge_identity')
        if geometry['minimum_clearance_m'] != .1:
            raise ValueError('execution_bridge_geometry_limit')
        super().__init__(env, contact_getter=contact_getter, geometry=copy.deepcopy(geometry),
                         starting_z=5.5, max_substeps=max_substeps, state_getter=state_getter)
        self.episode_id, self.reset_id = episode_id, reset_id
        self.runtime = None
        self._packet = None
        self._reset_seen = False
        self._reset_observation = None
        self._initial_counter = None
        self._initial_xy = None
        self._last_timestamp = None
        self._at_next_apply = False
        self._observed_reset_counter = None
        self._observed_reset_stamp = None
        self.interval_records = []

    def _stop(self, reason):
        if self.runtime is not None:
            self.runtime._stop('execution_bridge:' + str(reason))
        raise RuntimeError('execution_bridge:' + str(reason))

    def _reset(self, ids, *args, **kwargs):
        if self.runtime is not None or self._reset_seen:
            # DirectRLEnv calls dones before auto-reset. If an unexpected reset
            # arrives earlier, preserve a provably finished pending step first.
            self._finish_physics()
            self._stop('unexpected_reset')
        result = super()._reset(ids, *args, **kwargs)
        if self.generations != [1]:
            self._stop('reset_generation')
        self._reset_seen = True
        self._observed_reset_counter = int(self.env._sim_step_counter)
        self._observed_reset_stamp = float(self.events[-1]['after']['backend']['cache_sim_timestamp_s'])
        return result

    def _safety_observation(self, backend, contact, index):
        forces = np.asarray(contact['normal_force_world_n'], dtype=float)
        stamp = float(backend['cache_sim_timestamp_s'])
        if (contact['body_paths'] != [self.geometry['body_path']]
                or forces.shape != (1, 3) or not np.isfinite(forces).all()
                or contact['physics_dt_s'] != 1/120
                or not np.isfinite(stamp) or contact['sample_timestamp_s'] != stamp):
            raise ValueError('execution_bridge_contact_binding')
        pose = np.asarray(backend['transform_actor_world_xyzw'], dtype=float)
        if pose.shape != (1, 7):
            raise ValueError('execution_bridge_pose')
        margin = clearance(self.geometry['body_local_corners_m'], pose[0], self.geometry['ground_world_z_m'])
        return SafetyObservation(self.episode_id, self.reset_id, index,
            pose[0, :2] - self._initial_xy, margin, bool(np.any(forces)))

    def reset_observation(self):
        if (not self.active or not self._reset_seen or self.generations != [1]
                or self.control_index != -1 or self.pending is not None or self.runtime is not None):
            raise ValueError('execution_bridge_observed_reset_required')
        start = self._snapshot()
        if (int(self.env._sim_step_counter) != self._observed_reset_counter
                or float(start['backend']['cache_sim_timestamp_s']) != self._observed_reset_stamp):
            raise ValueError('execution_bridge_reset_boundary_changed')
        if np.any(np.asarray(start['_thruster_dynamics_time_s']) != 0):
            raise ValueError('execution_bridge_reset_actuator_clock')
        obs = ResetObservation(self.episode_id, self.reset_id, 0,
            np.asarray(start['state_11'])[0], np.asarray(start['actuator_speed_n'])[0])
        backend = start['backend']
        pose = np.asarray(backend['transform_actor_world_xyzw'], dtype=float)
        velocity = np.asarray(backend['velocity_com_world_6'], dtype=float)
        if (pose.shape != (1, 7) or velocity.shape != (1, 6)
                or not np.isfinite(pose).all() or not np.isfinite(velocity).all()
                or np.max(np.abs(velocity)) > 1e-6 or abs(pose[0, 2]-5.5) > 1e-6
                or np.linalg.norm(pose[0, 3:6]) > 1e-6 or abs(abs(pose[0, 6])-1) > 1e-6):
            raise ValueError('execution_bridge_reset_backend')
        self._initial_xy = pose[0, :2].copy()
        safety = self._safety_observation(backend, _copy(self.contact_getter()), 0)
        if safety.contact_observed or safety.minimum_clearance_m < .1:
            raise ValueError('execution_bridge_reset_safety')
        self._reset_observation = obs
        self._initial_counter = int(self.env._sim_step_counter)
        self._last_timestamp = float(backend['cache_sim_timestamp_s'])
        self.reset_record = dict(snapshot=start, contact_safety=_copy(vars(safety)),
                                 backend_step_index=self._initial_counter)
        return obs

    def bind(self, runtime):
        observed = self._reset_observation
        if self.runtime is not None or observed is None:
            raise ValueError('execution_bridge_reset_before_bind')
        # Solver preparation may take seconds after reset. Re-read instead of
        # binding a once-valid reset snapshot after external state changed.
        fresh = self.reset_observation()
        if (not np.array_equal(fresh.state, observed.state)
                or not np.array_equal(fresh.rotor_speed, observed.rotor_speed)):
            raise ValueError('execution_bridge_reset_changed_before_bind')
        expected = runtime.ledger._reset
        if (expected.episode_id != observed.episode_id or expected.reset_id != observed.reset_id
                or runtime.ledger.physics_index != 0 or runtime.ledger.pending or runtime.ledger.stopped
                or not np.array_equal(expected.state, observed.state)
                or not np.array_equal(expected.rotor_speed, observed.rotor_speed)
                or int(self.env._sim_step_counter) != self._initial_counter):
            raise ValueError('execution_bridge_reset_ledger_binding')
        self.runtime = runtime

    def _pre(self, action, *args, **kwargs):
        if self.runtime is None or self._packet is None or self.runtime.ledger.stopped:
            self._stop('dispatch_required')
        actual = np.asarray(_copy(action), dtype=np.float32)
        if actual.shape != (1, 4) or not np.array_equal(actual[0], self._packet['command']):
            self._stop('dispatch_command_mismatch')
        if int(self.env._sim_step_counter) != self._initial_counter + self.runtime.ledger.physics_index:
            self._stop('dispatch_backend_index')
        if self.control_index != self._packet['physics_index']//2-1:
            self._stop('dispatch_duplicate_pre')
        return super()._pre(action, *args, **kwargs)

    def _apply(self, *args, **kwargs):
        # Parent _apply completes and checks the preceding substep FIRST.
        # A rejection in that callback prevents the next actuator call.
        if self.runtime is None or self._packet is None or self.runtime.ledger.stopped:
            self._stop('dispatch_required')
        self._at_next_apply = True
        try:
            result = super()._apply(*args, **kwargs)
        finally:
            self._at_next_apply = False
        row = self.pending
        try:
            index = self._packet['physics_index'] + row['substep_index']
            command = row['command']; telemetry = command['telemetry']
            actual = np.asarray(telemetry['virtual_control_4'], dtype=np.float32)
            expected = self.runtime.ledger._steady.allocator.command(self._packet['command'], pre_tam=True)
            if (row['reset_generation'] != [1] or row['control_index'] != index//2
                    or row['substep_index'] not in (0, 1)
                    or self.env._direct_index_v24 != row['substep_index']+1
                    or int(self.env._sim_step_counter) != self._initial_counter+index+1
                    or telemetry['configuration'] != self.runtime.ledger._domain.configuration
                    or actual.shape != (1, 4) or not np.isfinite(actual).all()
                    or not np.allclose(actual[0], self._packet['command'], rtol=0, atol=1e-7)
                    or not np.array_equal(np.asarray(telemetry['control_mask_4'])[0], self.runtime.ledger._steady.allocator._mask)
                    or not np.array_equal(np.asarray(telemetry['step_token']), np.asarray(row['before']['telemetry']['step_token'])+1)):
                raise ValueError('actual_command_binding')
            for value, target in ((command['_last_motor_values_raw'], expected['pwm_raw']),
                                  (telemetry['motor_pwm_n'], expected['pwm'])):
                values = np.asarray(value, dtype=float)
                if (values.shape != (1, len(target)) or not np.isfinite(values).all()
                        or not np.allclose(values[0], target, rtol=0, atol=1e-6)):
                    raise ValueError('actual_pwm_mapping')
            # Admission happened before physics. Store independently of mutable
            # environment buffers; the receipt will use this actual command.
            row['execution_command_v55'] = dict(physics_index=index, command=actual[0].tolist(),
                backend_step_before=int(self.env._sim_step_counter),
                timestamp_before=float(command['backend']['cache_sim_timestamp_s']))
        except Exception as exc:
            self._stop(exc)
        return result

    def _finish_physics(self):
        row = self.pending
        if row is None:
            return
        issued = row.get('execution_command_v55')
        if (issued is None or self.runtime is None or self._packet is None
                or int(self.env._sim_step_counter) != issued['backend_step_before']+int(self._at_next_apply)):
            self._stop('uncertain_physics_boundary')
        # Snapshot/sensor errors can occur AFTER a real physics step. Check the
        # independent timestamp before calling the rich trace observer.
        from workflows.control_trace_v23 import backend_readback
        try:
            observed_stamp = float(backend_readback(self.env)['cache_sim_timestamp_s'])
            if (not np.isfinite(observed_stamp)
                    or abs(observed_stamp-issued['timestamp_before']-1/120) > 1e-7):
                raise ValueError('timestamp_step')
        except Exception as exc:
            self._stop('uncertain_physics_boundary:' + str(exc))
        error = None; safety = None
        try:
            super()._finish_physics()
            state = np.asarray(row['state_after_physics_11'], dtype=float)
            if self.runtime.ledger._domain.check_states(state):
                raise ValueError('actual_state_outside_support')
            safety = self._safety_observation(row['backend_after_physics'], row['contact_after_physics_v26'],
                                              issued['physics_index']+1)
        except Exception as exc:
            error = exc
        finally:
            # No future callback may duplicate this known physical receipt.
            self.pending = None
        ack = self.runtime.acknowledge(self._packet['ticket'], issued['command'],
            physics_index=issued['physics_index'], episode_id=self.episode_id,
            reset_id=self.reset_id, safety=safety)
        row['execution_ack_v55'] = _copy(ack)
        self._last_timestamp = observed_stamp
        if error is not None:
            row['execution_observation_error_v55'] = str(error)
            self._stop(error)
        if ack['status'] != 'acknowledged':
            self._stop(ack['reason'])

    def run_interval(self, env_step, reference, *, reference_id):
        started = time.perf_counter()
        if self.runtime is None or self.runtime.ledger.stopped or self._packet is not None:
            self._stop('dispatch_runtime_unavailable')
        record = dict(status='started', physics_index=self.runtime.ledger.physics_index)
        self.interval_records.append(record)
        try:
            index = self.runtime.ledger.physics_index
            snap = self._snapshot()
            if (int(self.env._sim_step_counter) != self._initial_counter+index
                    or float(snap['backend']['cache_sim_timestamp_s']) != self._last_timestamp):
                raise ValueError('boundary_changed_outside_dispatch')
            observation = BoundaryObservation(self.episode_id, self.reset_id, index, np.asarray(snap['state_11'])[0])
            safe = self._safety_observation(snap['backend'], _copy(self.contact_getter()), index)
            decision = self.runtime.step(observation, reference, reference_id=reference_id, safety=safe)
            record['decision'] = _copy(decision)
            if decision['status'] != 'dispatch':
                raise ValueError('runtime_' + str(decision['reason']))
            self._packet = decision['packet']
            import torch
            result = env_step(torch.as_tensor(np.array(self._packet['command'], copy=True),
                                             device=self.env.device).reshape(1, 4))
            if bool(torch.any(result[2])) or bool(torch.any(result[3])):
                raise ValueError('unexpected_done')
            if self.runtime.ledger.physics_index != index+2 or self.pending is not None or self.runtime.ledger.pending:
                raise ValueError('missing_complete_interval_receipts')
            record['status'] = 'completed_interval'
            return record
        except BaseException as exc:
            record.update(status='stopped', reason=str(exc))
            self.runtime._stop('execution_bridge_interval:' + str(exc))
            raise
        finally:
            self._packet = None
            record['whole_cycle_wall_ms'] = 1000*(time.perf_counter()-started)
            record['timing_scope'] = 'boundary_readback_decision_env_step_substep_validation_ack_excludes_record_encoding'
