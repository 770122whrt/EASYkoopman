"""Independent offline audit of one v79 decision, not full Isaac acceptance.

The caller supplies the actual current feedback record and the preceding
confirmed decision. Costs, feasibility flags and reference lists in the current
decision are not evidence for themselves. A ready preview is causally replayed.
"""
import numpy as np
from koopman.feedback_preview_v79 import audit_selection, feedback_preview
from koopman.reliable_mpc_v77 import physical_ramp


def _array(value, shape, label):
    value = np.asarray(value, dtype=float)
    if value.shape != shape or not np.isfinite(value).all():
        raise ValueError(label + '_shape_or_finite')
    return value


def _same(actual, expected, label, atol=1e-7):
    actual = _array(actual, np.asarray(expected).shape, label)
    if not np.allclose(actual, expected, atol=atol, rtol=0):
        raise ValueError(label)


def audit_decision(*, checker, origin, state, previous, reference,
                   feedback_result, prior_decision, decision, feedback_factory=None):
    """Raise ValueError on an inconsistent record; return recomputed evidence.

    prior_decision is None at the first solve, otherwise contains origin_control,
    reference and the preceding confirmed full commands. This function does not
    authenticate receipts or the provenance of caller-supplied input records.
    A full-run validator must bind them to its independently reconstructed ledger.
    """
    h = checker.horizon
    old = _array(previous, (4,), 'previous')
    ref = _array(reference, (5,), 'reference')
    state = _array(state, (11,), 'state')
    if decision['origin_control'] != origin.origin_control:
        raise ValueError('decision_origin')
    _same(decision['reference'], ref, 'decision_reference', atol=0.)
    selected = _array(decision['commands'], (h, 4), 'selected')
    enabled = decision['preview_enabled']
    returned = decision['worker_returned_commands']
    if type(enabled) is not bool or type(returned) is not bool:
        raise ValueError('decision_flags')
    if not returned and decision.get('worker_status') != 'no_plan':
        raise ValueError('worker_status')
    feedback_ready = feedback_result['status'] == 'ready'
    if feedback_ready:
        command = _array(feedback_result['command'], (4,), 'feedback')
        baseline_reference = 'feedback_hold'
    else:
        if feedback_result.get('reason') not in (
                'no_admissible_limited_command', 'static_inverse_not_found', 'timeout'):
            raise ValueError('feedback_failure')
        command = old
        baseline_reference = 'previous_hold_feedback_unavailable'
    if ('baseline_reference' in decision and
            decision['baseline_reference'] != baseline_reference):
        raise ValueError('baseline_reference')
    expected = {'held': np.tile(command, (h, 1))}
    if prior_decision is not None:
        prior = _array(prior_decision['commands'], (h, 4), 'prior')
        prior_ref = _array(prior_decision['reference'], (5,), 'prior_reference')
        if (origin.origin_control == prior_decision['origin_control'] + 2
                and np.array_equal(ref, prior_ref)
                and np.allclose(old, prior[0], atol=1e-7, rtol=0)):
            expected['warm'] = np.vstack([prior[1:], prior[-1]])
    preview = decision['preview']
    preview_ready = enabled and preview['status'] == 'ready'
    if not enabled and preview['status'] != 'disabled':
        raise ValueError('disabled_preview_status')
    if enabled and preview['status'] not in ('ready', 'no_preview'):
        raise ValueError('preview_status')
    names = list(expected)
    if preview_ready:
        names.append('preview')
    if returned:
        names.append('worker')
    plans = decision['selection_plans']
    if set(plans) != set(names):
        raise ValueError('reference_inventory')
    if 'required_references' in decision and set(decision['required_references']) != set(names):
        raise ValueError('required_reference_record')
    for name, plan in expected.items():
        _same(plans[name], plan, 'causal_' + name)
    if preview_ready:
        if feedback_factory is None:
            raise ValueError('preview_replay_factory')
        replay = feedback_preview(origin, state, old, ref, feedback_factory(), checker)
        if replay['status'] != 'ready':
            raise ValueError('preview_replay_unavailable:' + str(replay['reason']))
        expected['preview'] = replay['commands']
        _same(plans['preview'], replay['commands'], 'causal_preview')
    checks = {name: checker.check(origin, state, plan, old, ref)
              for name, plan in expected.items()}
    seed = 'warm' if checks.get('warm', {}).get('feasible') else 'held'
    if checks.get('preview', {}).get('feasible') and (
            not checks[seed]['feasible'] or checks['preview']['cost'] < checks[seed]['cost']):
        seed = 'preview'
    if decision['initialization_source'] != seed:
        raise ValueError('initialization_source')
    guess = expected[seed]
    target = feedback_result.get('static_command')
    ramp = target is not None and checker.deadzone_flat(guess)
    if ramp:
        if decision.get('initialization_source') != seed:
            raise ValueError('initialization_source')
        guess = physical_ramp(old, target, checker.domain, checker.mask, h)
        _same(decision['initialization_sequence'], guess, 'causal_physical_initialization', atol=1e-12)
    expected_initialization = 'physical_target_ramp' if ramp else seed
    if decision['initialization_kind'] != expected_initialization:
        raise ValueError('initialization_kind')
    if returned:
        if decision['worker_status'] not in ('optimized', 'recovered', 'baseline_retained'):
            raise ValueError('worker_status')
        if decision['worker_status'] == 'baseline_retained':
            _same(plans['worker'], np.asarray(guess, dtype=np.float32), 'retained_worker_initialization')
    fresh = audit_selection(checker, origin, state, old, ref, plans, selected, required=names)
    if not fresh['accepted']:
        raise ValueError(fresh['reason'])
    source = decision['selected_reference']
    if source not in names:
        raise ValueError('selected_reference')
    _same(selected, plans[source], 'selected_reference_sequence')
    status = {'held': 'baseline_retained', 'warm': 'warm_retained',
              'preview': 'preview_retained'}.get(source)
    if source == 'worker':
        status = 'optimized' if checks['held']['feasible'] else 'recovered'
        if decision['worker_status'] == 'baseline_retained':
            status = 'initialization_retained'
    if not returned:
        status = ('timeout_retained' if decision.get('worker_reason') in
                  ('solver_timeout', 'worker_timeout') else 'solver_failure_retained')
    if decision['status'] != status:
        raise ValueError('selection_status')
    if not decision['exact_feasible']:
        raise ValueError('recorded_exact_feasibility')
    if decision.get('consecutive_solver_failures', 0) > 3:
        raise ValueError('consecutive_solver_failures')
    _same(decision['cost'], fresh['selected_cost'], 'recorded_cost', atol=1e-10)
    selected_check = checker.check(origin, state, selected, old, ref)
    _same(decision['predictions'], selected_check['predictions'],
          'recorded_predictions', atol=1e-10)
    return dict(accepted=True, scope='offline_single_decision',
                required_references=names, selected_reference=source,
                selected_cost=fresh['selected_cost'], references=fresh['references'],
                preview_replayed=preview_ready, full_isaac_acceptance=False)
