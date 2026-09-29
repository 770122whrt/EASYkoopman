"""Causal feedback preview and independent all-reference selection audit.

Only predicted states enter future feedback. An origin is immutable here;
simulation/real command acknowledgments remain exclusively in the live ledger.
The checker preserves the v76 bounds/objective without importing CasADi.
"""
import time
import numpy as np
from koopman.reliable_mpc_v77 import ExactChecker as LegacyChecker
from koopman.bounded_mpc_v44 import COMMAND_ATOL
from koopman.control_objective_v44 import trajectory_cost, checked_reference
from koopman.prepared_commands_v45 import PreparedCommands
from workflows.feedback_inverse_v28 import MINIMUM_DEADZONE_DISTANCE


class ExactChecker(LegacyChecker):
    def check(self, origin, state, commands, previous, reference):
        result = dict(feasible=False, reason=None, cost=None, predictions=None)
        def reject(reason): result['reason'] = reason; return result
        state = np.asarray(state, dtype=float); old = np.asarray(previous, dtype=float)
        ref = checked_reference(reference)
        if state.shape != (11,) or old.shape != (4,) or not np.isfinite(old).all():
            return reject('check_input')
        if self.domain.check_states(state[None]): return reject('initial_state_out_of_support')
        a = np.asarray(commands, dtype=float)
        if (a.ndim != 2 or a.shape[1] != 4 or not 1 <= len(a) <= self.horizon
                or not np.isfinite(a).all() or np.any(np.abs(a) > .95)):
            return reject('command_bound')
        a = a.astype(np.float32); d = self.domain
        if np.any(np.abs(a*(1-self.mask)) > COMMAND_ATOL): return reject('command_mask')
        if np.any((a < d.command_lower-COMMAND_ATOL) | (a > d.command_upper+COMMAND_ATOL)):
            return reject('command_support')
        if np.any(np.abs(np.diff(np.vstack([old, a.astype(float)]), axis=0)) > .02+COMMAND_ATOL):
            return reject('command_slew')
        micro = np.repeat(a, 2, axis=0)
        prepared = PreparedCommands(origin, micro[None], allocator=self.plant.allocator)
        raw = prepared.pwm_raw[0].astype(float)
        if np.max(np.abs(raw)) > .95+COMMAND_ATOL: return reject('raw_pwm_saturation')
        if np.min(np.abs(np.abs(raw)-float(np.float32(.02)))) <= MINIMUM_DEADZONE_DISTANCE:
            return reject('raw_pwm_deadzone_margin')
        prediction = origin.forecast(state, micro, self.predictor)
        if not prediction['complete']: return reject('prediction_failed')
        bad = d.check_states(prediction['predictions'])
        if bad:
            result['rejection'] = bad
            return reject('predicted_'+bad['reason'])
        result.update(feasible=True, predictions=prediction['predictions'],
                      cost=trajectory_cost(prediction['predictions'], micro, old, ref, self.mask, self.weights))
        return result


def feedback_preview(origin, state, previous, reference, feedback, checker, *, timeout_s=30.):
    if not np.isfinite(timeout_s) or not 0 < timeout_s <= 60: raise ValueError('preview_budget')
    start = time.perf_counter(); x = np.array(state, dtype=float, copy=True)
    old = np.array(previous, dtype=float, copy=True); ref = checked_reference(reference)
    result = dict(status='no_preview', reason=None, commands=None, predictions=None,
                  cost=None, completed_macro_steps=0, runtime_eligible=False,
                  real_future_data_used=False, actual_history_advanced=False)
    sequence = []; predicted = None
    def finish(reason):
        result.update(reason=reason, elapsed_seconds=time.perf_counter()-start)
        return result
    for _ in range(checker.horizon):
        if time.perf_counter()-start >= timeout_s: return finish('preview_timeout')
        decision = feedback.decide(x.copy(), ref.copy(), previous=old.copy())
        if decision['status'] != 'ready': return finish('feedback_'+str(decision.get('reason')))
        sequence.append(np.array(decision['command'], dtype=np.float32, copy=True))
        # Replay from the immutable origin: never append simulated acknowledgments
        # to live history, and never use an observed future trajectory for x.
        checked = checker.check(origin, state, sequence, previous, ref)
        if not checked['feasible']: return finish('prefix_'+str(checked['reason']))
        predicted = checked['predictions']; x = predicted[-1].copy(); old = sequence[-1].copy()
        result['completed_macro_steps'] += 1
    if time.perf_counter()-start >= timeout_s: return finish('preview_timeout')
    result.update(status='ready', commands=np.asarray(sequence), predictions=predicted,
                  cost=checked['cost'])
    return finish(None)


def audit_selection(checker, origin, state, previous, reference, plans, selected, *, required, atol=1e-10):
    """Recompute every supplied reference. Never trust recorded feasibility/cost.

    The caller specifies required causal references from the decision inputs,
    not from a received worker list. This is finite-plan selection, not a proof
    of global optimality of the nonlinear continuous optimization problem.
    """
    if not set(required) <= set(plans): raise ValueError('missing_reference')
    if not np.isfinite(atol) or not 0 <= atol <= 1e-8: raise ValueError('selection_tolerance')
    selected = np.asarray(selected, dtype=float)
    # check() deliberately accepts prefixes for feedback preview; selection
    # must not let broadcasting compare a prefix to a full-horizon reference.
    if selected.shape != (checker.horizon, 4): raise ValueError('selected_plan_shape')
    if not np.isfinite(selected).all(): raise ValueError('selected_plan_nonfinite')
    summaries = {}; feasible = []
    for name, commands in plans.items():
        a = np.asarray(commands, dtype=float)
        if a.shape != (checker.horizon, 4): raise ValueError('selection_plan_shape')
        c = checker.check(origin, state, a, previous, reference)
        summaries[name] = {k:c[k] for k in ('feasible', 'reason', 'cost')}
        if c['feasible']: feasible.append((name, a, c))
    chosen = checker.check(origin, state, selected, previous, reference)
    reason = None
    if not chosen['feasible']: reason = 'selected_infeasible'
    elif not feasible: reason = 'no_feasible_reference'
    elif not any(np.allclose(selected, a, atol=COMMAND_ATOL, rtol=0) for _,a,_ in feasible):
        reason = 'selected_not_in_inventory'
    elif chosen['cost'] > min(c['cost'] for _,_,c in feasible)+atol: reason = 'dominated_selection'
    return dict(accepted=reason is None, reason=reason, references=summaries,
                selected_cost=chosen['cost'], global_optimum_claimed=False)


def audit_observed_pwm(raw, pwm):
    """Check measured backend PWM, not just proximity to a CPU reconstruction."""
    raw=np.asarray(raw,dtype=float);pwm=np.asarray(pwm,dtype=float)
    if (raw.ndim!=1 or raw.shape!=pwm.shape or len(raw) not in (4,6,8)
            or not np.isfinite(raw).all() or not np.isfinite(pwm).all()):
        raise ValueError('observed_pwm_shape')
    distance=float(np.min(np.abs(np.abs(raw)-float(np.float32(.02)))))
    reason=None
    if np.any(np.abs(pwm)>1) or not np.allclose(pwm,np.clip(raw,-1,1),atol=1e-6,rtol=0):
        reason='observed_pwm_clip'
    elif np.max(np.abs(raw))>.95+COMMAND_ATOL:reason='observed_pwm_saturation'
    elif distance<=MINIMUM_DEADZONE_DISTANCE:reason='observed_pwm_deadzone_margin'
    return dict(accepted=reason is None,reason=reason,minimum_margin=distance,
                required_margin=MINIMUM_DEADZONE_DISTANCE)
