"""Actual-trajectory metrics and strict matched-run comparison, not predicted gain."""
from collections import Counter
import numpy as np
from koopman.control_objective_v44 import tracking_terms, control_mask


def check_pair(physical,learned):
    """Compare already authenticated/independently accepted v80 and v82 traces.

    This checks pairing, not artifact authenticity or solver correctness. Callers
    must additionally bind both native acceptances, manifests, and learned prior.
    Identity hashes should differ for prediction, but common support must match.
    """
    for key in ('configuration','task','profile','seed','preview_enabled','controls','reference'):
        if physical['case'][key]!=learned['case'][key]:raise ValueError('paired_case:'+key)
    for key in ('weights','horizon_macro_steps','common_support_id','pwm_planning_margin','pwm_optimizer_margin'):
        if physical['model'][key]!=learned['model'][key]:raise ValueError('paired_model:'+key)
    if physical['timing_mode']!=learned['timing_mode']:raise ValueError('paired_timing')
    pm=physical['model'];lm=learned['model'];pi=pm['model_identity'];li=lm['model_identity']
    expected_physical=dict(kind='identified_physics',symbolic_proxy='projected_koopman',
        unique_koopman_representation_claimed=False,pwm_planning_margin=3e-6,pwm_optimizer_margin=4e-6)
    if (physical['schema']!='preview-control-v80' or physical['case']['controller']!='identified_physics'
            or pm['kind']!='identified_physics' or pi!=expected_physical):raise ValueError('paired_physical_identity')
    if (learned['schema']!='learned-control-v82' or learned['case']['controller']!='learned_velocity'
            or lm['kind']!='learned_velocity' or li.get('kind')!='learned_velocity'
            or li.get('symbolic_proxy')!='learned_velocity_matrix_v81'
            or li.get('uses_learned_velocity_matrix') is not True
            or li.get('prediction_artifact_sha256')!=lm['prediction_artifact_sha256']
            or li.get('prediction_content_sha256')!=lm['prediction_content_sha256']
            or li.get('prediction_record_content_sha256')!=lm['prediction_content_sha256']):
        raise ValueError('paired_learned_identity')
    if pm['frozen_parameter_source_sha256']!=lm['common_support_model_sha256']:
        raise ValueError('paired_common_support_source')

    def near(a,b,label):
        a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
        if a.shape!=b.shape or not np.allclose(a,b,rtol=0,atol=1e-7):raise ValueError('paired_'+label)
    ps=physical['reset_record']['snapshot'];ls=learned['reset_record']['snapshot']
    for key in ('state_11','actuator_speed_n','_thruster_dynamics_time_s'):
        near(ps[key],ls[key],'reset_'+key)
    for key in ('transform_actor_world_xyzw','velocity_com_world_6','com_local_pose_xyzw'):
        near(ps['backend'][key],ls['backend'][key],'reset_backend_'+key)
    for key in ('body_local_corners_m','ground_world_corners_m','meters_per_unit','minimum_clearance_m'):
        near(physical['geometry'][key],learned['geometry'][key],'geometry_'+key)
    near(physical['intervals'][0]['decision']['packet']['command'],
         learned['intervals'][0]['decision']['packet']['command'],'startup_command')
    if len(physical['substeps'])!=len(learned['substeps']):raise ValueError('paired_steps')
    samples=[(ps,ls)]+[(a['before'],b['before']) for a,b in zip(physical['substeps'],learned['substeps'])]
    for a,b in samples:
        for key in ('fluid_velocity_world_3','thruster_efficiency_n','mass_kg','inertia_diagonal_kg_m2',
                    'com_to_cob_offset_m','volume_m3','drag_multiplier','thruster_dynamics_time_constant_s',
                    'water_density_kg_m3','dynamic_viscosity_pa_s','control_mask_4'):
            near(a['telemetry'][key],b['telemetry'][key],'environment_'+key)


def actual_metrics(data):
    x=np.asarray([s['state_after_physics_11'][0] for s in data['substeps']])
    u=np.asarray([s['decision']['packet']['command'] for s in data['intervals']])
    if x.shape!=(240,11) or u.shape!=(60,4) or not np.isfinite(x).all() or not np.isfinite(u).all():
        raise ValueError('complete_2s_trajectory_required')
    c=data['case'];terms=tracking_terms(x,c['reference'],control_mask(c['configuration']))
    weights=data['model']['weights'];weighted=sum(weights[k]*v for k,v in terms.items())
    effort=float(np.sum(u*u)/30);slew=float(np.sum(np.diff(np.vstack([np.zeros(4),u]),axis=0)**2)/60)
    cost=float(weighted.sum()/120+weights['terminal']*weighted[-1]+weights['effort']*effort+weights['slew']*slew)
    cycles=np.asarray([i['whole_cycle_wall_ms'] for i in data['intervals'][1:]])
    solves=data['solve_audit'];statuses=Counter(s['status'] for s in solves)
    sources=Counter(s.get('selected_reference','unrecorded') for s in solves)
    worker=Counter((s.get('solver') or {}).get('return_status','not_returned') for s in solves)
    return dict(normalized_tracking_score=float(np.mean(terms['depth']/.02**2+terms['attitude']/.04**2)),
        depth_rmse_m=float(np.sqrt(np.mean(terms['depth']))),attitude_rmse_rad=float(np.sqrt(np.mean(terms['attitude']))),
        terminal_depth_error_m=float(np.sqrt(terms['depth'][-1])),terminal_attitude_error_rad=float(np.sqrt(terms['attitude'][-1])),
        control_squared_integral=effort,actual_objective=cost,
        cycle_median_ms=float(np.median(cycles)),cycle_p95_ms=float(np.percentile(cycles,95)),
        cycle_max_ms=float(np.max(cycles)),solve_status_counts=dict(statuses),selected_reference_counts=dict(sources),
        nlp_return_status_counts=dict(worker),control_effort_is_not_energy_in_joules=True)
