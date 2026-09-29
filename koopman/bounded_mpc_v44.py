"""Local bounded 4D candidate optimization, not an admitted live controller.

Fit provenance must be loaded from the verified cache. Caller-supplied episode,
reference and history identities still require an atomic runtime capture and
nonblocking execution arbiter; no returned trial is eligible to issue directly.
"""
from dataclasses import dataclass, field
import hashlib
import json
import numbers
from pathlib import Path
import re
import time

import numpy as np

from koopman.command_batch_v42 import forecast_batch
from koopman.command_prediction_v37 import validate_context
from koopman.command_state_v39 import _PredictionOrigin
from koopman.control_objective_v44 import (ObjectiveWeights, checked_reference, control_mask,
                                         state_features, trajectory_cost)
from koopman.prepared_allocation_v42 import PreparedDirectAllocation
from koopman.prepared_projected_v40 import _context_key

COMMAND_ATOL = 1e-7  # float32 bounds rounding, not a model-accuracy relaxation


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
    from workflows.identify_sparse_world_v30 import load_fit_cache, from_record
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


@dataclass(frozen=True)
class SearchConfig:
    horizon: int = 20
    perturbation: tuple = (.002,)*4
    slew: tuple = (.01,)*4
    raw_pwm_limit: float = .95
    timeout_ms: float = 100.

    def __post_init__(self):
        if type(self.horizon) is not int or not 1 <= self.horizon <= 128:
            raise ValueError('mpc_horizon')
        for name in ('perturbation', 'slew'):
            values = np.asarray(getattr(self, name), dtype=float)
            if values.shape != (4,) or not np.isfinite(values).all() or np.any(values <= 0) or np.any(values > 1.9):
                raise ValueError('mpc_'+name)
            object.__setattr__(self, name, tuple(float(v) for v in values))
        for value in (self.timeout_ms, self.raw_pwm_limit):
            if isinstance(value, bool) or not isinstance(value, numbers.Real) or not np.isfinite(value):
                raise ValueError('mpc_limits')
        if not 0 < self.timeout_ms <= 10000 or not 0 < self.raw_pwm_limit <= 1:
            raise ValueError('mpc_limits')


class BoundedMPC:
    def __init__(self, domain, predictor, *, model_id, config=SearchConfig(),
                 weights=ObjectiveWeights(), allow_diagnostic=False):
        if not isinstance(domain, SupportDomain) or (not domain._verified_fit and not allow_diagnostic):
            raise ValueError('mpc_fit_provenance_required')
        if model_id != domain.model_id: raise ValueError('mpc_model_mismatch')
        if not callable(predictor) or not isinstance(config, SearchConfig) or not isinstance(weights, ObjectiveWeights):
            raise ValueError('mpc_setup_invalid')
        self.domain, self.predictor, self.config, self.weights = domain, predictor, config, weights

    def solve(self, origin, initial_state, baseline, previous, reference, *,
              episode_id, reference_id, request_id, committed_prefix=0):
        started = time.perf_counter(); cfg = self.config; domain = self.domain
        deadline = started+cfg.timeout_ms/1000
        result = dict(status='no_plan', reason=None, selected_index=None, commands=None, predictions=None,
            cost=None, baseline_cost=None, candidate_count=0, candidates=[], runtime_eligible=False,
            data_source_verified=domain._verified_fit,
            metadata=dict(episode_id=episode_id, reference_id=reference_id, request_id=request_id,
                configuration=domain.configuration, context_key=list(domain.context_key),
                model_id=domain.model_id, support_id=domain.identity,
                input_contract='bounded4D_direct_preTAM_held_two_substeps',
                clock='time.perf_counter', started_perf_counter_s=started))

        def check_time():
            if time.perf_counter() >= deadline: raise TimeoutError('mpc_budget')

        def guarded_predictor(states, acceleration, context):
            # v42's optional deadline uses a different clock. Keep the frozen
            # forecast untouched and check our clock around every physics tick.
            # Cooperative checks cannot preempt a blocked predictor: isolation
            # and final packet admission remain the runtime arbiter's job.
            check_time()
            value = self.predictor(states, acceleration, context)
            check_time()
            return value

        def finish(reason):
            if reason is None and time.perf_counter() >= deadline:
                result.update(status='no_plan', selected_index=None, commands=None, predictions=None, cost=None)
                reason = 'timeout'
            result['reason'] = reason
            completed = time.perf_counter()
            result['elapsed_ms'] = 1000*(completed-started)
            result['metadata']['completed_perf_counter_s'] = completed
            return result

        try:
            check_time()
            if (not isinstance(origin, _PredictionOrigin) or origin._configuration != domain.configuration
                    or _context_key(origin._context) != domain.context_key):
                return finish('origin_context_mismatch')
            if any(not isinstance(v, str) or not v.strip() for v in (episode_id, reference_id, request_id)):
                return finish('request_identity_invalid')
            x, base, old = (np.array(v, dtype=float, copy=True) for v in (initial_state, baseline, previous))
            ref = checked_reference(reference); mask = control_mask(domain.configuration)
            if (x.shape != (11,) or base.shape != (cfg.horizon, 4) or old.shape != (4,)
                    or not np.isfinite(base).all() or not np.isfinite(old).all() or np.any(np.abs(old) > .95)
                    or type(committed_prefix) is not int or not 0 <= committed_prefix <= cfg.horizon):
                return finish('request_input_invalid')
            result['metadata'].update(origin_control=origin.origin_control,
                history_physics_index=2*origin.origin_control, origin_actuator_time_s=origin._actuator.elapsed_time,
                committed_prefix=committed_prefix, previous_command=old.tolist(), reference=ref.tolist())
            rejected = domain.check_states(x[None])
            if rejected: return finish('initial_'+rejected['reason'])
            candidates = [base.astype(np.float32)]
            for axis in np.flatnonzero(mask):
                for sign in (-1, 1):
                    sequence = base.copy(); sequence[committed_prefix:, axis] += sign*cfg.perturbation[axis]
                    for t in range(committed_prefix, cfg.horizon):
                        check_time()
                        prior = old if t == 0 else sequence[t-1]
                        sequence[t] = np.clip(sequence[t], domain.command_lower, domain.command_upper)
                        sequence[t] = np.clip(sequence[t], prior-np.asarray(cfg.slew), prior+np.asarray(cfg.slew))
                        sequence[t] *= mask
                    candidates.append(sequence.astype(np.float32))
            result['candidate_count'] = len(candidates)
            kernel = PreparedDirectAllocation(domain.configuration)
            viable, indices = [], []
            for i, sequence in enumerate(candidates):
                check_time(); reason = None
                checks = [('command_bound', np.any(np.abs(sequence) > .95+COMMAND_ATOL, axis=1)),
                    ('command_mask', np.any(np.abs(sequence*(1-mask)) > COMMAND_ATOL, axis=1)),
                    ('command_support', np.any((sequence < domain.command_lower-COMMAND_ATOL) |
                                              (sequence > domain.command_upper+COMMAND_ATOL), axis=1)),
                    ('command_slew', np.any(np.abs(np.diff(np.vstack([old, sequence]), axis=0)) >
                                           np.asarray(cfg.slew)+COMMAND_ATOL, axis=1))]
                for label, bad in checks:
                    if bad.any(): reason = dict(reason=label, index=int(np.flatnonzero(bad)[0])); break
                if reason is None:
                    for t, command in enumerate(sequence):
                        check_time()
                        raw = kernel.command(command, pre_tam=True)['pwm_raw']
                        if not np.isfinite(raw).all() or np.max(np.abs(raw)) > cfg.raw_pwm_limit+COMMAND_ATOL:
                            reason = dict(reason='raw_pwm_saturation', index=t); break
                row = dict(index=i, feasible=False, cost=None, rejection=reason)
                result['candidates'].append(row)
                if reason is None: viable.append(sequence); indices.append(i)
            check_time()
            if 0 not in indices: return finish('baseline_infeasible')
            forecasts = forecast_batch(origin, x, np.asarray(viable), guarded_predictor, deadline=None)
            for index, forecast in zip(indices, forecasts):
                check_time(); row = result['candidates'][index]
                if not forecast['complete']:
                    row['rejection'] = dict(reason='prediction_failed', detail=forecast['failure']); continue
                reason = domain.check_states(forecast['predictions'])
                if reason:
                    row['rejection'] = dict(reason='predicted_'+reason['reason'], index=reason['index']+1); continue
                cost = trajectory_cost(forecast['predictions'], candidates[index], old, ref, mask, self.weights)
                row.update(feasible=True, cost=cost)
            check_time()
            if not result['candidates'][0]['feasible']: return finish('baseline_prediction_infeasible')
            base_cost = result['candidates'][0]['cost']
            best = min((row for row in result['candidates'] if row['feasible']), key=lambda row: row['cost'])
            selected = best['index'] if best['cost'] < base_cost-1e-12*max(1., base_cost) else 0
            chosen = forecasts[indices.index(selected)]
            commands, predictions = owned(candidates[selected], np.float32), owned(chosen['predictions'])
            check_time()
            result.update(status='baseline' if selected == 0 else 'selected', selected_index=selected,
                commands=commands, predictions=predictions, cost=result['candidates'][selected]['cost'],
                baseline_cost=base_cost)
            return finish(None)
        except TimeoutError:
            return finish('timeout')
        except (ValueError, FloatingPointError) as exc:
            return finish('invalid_or_numerical:'+str(exc))
