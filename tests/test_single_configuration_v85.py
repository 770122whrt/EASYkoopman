from types import SimpleNamespace
import pytest
from workflows.single_configuration_v85 import split_base, GRID


def episode(excitation, configuration='base'):
    return SimpleNamespace(case={'configuration': configuration, 'excitation': excitation,
        'run_id': configuration+'_'+excitation}, trace_sha256=configuration+'_'+excitation)


def test_fixed_excitation_split_never_trains_on_chirp():
    records=[episode('chirp'),episode('prbs'),episode('multisine'),episode('chirp','uuv4')]
    train, held = split_base(records)
    assert [e.case['excitation'] for e in train] == ['prbs','multisine']
    assert [e.case['excitation'] for e in held] == ['chirp']
    assert set(e.trace_sha256 for e in train).isdisjoint(e.trace_sha256 for e in held)
    assert GRID == (1e-8,1e-6,1e-4,.001,.1)


@pytest.mark.parametrize('bad',[
    [episode('prbs'),episode('chirp')],
    [episode('prbs'),episode('multisine'),episode('chirp'),episode('chirp')]])
def test_incomplete_or_duplicated_inventory_rejected(bad):
    with pytest.raises(ValueError,match='base_excitation_inventory'):
        split_base(bad)
