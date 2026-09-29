"""Predeclared descriptive pair decisions, never statistics from one seed."""
import math


def classify_pair(feedback, mpc, *, command_difference):
    if any(r['status']!='physical_and_causal_replay_passed' for r in (feedback,mpc)):
        raise ValueError('pair_not_qualified')
    a,b=feedback['case'],mpc['case']
    if a['controller']!='feedback' or b['controller']!='mpc':raise ValueError('pair_arms')
    if a.get('control_rate_hz')!=30 or b.get('control_rate_hz')!=30:raise ValueError('pair_control_clock')
    keys=('configuration','mode','controls','seed','reference','reference_id','model_key','control_rate_hz','defer_gc')
    if a.get('strategy','v65')!=b.get('strategy','v65'):raise ValueError('pair_strategy_mismatch')
    if any(a[k]!=b[k] for k in keys):raise ValueError('pair_not_matched')
    if any(r['physical_steps']!=4*a['controls'] for r in (feedback,mpc)):
        raise ValueError('pair_incomplete')
    f,m=feedback['metrics'],mpc['metrics']
    if f['mpc_activations']!=0 or m['mpc_activations']<1:raise ValueError('pair_activation')
    values=[command_difference]+[x[k] for x in (f,m) for k in
        ('normalized_tracking_score','depth_rmse_m','attitude_rmse_rad')]
    if not all(math.isfinite(v) and v>=0 for v in values):raise ValueError('pair_metric')
    base=f['normalized_tracking_score'];delta=base-m['normalized_tracking_score']
    fraction=delta/base if base>0 else None
    depth=f['depth_rmse_m']-m['depth_rmse_m']
    attitude=f['attitude_rmse_rad']-m['attitude_rmse_rad']
    if command_difference<=1e-7:verdict='no_distinct_mpc_intervention'
    elif fraction is not None and fraction>=.05 and (depth>=.0002 or attitude>=.0005):
        verdict='benefit_in_this_scenario'
    elif fraction is not None and fraction<=-.05:verdict='worse_in_this_scenario'
    else:verdict='no_material_benefit_in_this_scenario'
    return dict(verdict=verdict,score_relative_improvement=fraction,
        depth_rmse_improvement_m=depth,attitude_rmse_improvement_rad=attitude,
        command_max_difference=command_difference,statistical_significance_claim=False,
        unique_koopman_advantage_proven=False,runtime_qualified=False)
