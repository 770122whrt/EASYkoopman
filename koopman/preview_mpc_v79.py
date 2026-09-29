"""One continuous solve with causal feedback preview and audited retention.

Old v77 controllers/results remain immutable. No fixed-direction enumeration,
model fitting or closed-loop performance claim is introduced by this adapter.
"""
import time
import numpy as np
from koopman.feedback_preview_v79 import ExactChecker, feedback_preview, audit_selection
from koopman.reliable_mpc_v77 import physical_ramp, ProcessTransport
from koopman.model_separation_v79 import make_predictor
from koopman.control_objective_v44 import ObjectiveWeights, checked_reference
from koopman.inexact_tracking_v66 import InexactTrackingFeedback
from koopman.bounded_feedback_v46 import FeedbackConfig


class PreviewMPC:
    def __init__(self, checker, worker, feedback_factory, *, preview_enabled=True):
        if type(preview_enabled) is not bool: raise ValueError('preview_switch')
        self.checker, self.worker, self.horizon = checker, worker, checker.horizon
        self.feedback_factory = feedback_factory
        self.preview_enabled = preview_enabled
        self._last = None; self._failures = 0

    def solve(self, *, origin, initial_state, baseline, previous, reference, physical_target=None):
        started = time.perf_counter()
        result = dict(status='no_plan', reason=None, commands=None, predictions=None,
                      cost=None, exact_feasible=False, runtime_eligible=False,
                      search_kind='continuous_nonlinear_program', solver={},
                      preview_enabled=self.preview_enabled, origin_control=origin.origin_control,
                      reference=np.asarray(reference).copy())
        def finish(reason=None):
            result.update(reason=reason, elapsed_seconds=time.perf_counter()-started)
            return result
        try:
            ref = checked_reference(reference); old = np.asarray(previous, dtype=float)
            held = np.asarray(baseline, dtype=float)
            if held.shape != (self.horizon, 4) or old.shape != (4,): return finish('input_shape')
            plans = {'held':held.copy()}; checks = {}; required = ['held']
            def inspect(name, seq):
                plans[name] = np.asarray(seq, dtype=float).copy()
                checks[name] = self.checker.check(origin, initial_state, seq, old, ref)
            inspect('held', held)
            last = self._last
            if (last is not None and origin.origin_control == last['origin']+2
                    and np.array_equal(ref, last['reference'])
                    and np.allclose(old, last['commands'][0], atol=1e-7, rtol=0)):
                required.append('warm')
                inspect('warm', np.vstack([last['commands'][1:], last['commands'][-1]]))
            preview = (feedback_preview(origin, initial_state, old, ref,
                                       self.feedback_factory(), self.checker) if self.preview_enabled else
                       dict(status='disabled', reason='disabled_by_protocol'))
            result['preview'] = {k:v for k,v in preview.items() if k not in ('commands','predictions')}
            if preview['status'] == 'ready':
                required.append('preview'); inspect('preview', preview['commands'])
            # Preserve v77's warm-first initialization when no preview is usable;
            # only the new causal feedback preview may replace that initial guess.
            seed = 'warm' if checks.get('warm',{}).get('feasible') else 'held'
            if checks.get('preview',{}).get('feasible') and (
                    not checks[seed]['feasible'] or checks['preview']['cost'] < checks[seed]['cost']):
                seed = 'preview'
            guess = plans[seed].copy()
            result['initialization_source'] = seed
            if physical_target is not None and self.checker.deadzone_flat(guess):
                guess = physical_ramp(old, physical_target, self.checker.domain, self.checker.mask, self.horizon)
                seed = 'physical_target_ramp'
                result['initialization_sequence'] = guess.copy()
            result['initialization_kind'] = seed
            answer = self.worker.call(dict(origin=origin, initial_state=initial_state,
                         baseline=held, previous=old, reference=ref, initial_guess=guess))
            result['solver'] = answer.get('solver', {})
            for key in ('worker_pid','worker_cpu_seconds','worker_threads','constraint_violation',
                        'candidate_commands','candidate_failure','command_bound_violation',
                        'solution_check','selected_source'):
                result[key] = answer.get(key)
            result['worker_reason'] = answer.get('reason'); result['worker_status'] = answer.get('status')
            failed = answer.get('commands') is None
            result['worker_returned_commands'] = not failed
            self._failures = self._failures+1 if failed else 0
            if self._failures > 3: return finish('consecutive_solver_failures')
            if not failed:
                required.append('worker')
                if np.asarray(answer['commands']).shape != (self.horizon,4): return finish('worker_plan_shape')
                inspect('worker', answer['commands'])
                if not checks['worker']['feasible']: return finish('worker_plan_failed_exact_check')
            feasible = [name for name,c in checks.items() if c['feasible']]
            if not feasible: return finish('no_exact_feasible_solution_found')
            chosen = min(feasible, key=lambda name:checks[name]['cost'])
            commands = plans[chosen].astype(np.float32)
            # Re-evaluate ALL retained references independently of above costs.
            audit = audit_selection(self.checker, origin, initial_state, old, ref,
                                    plans, commands, required=tuple(required))
            result.update(selection_plans=plans, selection_audit=audit, selected_reference=chosen,
                          required_references=required)
            if not audit['accepted']: return finish('selection_audit_'+str(audit['reason']))
            status = {'held':'baseline_retained','warm':'warm_retained','preview':'preview_retained'}.get(chosen)
            if chosen == 'worker':
                status = 'optimized' if checks['held']['feasible'] else 'recovered'
                if answer.get('status') == 'baseline_retained': status = 'initialization_retained'
            if failed: status = 'timeout_retained' if answer.get('reason') in ('solver_timeout','worker_timeout') else 'solver_failure_retained'
            self._last = dict(origin=origin.origin_control, reference=ref.copy(), commands=commands.copy())
            result.update(status=status, commands=commands, cost=checks[chosen]['cost'],
                          predictions=checks[chosen]['predictions'], exact_feasible=True,
                          baseline_cost=checks['held']['cost'], consecutive_solver_failures=self._failures)
            return finish()
        except (ValueError, RuntimeError, TypeError, KeyError, FloatingPointError) as exc:
            result['exception'] = str(exc)
            return finish('invalid_solver_request_or_reply')

    def close(self): return self.worker.close()


def create_solver(domain, fitted, context, kind, *, horizon=20, weights=ObjectiveWeights(depth=4.), preview_enabled=True):
    predictor = make_predictor(kind, fitted, context)
    checker = ExactChecker(domain, predictor, horizon=horizon, weights=weights)
    # The two identified representations have the SAME symbolic velocity map;
    # this equivalence is explicit, not a new learned-model/control claim.
    proxy = 'nominal_physics' if kind == 'nominal_physics' else 'projected_koopman'
    spec = dict(domain=domain, fitted=fitted, context=context, kind=proxy, horizon=horizon, weights=weights)
    worker = ProcessTransport(spec)
    def feedback_factory():
        return InexactTrackingFeedback(domain, context, config=FeedbackConfig(slew=.02,timeout_ms=2000.))
    solver = PreviewMPC(checker, worker, feedback_factory, preview_enabled=preview_enabled)
    solver.model_identity = dict(kind=kind, symbolic_proxy=proxy,
                                unique_koopman_representation_claimed=False)
    return solver
