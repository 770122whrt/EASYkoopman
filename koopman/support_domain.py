"""Fit-bound state and command support; no search algorithm or runtime side effects."""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from koopman.command_context import validate_context
from koopman.control_objective import control_mask, state_features
from koopman.prepared_physics import _context_key

COMMAND_ATOL = 1e-7
def owned(value, dtype=float):
    a = np.asarray(value, dtype=dtype)
    return np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)

@dataclass(frozen=True)
class SupportDomain:
    configuration: str
    context_key: tuple
    model_id: str
    state_lower: np.ndarray
    state_upper: np.ndarray
    command_lower: np.ndarray
    command_upper: np.ndarray
    fit_sources: tuple = ()
    _verified_fit: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        control_mask(self.configuration)
        if not isinstance(self.model_id, str) or not re.fullmatch('[0-9a-f]{64}', self.model_id):
            raise ValueError('support_model_identity')
        key = tuple(self.context_key)
        if len(key) != 12 or not np.isfinite(key).all(): raise ValueError('support_context')
        object.__setattr__(self, 'context_key', key)
        for name, shape in [('state_lower', (11,)), ('state_upper', (11,)),
                            ('command_lower', (4,)), ('command_upper', (4,))]:
            a = np.asarray(getattr(self, name), dtype=float)
            if a.shape != shape or not np.isfinite(a).all(): raise ValueError('support_bounds')
            object.__setattr__(self, name, owned(a))
        if (np.any(self.state_lower > self.state_upper) or np.any(self.command_lower > self.command_upper)
                or np.any(self.command_lower < -.95) or np.any(self.command_upper > .95)):
            raise ValueError('support_bounds')
        object.__setattr__(self, 'fit_sources', tuple(tuple(item) for item in self.fit_sources))

    @classmethod
    def diagnostic(cls, configuration, context, model_id):
        validate_context(configuration, context)
        mask = control_mask(configuration)
        return cls(configuration, _context_key(context), model_id,
                   np.full(11, -100.), np.full(11, 100.), -.95*mask, .95*mask)

    def record(self):
        return dict(schema='fit-support-v44', configuration=self.configuration,
            context_key=list(self.context_key), model_id=self.model_id,
            state_lower=self.state_lower.tolist(), state_upper=self.state_upper.tolist(),
            command_lower=self.command_lower.tolist(), command_upper=self.command_upper.tolist(),
            fit_sources=self.fit_sources, verified_fit=self._verified_fit,
            hard_limits=dict(z=[3.5, 7.5], linear_speed=1.5, angular_speed=3., tilt=np.pi/3),
            limitations=['box_screen_not_statistical_guarantee', 'xy_and_contact_require_runtime_observation'])

    @property
    def identity(self):
        return hashlib.sha256(json.dumps(self.record(), sort_keys=True, allow_nan=False).encode()).hexdigest()

    def check_states(self, states):
        try:
            x = np.asarray(states, dtype=float)
            values = state_features(x, control_mask(self.configuration))
        except (ValueError, TypeError): return dict(reason='state_invalid', index=0)
        checks = [('height_limit', (x[:, 0] < 3.5) | (x[:, 0] > 7.5)),
                  ('linear_speed_limit', np.linalg.norm(x[:, 5:8], axis=1) > 1.5),
                  ('angular_speed_limit', np.linalg.norm(x[:, 8:], axis=1) > 3.),
                  ('tilt_limit', values[:, 3] < .5-1e-12),
                  ('state_out_of_support', np.any((values < self.state_lower-1e-12) |
                                                   (values > self.state_upper+1e-12), axis=1))]
        failed = [(int(np.flatnonzero(bad)[0]), reason) for reason, bad in checks if bad.any()]
        if failed:
            index, reason = min(failed, key=lambda item: item[0])
            return dict(reason=reason, index=index)
        return None

def load_fit_domains(root, model_path):
    """Only this factory admits fit provenance; runtime must use it, not labels."""
    from workflows.frozen_physics import load_fit_cache, from_record
    payload = Path(model_path).read_bytes(); record = json.loads(payload)
    from_record(record)
    model_id = hashlib.sha256(payload).hexdigest()
    episodes = load_fit_cache(Path(root))
    result = {}
    # Training-domain access only: an excluded LOCO configuration gets no box.
    for name in record['configurations']:
        selected = [e for e in episodes if e.case['configuration'] == name]
        if len(selected) != 3: raise ValueError('support_fit_inventory')
        c = selected[0].context
        for e in selected:
            if (e.case['role'] != 'fit' or e.acceptance.get('training_eligible') is not True
                    or record['fit_episode_hashes'].get(e.case['run_id']) != e.trace_sha256
                    or record['fit_source'] != e.source_commit or _context_key(e.context) != _context_key(c)):
                raise ValueError('support_fit_binding')
        validate_context(name, c)
        mask = control_mask(name)
        states = np.concatenate([e.states for e in selected])
        values = state_features(states, mask)
        commands = np.concatenate([e.arrays['issued_control'] for e in selected])
        pad = np.full(11, .02); pad[3] = .002
        lower, upper = values.min(0)-pad, values.max(0)+pad
        lower[0] = max(lower[0], 3.5); upper[0] = min(upper[0], 7.5)
        lower[1:4] = np.maximum(lower[1:4], -1); upper[1:4] = np.minimum(upper[1:4], 1)
        low_u, high_u = np.maximum(commands.min(0)-.002, -.95), np.minimum(commands.max(0)+.002, .95)
        low_u[mask == 0] = high_u[mask == 0] = 0.
        domain = SupportDomain(name, _context_key(c), model_id, lower, upper, low_u, high_u,
                               tuple((e.case['run_id'], e.trace_sha256) for e in selected))
        object.__setattr__(domain, '_verified_fit', True)
        if domain.check_states(states): raise ValueError('support_fit_outside_hard_limits')
        result[name] = domain
    return result
