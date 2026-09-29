"""Opt-in trace snapshot batching; preserves every original snapshot field.

Backend getters may share buffers. Clone immediately at each original read
boundary, then transfer one packed tensor per device/dtype. No cross-boundary
cache, precision conversion, asynchronous sensor read or omitted validation.
"""
import copy
from dataclasses import dataclass

import torch

from workflows.isaac_execution_v55 import IsaacExecutionSession


@dataclass(frozen=True)
class _Leaf:
    index: int


class SnapshotBatch:
    def __init__(self):
        self.tensors = []
        self.transfer_count = 0

    def capture(self, value):
        if isinstance(value, torch.Tensor):
            leaf = _Leaf(len(self.tensors))
            self.tensors.append(value.detach().clone())
            return leaf
        if isinstance(value, dict):
            return {key: self.capture(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.capture(item) for item in value]
        return copy.deepcopy(value)

    def finish(self, tree):
        groups = {}
        values = {}
        for index, tensor in enumerate(self.tensors):
            groups.setdefault((tensor.device, tensor.dtype), []).append((index, tensor))
        for rows in groups.values():
            packed = torch.cat([tensor.reshape(-1) for _, tensor in rows]).cpu()
            self.transfer_count += 1
            offset = 0
            for index, tensor in rows:
                count = tensor.numel()
                values[index] = packed[offset:offset + count].reshape(tensor.shape).tolist()
                offset += count
        def resolve(node):
            if isinstance(node, _Leaf):
                return values[node.index]
            if isinstance(node, dict):
                return {key: resolve(value) for key, value in node.items()}
            if isinstance(node, list):
                return [resolve(value) for value in node]
            return node
        return resolve(tree)


class BatchedIsaacExecutionSession(IsaacExecutionSession):
    def _snapshot(self):
        env = self.env
        batch = SnapshotBatch()
        take = batch.capture
        result = {'state_11': take(self.state_getter(env)),
                  'telemetry': take(env.get_koopman_telemetry_snapshot()),
                  'actuator_speed_n': take(env.thruster_dynamics.state)}
        for name in ('old_actions', 'actions_i', '_actions', '_goal', 'PID_args',
                     '_thrust', '_moment', '_thruster_dynamics_time_s',
                     '_actions_d_filt', '_depth_integral_state',
                     '_last_motor_values_raw', '_last_motor_values_clipped'):
            if hasattr(env, name):
                result[name] = take(getattr(env, name))
        if self.backend_readback_enabled:
            robot = env._robot
            fields = {'transform_actor_world_xyzw': 'get_transforms',
                      'velocity_com_world_6': 'get_velocities',
                      'mass_kg': 'get_masses', 'inverse_mass_per_kg': 'get_inv_masses',
                      'inertia_9': 'get_inertias', 'inverse_inertia_9': 'get_inv_inertias',
                      'com_local_pose_xyzw': 'get_coms', 'gravity_disabled': 'get_disable_gravities'}
            backend = {key: take(getattr(robot.root_physx_view, name)()) for key, name in fields.items()}
            backend['cache_state_world_wxyz_13'] = take(robot.data.root_state_w)
            backend['cache_sim_timestamp_s'] = float(robot.data._sim_timestamp)
            backend['gravity_world_m_s2'] = take(env.sim.cfg.gravity)
            for name in ('_external_force_b', '_external_torque_b', '_external_wrench_positions_b',
                         'has_external_wrench', 'uses_external_wrench_positions', '_use_global_wrench_frame'):
                if hasattr(robot, name):
                    backend[name] = take(getattr(robot, name))
            result['backend'] = backend
        return batch.finish(result)
