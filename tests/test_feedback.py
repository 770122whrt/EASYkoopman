"""Frozen feedback oracle from 7bbbbef; no simulator-performance claim."""
import numpy as np
import pytest

from control_fixtures import context, oracle, assert_frozen, state
from koopman.feedback import FeedbackConfig, InexactTrackingFeedback
from koopman.support_domain import SupportDomain


@pytest.mark.parametrize('configuration', ['base', 'uuv4', 'uuv6'])
def test_maps_cache_decisions_startup_and_audit_match_frozen_behavior(configuration):
    expected = oracle('feedback_7bbbbef.json')['configurations'][configuration]
    c = context(configuration)
    domain = SupportDomain.diagnostic(configuration, c, '7'*64)
    policy = InexactTrackingFeedback(domain, c, config=FeedbackConfig(timeout_ms=2000.),
                                     allow_diagnostic=True)
    rng = np.random.default_rng(8546)
    for row in expected['maps']:
        command = rng.uniform(-.1, .1, 4)
        command[2] = 0
        assert_frozen(policy.steady.evaluate(command), row)
        assert_frozen(policy.steady.evaluate(command), row)
    x = state()[0]
    index = 0
    for delta in (0., .02, -.03):
        reference = np.array([5.5+delta, np.cos(.02), 0., np.sin(.02), 0.])
        for previous in (None, np.array([0., 0., 0., .03]), np.array([0., .001, 0., .3])):
            assert_frozen(policy.decide(x, reference, previous=previous), expected['decisions'][index])
            index += 1
    assert_frozen(policy.prepare_startup(x, x[:5]), expected['startup'])
    assert_frozen(policy.decide(x, x[:5], previous=None), expected['prepared'])
    assert_frozen(policy.audit, expected['audit'])
    assert policy.steady.cache_size == expected['cache_size']
