"""Cache only the fixed command map; inspect current demand/bounds every time."""
from dataclasses import replace
import numpy as np
import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from test_prepared_projected_v40 import context
from koopman.bounded_feedback_v47 import PreparedTrackingMap


@pytest.mark.parametrize('name',SUPPORTED_EMBODIMENTS)
def test_cached_map_matches_source_and_never_aliases_result(name):
    from koopman.cached_checks_v53 import CachedTrackingMap
    actual=CachedTrackingMap(name,context(name));original=PreparedTrackingMap(name,context(name))
    commands=[np.zeros(4),np.array([.002,-.003,0,.12]),np.array([-.002,.003,0,-.10])]
    for u in commands*2:
        a=actual.evaluate(u);b=original.evaluate(u)
        for key in b:np.testing.assert_array_equal(a[key],b[key])
        a['wrench'][:]=999;a['pwm_raw'][:]=999
        for key in b:np.testing.assert_array_equal(actual.evaluate(u)[key],b[key])
    assert actual.cache_size==3


def test_hit_still_uses_new_demand_slew_and_support_bounds():
    from koopman.cached_checks_v53 import CachedTrackingMap
    m=CachedTrackingMap('base',context('base'));u=np.array([0.,0,0,.1]);target=m.evaluate(u)['wrench']
    good=m.inspect(u,target,-.95*np.ones(4),.95*np.ones(4))
    assert good['physical_residual_accepted'] and good['command_constraints_accepted']
    changed=target.copy();changed[2]+=100
    rejected=m.inspect(u,changed,-.95*np.ones(4),np.full(4,.05))
    assert not rejected['physical_residual_accepted'] and not rejected['command_constraints_accepted']


def test_map_cache_is_finite_and_rejects_geometry_mutation():
    from koopman.cached_checks_v53 import CachedTrackingMap
    m=CachedTrackingMap('uuv6',context('uuv6'),cache_limit=2)
    for depth in (.1,.11,.12):m.evaluate([0,0,0,depth])
    assert m.cache_size==2
    m.allocator._inverse.add_(1.)
    with pytest.raises(ValueError,match='binding'):m.evaluate([0,0,0,.12])


def test_nearby_float_commands_are_not_rounded_into_one_cache_key():
    from koopman.cached_checks_v53 import CachedTrackingMap
    m=CachedTrackingMap('base',context('base'))
    for value in (.019999,.020001):m.evaluate([0,0,0,value])
    assert m.cache_size==2


def test_recovery_solver_cached_mapping_retains_entire_result():
    from koopman.cached_checks_v53 import CachedRecoverySolver
    from test_recovery_solver_v50 import request_and_solver
    from koopman.recovery_solver_v51 import RecoverySolver
    _,request,old=request_and_solver()
    kw=dict(config=old.config,feedback_config=old.baseline.config,allow_diagnostic=True)
    reference=RecoverySolver(old.domain,old.baseline.context,old.solver.predictor,**kw)
    cached=CachedRecoverySolver(old.domain,old.baseline.context,old.solver.predictor,**kw)
    a=reference(request);b=cached(request)
    for key in ('status','reason','binding','selected_index','candidates'):assert a[key]==b[key]
    for key in ('commands','predictions','cost','baseline_cost'):np.testing.assert_array_equal(a[key],b[key])


# Reuse the observable integration contracts with cached policy/ledger objects.
import test_runtime_coordinator_v52 as runtime_tests
from test_runtime_coordinator_v52 import (
    test_coordinator_startup_prefix_plan_activation_and_ack_form_one_chain,
    test_worker_failure_keeps_qualified_feedback_without_wait_or_restart,
    test_runtime_safety_rejects_before_any_dispatch_or_model_request,
    test_unsafe_first_substep_preserves_actual_partial_history_and_stops,
    test_feedback_failure_never_falls_back_to_zero_or_last_command,
    test_unacknowledged_dispatch_is_not_sent_again,
    test_control_decision_deadline_does_not_return_a_late_dispatch,
    test_worker_replacement_preserves_startup_and_causal_history,
    test_replacement_cannot_discard_an_already_dispatched_startup,
    test_ack_computation_timeout_keeps_confirmed_actual_history)


@pytest.fixture(autouse=True)
def use_cached_runtime(monkeypatch):
    from koopman.cached_checks_v53 import CachedExecutionLedger,CachedTrackingFeedback
    monkeypatch.setattr(runtime_tests,'PreparedExecutionLedger',CachedExecutionLedger)
    monkeypatch.setattr(runtime_tests,'TrackingFeedback',CachedTrackingFeedback)
