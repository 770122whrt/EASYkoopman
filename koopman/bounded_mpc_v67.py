"""30 Hz held-pair candidate search on the unchanged 60 Hz prediction grid.

Candidates change only at paired 60 Hz entries, implementing 30 Hz holds.
The 120 Hz recurrence, micro-grid horizon, costs, deadzone/support gates and
request deadline remain explicit. No live promotion is implied.
"""
import time
import numpy as np
from koopman.bounded_mpc_v44 import SupportDomain, SearchConfig, COMMAND_ATOL, owned
from koopman.control_objective_v44 import ObjectiveWeights, control_mask, checked_reference, trajectory_cost
from koopman.command_state_v39 import _PredictionOrigin
from koopman.prepared_projected_v40 import _context_key
from koopman.prepared_allocation_v42 import PreparedDirectAllocation
from koopman.prepared_commands_v45 import PreparedCommands
from koopman.compiled_forecast_v64 import forecast_compiled, warm_forecast
from workflows.feedback_inverse_v28 import MINIMUM_DEADZONE_DISTANCE


class BoundedMPC:
    def __init__(self, domain, predictor, *, model_id, config=SearchConfig(),
                 weights=ObjectiveWeights(), allow_diagnostic=False, share_prefix=False):
        if not isinstance(domain, SupportDomain) or (not domain._verified_fit and not allow_diagnostic):
            raise ValueError('mpc_fit_provenance_required')
        if model_id != domain.model_id: raise ValueError('mpc_model_mismatch')
        if not callable(predictor) or not isinstance(config, SearchConfig) or not isinstance(weights, ObjectiveWeights):
            raise ValueError('mpc_setup_invalid')
        if config.horizon % 2 or any(abs(v-.02)>1e-12 for v in config.slew):
            raise ValueError('rate30_search_config')
        self.domain, self.predictor, self.config, self.weights = domain, predictor, config, weights
        self._allocator = PreparedDirectAllocation(domain.configuration)
        self.share_prefix = bool(share_prefix)
        warm_forecast(predictor)

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
                input_contract='bounded4D_direct_preTAM_held_four_substeps',
                control_rate_hz=30, prediction_grid_hz=60, physics_rate_hz=120,
                clock='time.perf_counter', started_perf_counter_s=started))

        def check_time():
            if time.perf_counter() >= deadline: raise TimeoutError('mpc_budget')

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
            if (type(origin.origin_control) is not int or origin.origin_control < 0
                    or origin.origin_control % 2 or committed_prefix % 2
                    or not np.array_equal(base[::2], base[1::2])):
                return finish('rate30_pairing_or_origin')
            result['metadata'].update(origin_control=origin.origin_control,
                history_physics_index=2*origin.origin_control, origin_actuator_time_s=origin._actuator.elapsed_time,
                committed_prefix=committed_prefix, previous_command=old.tolist(), reference=ref.tolist())
            rejected = domain.check_states(x[None])
            if rejected: return finish('initial_'+rejected['reason'])
            candidates = [base.astype(np.float32)]
            for axis in np.flatnonzero(mask):
                for sign in (-1, 1):
                    sequence = base.copy(); sequence[committed_prefix:, axis] += sign*cfg.perturbation[axis]
                    for t in range(committed_prefix, cfg.horizon, 2):
                        check_time()
                        prior = old if t == 0 else sequence[t-1]
                        sequence[t] = np.clip(sequence[t], domain.command_lower, domain.command_upper)
                        sequence[t] = np.clip(sequence[t], prior-np.asarray(cfg.slew), prior+np.asarray(cfg.slew))
                        sequence[t] *= mask
                        sequence[t+1] = sequence[t]
                    candidates.append(sequence.astype(np.float32))
            result['candidate_count'] = len(candidates)
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
                row = dict(index=i, feasible=False, cost=None, rejection=reason)
                result['candidates'].append(row)
                if reason is None: viable.append(sequence); indices.append(i)
            check_time()
            if not viable: return finish('baseline_infeasible')
            prepared = PreparedCommands(origin, np.asarray(viable), allocator=self._allocator, deadline=deadline)
            kept = []
            for position, index in enumerate(indices):
                check_time()
                raw = prepared.pwm_raw[position]
                bad = (~np.isfinite(raw).all(axis=1)) | (np.max(np.abs(raw), axis=1) > cfg.raw_pwm_limit+COMMAND_ATOL)
                distance = np.min(np.abs(np.abs(raw.astype(float))-float(np.float32(.02))), axis=1)
                ambiguous = distance <= MINIMUM_DEADZONE_DISTANCE
                if bad.any():
                    result['candidates'][index]['rejection'] = dict(reason='raw_pwm_saturation', index=int(np.flatnonzero(bad)[0]))
                elif ambiguous.any():
                    result['candidates'][index]['rejection'] = dict(reason='raw_pwm_deadzone_margin', index=int(np.flatnonzero(ambiguous)[0]))
                else:
                    kept.append((index, position))
            indices = [index for index, _ in kept]
            if 0 not in indices: return finish('baseline_infeasible')
            forecasts = forecast_compiled(origin, x, prepared, self.predictor,
                                          indices=[position for _, position in kept], deadline=deadline, share_prefix=self.share_prefix)
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
