import numpy as np
from workflows import calibrate_bilinear_v85 as experiment
from workflows.calibrate_lifted_v84 import GRID, source_split, choose_ridge


def test_identical_source_selection_and_grid():
    assert experiment.GRID == GRID
    assert experiment.source_split is source_split
    assert experiment.choose_ridge is choose_ridge
    source, train, dev = experiment.source_split(['base', 'long', 'uuv4'], 'base')
    assert source == ['long', 'uuv4'] and train == ['long'] and dev == 'uuv4'


def test_fit_uses_bilinear_and_records_source_only(monkeypatch):
    from types import SimpleNamespace
    episode = SimpleNamespace(states=np.zeros((641, 11)), acceleration=np.zeros((640, 6)),
        context=object(), case={'run_id':'source', 'configuration':'long'},
        trace_sha256='trace', source_commit='source_commit')
    seen = {}
    def fit(x, y, u, contexts, weights, *, ridge):
        seen.update(n=len(x), ridge=ridge, contexts=contexts, weights=weights)
        return {'schema':'bilinear_test'}
    monkeypatch.setattr(experiment.lk, 'fit_bilinear', fit)
    model = experiment.fit([episode], 1e-4)
    assert seen['n'] == 640 and seen['ridge'] == 1e-4
    assert len(seen['contexts']) == 640
    assert model['training_configuration_names'] == ['long']
    assert model['fit_episode_hashes'] == {'source':'trace'}
