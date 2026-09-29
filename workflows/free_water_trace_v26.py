"""Additive per-substep guard; live contact getter requires server qualification.

Isaac Lab 2.2.1 net_forces_w reports normal contact force, not full frictional
contact force. Getter must copy the current physics step, identify every body,
and perform no simulation step or state write. Sensor binding/completeness and
observer-on/off equivalence remain real-runtime gates outside this module.
"""
import numpy as np
from workflows.control_trace_v23 import ControlTraceSession, _copy
from workflows.free_water_v26 import screen_step


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
            from workflows.free_water_runtime_v26 import step_clearance
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
