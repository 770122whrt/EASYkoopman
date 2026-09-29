from types import SimpleNamespace

import numpy as np
import pytest

from koopman import diagnostics_v23 as diagnostic
from koopman.metrics_v21 import OFFICIAL_ROLLOUT_POLICY_V21, RolloutEpisodeV21, rollout_episode_v21


def episode():
    states = np.zeros((64, 11)); states[:, 1] = 1
    return RolloutEpisodeV21('fixture', 'uuv6', states, np.zeros((64, 4)),
                             np.zeros((64, 4)), states.copy(), .2, .1, (1, 1, 1, 1))


class Model:
    def __init__(self, error=False):
        self.calls = 0
        self.error = error

    def predict_increment(self, state, memory, control, *, platform_score=None):
        self.calls += 1
        if self.error:
            raise RuntimeError('specific kernel failure')
        increment = np.zeros(10); increment[0] = 60
        return increment


def test_diagnostic_preserves_production_result_and_failed_proposal():
    original, observed = Model(), Model()
    trace = rollout_episode_v21(original, episode(), start=3, steps=5,
                                policy=OFFICIAL_ROLLOUT_POLICY_V21)
    report = diagnostic.diagnose_window(observed, episode(), start=3, steps=5)
    assert observed.calls == original.calls == 2
    assert report['reason_code'] == trace.reason_code == 'rollout_diverged'
    assert report['failure_transition_index'] == 4
    assert report['completed_transition_count'] == 1
    assert report['last_prediction']['proposed_state_11'][0] == 120
    assert report['last_prediction']['state_11'][0] == 60


def test_raw_prediction_exception_is_retained():
    report = diagnostic.diagnose_window(Model(error=True), episode(), start=0, steps=5)
    assert report['reason_code'] == 'prediction_failed'
    assert report['last_prediction']['exception'] == 'RuntimeError: specific kernel failure'


def test_forbidden_roles_rejected_before_any_backend_read():
    calls = []
    good = SimpleNamespace(episode_id='source', configuration='uuv6', role='fit')
    reader = diagnostic.SourceOnlyReader(SimpleNamespace(open_episode=lambda b: calls.append(b)), [good])
    for bad in (SimpleNamespace(episode_id='source', configuration='base', role='fit'),
                SimpleNamespace(episode_id='source', configuration='uuv6', role='test'),
                SimpleNamespace(episode_id='other', configuration='uuv6', role='validation')):
        with pytest.raises(ValueError, match='source_access_denied'):
            reader.open_episode(bad)
    assert calls == []


def test_output_is_fresh_and_only_below_diagnostic_root(tmp_path):
    root = tmp_path / 'tmp' / 'phase8_3'
    output = diagnostic.reserve_output(root, 'run-1')
    assert output.is_dir()
    for name in ('run-1', '../escape', '/absolute', 'nested/run'):
        with pytest.raises((ValueError, FileExistsError)):
            diagnostic.reserve_output(root, name)


def test_redirected_binding_cannot_read_outside_dataset_root(tmp_path):
    calls = []
    binding = SimpleNamespace(episode_id='source', configuration='uuv6', role='fit',
                              transition_path='../test.jsonl', manifest_path='source.json')
    backend = SimpleNamespace(dataset_root=tmp_path / 'dataset', open_episode=lambda b: calls.append(b))
    reader = diagnostic.SourceOnlyReader(backend, [binding])
    with pytest.raises(ValueError, match='source_access_denied'):
        reader.open_episode(binding)
    assert calls == []
