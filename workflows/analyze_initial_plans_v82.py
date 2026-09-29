"""Cross-evaluate authentic first MPC plans at a verified shared origin.

No optimizer is called and no future measured state is consumed. Lower model
cost for another arm's plan is a possible local-solver confound, not evidence
of counterfactual control benefit or of a global optimum.
"""
import argparse
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import numpy as np
from workflows.analyze_executed_prediction_v82 import (
    validate_admission,_native_binding,sha,analysis_platform,MODEL_CONTENT_SHA256,load_analysis_assets,plain)
from koopman.command_state_v39 import CausalCommandState
from koopman.preview_solver_v80 import ExactChecker
from koopman.preview_solver_v82 import load_model,verify_support,model_identity,make_predictor
from workflows.identify_sparse_world_v30 import from_record
from workflows.protocol_v77 import settings

ARMS=('physics','learned_0.001','learned_0.1')


def verify_common_origins(records):
    if set(records)!=set(ARMS):raise ValueError('common_origin_arm_inventory')
    base=records['physics'];diffs={}
    fields=('state','startup_command','observed_rotor','origin_rotor','origin_clock','observed_clock','reset_state')
    for name,item in records.items():
        if item['case']!=base['case']:raise ValueError('common_origin_case')
        for field in fields:
            a=np.asarray(item[field],dtype=float);b=np.asarray(base[field],dtype=float)
            if a.shape!=b.shape or not np.isfinite(a).all() or not np.allclose(a,b,atol=1e-7,rtol=0):
                raise ValueError('common_origin_'+field)
            diffs[field]=max(diffs.get(field,0.),float(np.max(np.abs(a-b))))
    return dict(absolute_tolerance=1e-7,relative_tolerance=0.,maximum_differences=diffs,
                common_origin_source='physics_trace_first_solve')


def cross_evaluate(checkers,origin,state,previous,reference,plans):
    if set(plans)!=set(ARMS):raise ValueError('plan_inventory')
    if any(np.asarray(p).shape!=(20,4) or not np.isfinite(p).all() for p in plans.values()):
        raise ValueError('plan_shape')
    if set(checkers)!=set(ARMS):raise ValueError('checker_inventory')
    cells=[]
    for model,checker in checkers.items():
        for source,plan in plans.items():
            result=checker.check(origin,state,plan,previous,reference)
            cells.append(dict(evaluation_model=model,plan_source=source,feasible=result['feasible'],
                cost=result['cost'],reason=result['reason'],rejection=result.get('rejection')))
    return cells


def _read_trace(path):
    path=Path(path);payload=path.read_bytes();data=json.loads(gzip.decompress(payload))
    acceptance_path=path.parent/'acceptance.json'
    collector_path=path.parent.parent/(path.parent.name+'.exit.json')
    validator_path=path.parent.parent/(path.parent.name+'-validation.exit.json')
    read=lambda p:json.loads(p.read_text(encoding='utf8'))
    accepted=read(acceptance_path);collector=read(collector_path);validator=read(validator_path)
    validate_admission(data,accepted,collector,validator,sha(payload))
    _native_binding(data,path,collector,validator)
    return data,dict(trace=str(path),trace_sha256=sha(payload),
        acceptance_sha256=sha(acceptance_path.read_bytes()),
        collector_exit_sha256=sha(collector_path.read_bytes()),validator_exit_sha256=sha(validator_path.read_bytes()),
        source_manifest_sha256=data['source_manifest_sha256'])


def _bind_model(data,arm,assets,loaded):
    cfg=data['case']['configuration'];m=data['model'];kind=data['case']['controller']
    if data['case']['preview_enabled'] is not True or data['case']['profile']!='depth4_h20':
        raise ValueError('comparison_preview_or_profile')
    profile=settings('depth4_h20')
    if (m['common_support_id']!=assets.domains[cfg].identity or m['weights']!=asdict(profile['weights'])
            or m['horizon_macro_steps']!=20 or m['pwm_planning_margin']!=3e-6 or m['pwm_optimizer_margin']!=4e-6):
        raise ValueError('comparison_common_control_contract')
    if arm=='physics' and data['schema']=='preview-control-v80':
        identity=dict(kind='identified_physics',symbolic_proxy='projected_koopman',
            unique_koopman_representation_claimed=False,pwm_planning_margin=3e-6,pwm_optimizer_margin=4e-6)
        if (kind!='identified_physics' or m['kind']!=kind or m['model_identity']!=identity
                or m['frozen_parameter_source_sha256']!=assets.model_sha256):
            raise ValueError('comparison_physics_identity')
    else:
        record=loaded['0.1'] if arm=='physics' else loaded[arm.removeprefix('learned_')]
        expected='matched_physics' if arm=='physics' else 'learned_velocity'
        identity=model_identity(record,expected)
        if (data['schema']!='learned-control-v82' or kind!=expected or m['kind']!=expected
                or m['model_identity']!=identity or m['prediction_artifact_sha256']!=record.file_sha256
                or m['prediction_content_sha256']!=identity['prediction_content_sha256']
                or m['common_support_model_sha256']!=assets.model_sha256):
            raise ValueError('comparison_learned_identity')


def _origin_record(data,assets):
    case=data['case'];cfg=case['configuration'];context=assets.context(cfg);steps=data['substeps']
    reset=data['reset_record']['snapshot'];before=steps[4]['before']
    if np.any(np.asarray(reset['actuator_speed_n'])!=0) or np.any(np.asarray(reset['_thruster_dynamics_time_s'])!=0):
        raise ValueError('comparison_zero_reset')
    command=np.asarray(steps[0]['execution_command_v55']['command'],dtype=np.float32)
    live=CausalCommandState(cfg,context,episode_id='initial-plan-comparison',zero_rotor_reset_verified=True)
    for index in range(4):
        issued=steps[index]['execution_command_v55']
        if issued['physics_index']!=index or not np.array_equal(np.asarray(issued['command'],dtype=np.float32),command):
            raise ValueError('comparison_startup_hold')
        live.record_issued(command,physics_index=index,episode_id='initial-plan-comparison')
    origin=live.snapshot(configuration=cfg,context=context,origin_control=2,episode_id='initial-plan-comparison')
    observed=np.asarray(before['actuator_speed_n'][0]);observed_clock=float(before['_thruster_dynamics_time_s'][0])
    if (np.max(np.abs(observed-origin._actuator.current()))>1e-3
            or abs(observed_clock-origin._actuator.elapsed_time)>1e-7):
        raise ValueError('comparison_actuator_replay')
    audits=[r for r in data['solve_audit'] if r['physics_index']==4]
    if len(audits)!=1:raise ValueError('comparison_first_solve')
    audit=audits[0];plan=np.asarray(audit['commands'],dtype=np.float32)
    if (plan.shape!=(20,4) or not np.isfinite(plan).all() or audit['exact_feasible'] is not True
            or audit['origin_control']!=2 or audit['preview_enabled'] is not True
            or not np.allclose(audit['reference'],case['reference'],atol=1e-12,rtol=0)
            or not np.allclose(plan[0],steps[4]['execution_command_v55']['command'],atol=1e-7,rtol=0)):
        raise ValueError('comparison_selected_plan')
    # No later physical observations are read; the stored future plan is model output.
    comparable_case={k:v for k,v in case.items() if k!='controller'}
    info=dict(case=comparable_case,state=np.asarray(before['state_11'][0]),startup_command=command,
        observed_rotor=observed,origin_rotor=origin._actuator.current().copy(),
        observed_clock=observed_clock,origin_clock=origin._actuator.elapsed_time,
        reset_state=np.asarray(reset['state_11'][0]))
    details=dict(selected_reference=audit['selected_reference'],solver_status=audit['status'],
        worker_status=audit['worker_status'],solver=audit['solver'],recorded_cost=audit['cost'],
        startup_actuator_replay_max_error=float(np.max(np.abs(observed-origin._actuator.current()))),
        plan_sha256=sha(plan.tobytes()),selected_plan=plan.tolist())
    return info,origin,plan,details


def analyze_group(paths,assets,model_directory):
    if set(paths)!=set(ARMS):raise ValueError('comparison_trace_inventory')
    loaded={}
    for ridge,digest in MODEL_CONTENT_SHA256.items():
        path=Path(model_directory)/f'pooled__learned_{ridge}.json';model=load_model(path,sha(path.read_bytes()))
        if model.record['content_sha256']!=digest:raise ValueError('comparison_frozen_model')
        verify_support(model,assets);loaded[ridge]=model
    old=from_record(json.loads(Path(assets.model_path).read_text()))
    for model in loaded.values():
        prior=from_record(model.record['physical_prior'])
        if (not np.array_equal(prior.matrix[:,10:16],old.matrix[:,10:16])
                or not np.array_equal(prior.damping,old.damping)
                or not np.array_equal(prior.quadratic,old.quadratic)
                or prior.angular_damping!=old.angular_damping):raise ValueError('comparison_same_data_physics')
    infos={};origins={};plans={};sources={}
    for arm,path in paths.items():
        data,source=_read_trace(path);_bind_model(data,arm,assets,loaded)
        info,origin,plan,detail=_origin_record(data,assets)
        infos[arm]=info;origins[arm]=origin;plans[arm]=plan;sources[arm]=dict(**source,**detail)
    equality=verify_common_origins(infos);common=infos['physics'];cfg=common['case']['configuration']
    context=assets.context(cfg);domain=assets.domains[cfg];profile=settings('depth4_h20')
    predictors={'physics':make_predictor('matched_physics',loaded['0.1'],context),
        **{'learned_'+r:make_predictor('learned_velocity',m,context) for r,m in loaded.items()}}
    checkers={key:ExactChecker(domain,predictor,**profile) for key,predictor in predictors.items()}
    cells=cross_evaluate(checkers,origins['physics'],common['state'],common['startup_command'],
                         common['case']['reference'],plans)
    physical={r['plan_source']:r for r in cells if r['evaluation_model']=='physics'};comparisons=[]
    for arm in ARMS[1:]:
        baseline=physical['physics'];other=physical[arm];valid=baseline['feasible'] and other['feasible']
        difference=baseline['cost']-other['cost'] if valid else None
        comparisons.append(dict(alternative_plan_source=arm,both_physically_predicted_feasible=valid,
            physical_predicted_cost_reduction=difference,
            reduction_exceeds_diagnostic_1e_8=difference>1e-8 if valid else None,
            inference='potential local-solver/initialization confound only; not counterfactual closed-loop benefit'))
    return dict(schema='initial-plan-cross-evaluation-v82/1',configuration=cfg,origin_physics=4,
        horizon_macro_steps=20,cross_cells=cells,physical_model_comparisons=comparisons,
        common_origin_check=equality,common_origin=common,sources=sources,
        prediction_model_identities={r:model_identity(m,'learned_velocity') for r,m in loaded.items()},
        common_support_id=domain.identity,common_support_model_sha256=assets.model_sha256,
        analysis_platform=analysis_platform(),new_solves=0,new_fits=0,new_physics_runs=0,
        future_measured_states_used=False,counterfactual_control_benefit=False,
        diagnostic_cost_tolerance=1e-8,tolerance_changes_no_runtime_gate=True,
        numerical_limit='Cross-platform cost differences around 1e-10 have been observed; report raw cost reductions and do not infer benefit from such micro-differences.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--physics',type=Path,required=True)
    p.add_argument('--learned-001',type=Path,required=True);p.add_argument('--learned-01',type=Path,required=True)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--models',type=Path)
    p.add_argument('--assets',type=Path)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    assets=load_analysis_assets(args.root,args.assets);models=args.models or args.root/'docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion'
    result=analyze_group(
        {'physics':args.physics,'learned_0.001':args.learned_001,'learned_0.1':args.learned_01},assets,models)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8') as stream:json.dump(plain(result),stream,indent=2,allow_nan=False)
    print(json.dumps(dict(output=str(args.output),configuration=result['configuration'],cells=len(result['cross_cells']))))


if __name__=='__main__':main()
