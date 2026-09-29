import pytest
from workflows.calibrate_lifted_v84 import choose_ridge, source_split


def row(z=.001,angle=.002,complete=True,h=80):
    return {'horizon_physics':h,'complete':complete,'metrics':{'z_rmse_m':z,'attitude_rmse_rad':angle} if complete else None}


def test_failure_count_precedes_better_error_and_tie_prefers_larger_ridge():
    assert choose_ridge({1e-8:[row(0,0,False)],.001:[row()],.1:[row()]})['ridge']==.1


def test_max_window_combined_normalized_score_not_average():
    result=choose_ridge({.001:[row(.002,0),row(0,.004)],.1:[row(.0015,.003),row(.0015,.003)]})
    assert result['ridge']==.001
    assert result['score']==pytest.approx(1.)


def test_only_source_development_rows_used_and_non80_ignored():
    dev={.001:[row(.0001,.0001),row(99,99,h=128)],.1:[row()]}
    assert choose_ridge(dev)['ridge']==.001
    with pytest.raises(TypeError):
        choose_ridge(dev,outer_rows=[row(0,0)])


def test_outer_target_never_in_fit_or_development_split():
    source,fit,dev=source_split(['base','asymmetric','uuv4','uuv6'],'uuv6')
    assert source==['asymmetric','base','uuv4']
    assert fit==['asymmetric','base'] and dev=='uuv4'
    assert 'uuv6' not in fit and dev!='uuv6'


def test_missing_80_or_mismatched_window_counts_fail_closed():
    with pytest.raises(ValueError):choose_ridge({.001:[row(h=1)]})
    with pytest.raises(ValueError):choose_ridge({.001:[row()],.1:[row(),row()]})
