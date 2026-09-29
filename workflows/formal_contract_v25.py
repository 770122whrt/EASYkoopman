"""Exact formal proposal and fail-closed D-23 entry; no simulation on import."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS

EXPERIMENT='phase8.4-structured-formal-v25-20260912'
RESULT_RELATIVE='source/results/'+EXPERIMENT


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def proposal():
    entries=[]
    for configuration in SUPPORTED_EMBODIMENTS:
        roles=[('preflight',8450,'prbs',32)]
        roles += [(role,seed+i,family,512) for role,seed in [('fit',8451),('validation',8461),('test',8471)]
                  for i,family in enumerate(('prbs','multisine','chirp'))]
        for role,seed,family,intervals in roles:
            entries.append({'run_id':f'f25-{configuration}-{role}-{seed}-{family}',
                            'configuration':configuration,'role':role,'seed':seed,
                            'mode':'direct_pre_tam_v24','intervals':intervals,'excitation':family,
                            'amplitudes':[.04,.04,.08,.2],'hold_intervals':4,'trace':True,'replay_path':None})
    return {'version':'formal-physical-input-v25','experiment_id':EXPERIMENT,
            'remote_project_root':'/root/EASYkoopman-phase8-4-formal-20260912-r8',
            'result_relative':RESULT_RELATIVE,'configurations':list(SUPPORTED_EMBODIMENTS),
            'physics_dt_s':1/120,'decimation':2,'initialization':['authored_static_v1','declared_v1','episode_local_v1'],
            'actuator_clock':'float32_accumulated_v1','single_environment':True,'disturbances_noise_dr':False,
            'resource_cap':{'native_case_minutes':10,'gpu_batch_minutes':180,'cpu_analysis_minutes':60,'disk_gib':4},
            'entries':entries}


def analysis_policy():
    return {'version':'formal-structured-edmd-analysis-v25','experiment_id':EXPERIMENT,
            'families':['linear_free','nonlinear_free','linear_fixed','nonlinear_fixed'],
            'primary':'nonlinear_fixed','scopes':'eight_local_one_pooled_eight_source_only_heldout',
            'fits':68,'mean_ridge':.001,'std_floor':1e-6,'condition_limit':1e8,
            'fit_role_only':True,'validation_use':'fixed_gate_only_no_tuning','test_access':'after_source_bound_validation_and_model_freeze',
            'horizons_control':[1,20,60,128,512],'origins':'all_control_boundaries;512fixed_origin',
            'path_ticks':'all_physics_ticks','units':['m','rad','m/s','rad/s'],'denominator_floor':[.01]*4,
            'gates':{'primary_all_complete_and_512_stable':True,'mandatory_accuracy_horizons':[20,60,128],
                     'aggregate_normalized_max':1.,'each_configuration_normalized_max':1.05,
                     'each_configuration_each_metric_max':1.10,'combined_velocity_max':.9,
                     'each_configuration_velocity_better_seed_count':2,
                     'nonlinear_over_complete_linear_fixed_max':.9,'each_configuration_over_linear_max':1.05,
                     'both_endpoint_and_path':True,'state_abs_limit':100.,'native_source_semantic_failures_allowed':0},
            'uncertainty':{'paired_episode_block_bootstrap_replicates':2000,'seed':8490,'percentiles':[2.5,97.5],
                           'stratification':'within_configuration_whole_seed_family_blocks','interpretation':'exploratory_interval_with_only_three_test_blocks_per_configuration;not_population_proof'},
            'ablations':'reuse_both_nonlinear_operators_unprojected;fixed_input_ablation_retains_nonlinear_known_kick',
            'free_input_failures':'record_invalid_finite_comparison;never_treat_as_numeric_win',
            'handoff':'only_after_formal_gates_and_independent_closeout;pooled_fit_only_operator;matching_direct4DcausalNclock',
            'claims_excluded':['unseen_real_platform','hardware','closed_loop','Agentic_benefit','global_finite_linear_Koopman_closure']}


def validate_proposal(value):
    if value!=proposal():raise ValueError('formal_proposal_mismatch')


def authorize(roles,policy,approval,source_commit,case_id):
    validate_proposal(roles)
    if policy!=analysis_policy():raise ValueError('formal_analysis_policy_mismatch')
    if approval.get('decision')!='approved':raise ValueError('formal_d23_not_approved')
    expected={'approval_record_version':'phase8.4-d23-v25','decision':'approved','experiment_id':EXPERIMENT,
              'role_protocol_sha256':digest(roles),'analysis_policy_sha256':digest(policy),'source_commit':source_commit,
              'attestation_scope':'protocol_and_source_hash_binding_only','identity_assurance':'none'}
    if not re.fullmatch('[0-9a-f]{40}',source_commit) or approval!=expected:
        raise ValueError('formal_d23_binding')
    matches=[e for e in roles['entries'] if e['run_id']==case_id]
    if len(matches)!=1:raise ValueError('formal_case_not_approved')
    return dict(matches[0]),dict(expected,approval_sha256=digest(approval))


def validate_stage(case,gate,source_commit,role_sha):
    if case['role']=='preflight':return
    stage='validation_and_models_frozen' if case['role']=='test' else 'all_eight_preflights_accepted'
    if (not isinstance(gate,dict) or gate.get('status')!=stage or gate.get('source_commit')!=source_commit
            or gate.get('role_protocol_sha256')!=role_sha or gate.get('analysis_policy_sha256')!=digest(analysis_policy())
            or gate.get('configurations')!=list(SUPPORTED_EMBODIMENTS)
            or not isinstance(gate.get('artifact_sha256'),dict) or not gate['artifact_sha256']):
        raise ValueError('formal_test_gate' if case['role']=='test' else 'formal_preflight_gate')
    preflights={f"collection/{e['run_id']}/trace.json" for e in proposal()['entries'] if e['role']=='preflight'}
    if not preflights.issubset(gate['artifact_sha256']):raise ValueError('formal_preflight_inventory')
    if case['role']=='test' and (gate.get('fit_count')!=68 or gate.get('test_accessed') is not False):
        raise ValueError('formal_test_gate')
    if case['role']=='test':
        scopes=['local-'+c for c in SUPPORTED_EMBODIMENTS]+['pooled']+['heldout-'+c for c in SUPPORTED_EMBODIMENTS]
        ids={family+'__'+scope for family in analysis_policy()['families'] for scope in scopes}
        models=gate.get('frozen_models',{})
        if (set(models)!=ids or len(set(models.values()))!=68 or not set(models.values()).issubset(gate['artifact_sha256'])
                or gate.get('validation_summary') not in gate['artifact_sha256']):
            raise ValueError('formal_test_model_inventory')


def verify_gate_artifacts(gate,root):
    if gate is None:return
    allowed=(root/RESULT_RELATIVE).resolve()
    for name,sha in gate['artifact_sha256'].items():
        path=(allowed/name).resolve()
        if (not path.is_relative_to(allowed) or not path.is_file() or path.is_symlink()
                or not re.fullmatch('[0-9a-f]{64}',sha) or hashlib.sha256(path.read_bytes()).hexdigest()!=sha):
            raise ValueError('formal_stage_artifact_binding')
    from workflows.validate_formal_trace_v25 import validate_trace
    for case in proposal()['entries']:
        if case['role']=='preflight':
            trace=json.loads((allowed/'collection'/case['run_id']/'trace.json').read_text())
            validate_trace(trace,case,gate['source_commit'])
    if gate['status']=='validation_and_models_frozen':
        summary=json.loads((allowed/gate['validation_summary']).read_text())
        if (summary.get('status')!='validation_gates_passed' or summary.get('source_commit')!=gate['source_commit']
                or summary.get('role_protocol_sha256')!=gate['role_protocol_sha256']
                or summary.get('analysis_policy_sha256')!=gate['analysis_policy_sha256']
                or summary.get('test_accessed') is not False):raise ValueError('formal_test_validation_binding')
        for model_id,name in gate['frozen_models'].items():
            model=json.loads((allowed/name).read_text())
            if (model.get('model_id')!=model_id or model.get('source_commit')!=gate['source_commit']
                    or model.get('role_protocol_sha256')!=gate['role_protocol_sha256']
                    or model.get('analysis_policy_sha256')!=gate['analysis_policy_sha256']
                    or model.get('training_role')!='fit'):raise ValueError('formal_test_operator_binding')


def accept_preflights(root,transfer):
    """Produce a gate only from all eight actual validated traces and native exits."""
    from workflows.validate_formal_trace_v25 import validate_trace
    source=source_identity();roles=proposal();artifacts={};checks=[]
    allowed=root/RESULT_RELATIVE
    for case in roles['entries']:
        if case['role']!='preflight':continue
        if (transfer/'preflight'/(case['run_id']+'.exit_status')).read_text().strip()!='0':
            raise ValueError('formal_preflight_native_exit')
        relative=f"collection/{case['run_id']}/trace.json";path=allowed/relative
        checks.append(validate_trace(json.loads(path.read_text()),case,source))
        artifacts[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    result={'status':'all_eight_preflights_accepted','source_commit':source,'role_protocol_sha256':digest(roles),
            'analysis_policy_sha256':digest(analysis_policy()),'configurations':list(SUPPORTED_EMBODIMENTS),
            'artifact_sha256':artifacts,'checks':checks,'model_handoff':False}
    path=allowed/'preflight-gate.json'
    with path.open('x',encoding='utf8') as output:json.dump(result,output,indent=2)
    return path


def source_identity():
    from workflows.collect_koopman_v21_identification import _repository_commit
    return _repository_commit()


def run_authorized(case,binding,gate=None):
    from workflows.collect_formal_v25 import run_authorized_case
    return run_authorized_case(case,binding,gate)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roles',type=Path,required=True);parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--approval',type=Path);parser.add_argument('--stage-gate',type=Path)
    parser.add_argument('--case',required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv);roles=json.loads(args.roles.read_text());policy=json.loads(args.policy.read_text())
    validate_proposal(roles)
    if policy!=analysis_policy():raise ValueError('formal_analysis_policy_mismatch')
    if not args.execute:
        matches=[e for e in roles['entries'] if e['run_id']==args.case]
        if len(matches)!=1:raise ValueError('formal_case_not_approved')
        print(json.dumps({'status':'proposal_dry_run_only','case':matches[0],'role_protocol_sha256':digest(roles),'analysis_policy_sha256':digest(policy),'simulation_started':False}))
        return
    if args.approval is None:raise ValueError('formal_d23_not_approved')
    approval=json.loads(args.approval.read_text());source=source_identity()
    case,binding=authorize(roles,policy,approval,source,args.case)
    gate=json.loads(args.stage_gate.read_text()) if args.stage_gate else None
    validate_stage(case,gate,source,digest(roles))
    verify_gate_artifacts(gate,Path(__file__).resolve().parents[1])
    run_authorized(case,binding,gate)


if __name__=='__main__':main()
