"""Compare models on authenticated actual four-substep executed prefixes.

Each model receives identical current observations and executed commands. Its
own causal actuator recurrence supplies acceleration; no future measured state
corrects the four-step prediction. This is not counterfactual control benefit.
"""
import argparse
import gzip
import hashlib
import json
import importlib.metadata
from pathlib import Path,PurePosixPath
import platform
import sys
import numpy as np
from koopman.command_state_v39 import CausalCommandState
from koopman.learned_velocity_v81 import prepare_learned,validate_record
from koopman.physical_control_v76 import PhysicalPredictor

MODEL_CONTENT_SHA256={
    '0.001':'0b199fae1d2fac89ed3934c81beead09faf3c3d96666eed682e31d8cefc414f7',
    '0.1':'862b0e4f5203b35ce869bacff7a2387b58d5a035ff73a7f87aba9f0cec6e479f'}
SCHEMAS={'preview-control-v80':'preview-control-v80-acceptance/1',
         'learned-control-v82':'learned-control-v82-acceptance/1'}


def plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    return value


def load_analysis_assets(root,asset_root=None):
    if asset_root is not None:
        from workflows.runtime_assets_v56 import AssetLocation,load_assets
        return load_assets(AssetLocation(str(Path(asset_root).resolve()),'.','assets/v38/inputs',
            '5d8c4aa1264d93307dc0cf692757441509e75809206ed80006543ca5e4239632'),model_key='nonlinear__pooled')
    from workflows.diagnose_separation_v79 import prepare
    return prepare(root)[1]


def analysis_platform():
    try:torch_version=importlib.metadata.version('torch')
    except importlib.metadata.PackageNotFoundError:torch_version=None
    return dict(os=platform.platform(),machine=platform.machine(),python=sys.version,
        python_executable=sys.executable,numpy=np.__version__,torch=torch_version,
        command_dtype='float32',prediction_arithmetic='numpy float64 with float32 actuator/allocation recurrence',
        platform_matched_to_collection_established=False)


def sha(payload):return hashlib.sha256(payload).hexdigest()


def validate_admission(data,acceptance,collector_exit,validation_exit,trace_sha256):
    if any(type(r.get('native_exit')) is not int or r['native_exit']!=0 or r.get('group_stopped') is not True
           for r in (collector_exit,validation_exit)):
        raise ValueError('native_exit_or_process_group')
    if (acceptance.get('trace_sha256')!=trace_sha256
            or acceptance.get('status')!='accepted_bounded_simulation_time_closed_loop'
            or data.get('status')!='completed_pending_independent_acceptance'
            or acceptance.get('case')!=data.get('case')
            or data.get('schema') not in SCHEMAS
            or acceptance.get('acceptance_schema')!=SCHEMAS[data['schema']]
            or acceptance.get('physics_steps')!=240 or acceptance.get('actual_pwm_checks')!=240
            or acceptance.get('backend_allocation_checks')!=60):
        raise ValueError('executed_prefix_admission')


def _argument(command,name):
    if command.count(name)!=1:raise ValueError('native_command_binding')
    index=command.index(name)
    if index+1>=len(command):raise ValueError('native_command_binding')
    return command[index+1]


def _native_binding(data,trace,collector,validator):
    version='preview_v80' if data['schema']=='preview-control-v80' else 'learned_v82'
    c=collector['command'];v=validator['command'];case=data['case']
    if (_argument(c,'-m')!='workflows.collect_'+version or _argument(v,'-m')!='workflows.validate_'+version
            or PurePosixPath(_argument(c,'--output').replace('\\','/')).name!=trace.parent.name
            or PurePosixPath(_argument(v,'--trace').replace('\\','/')).parts[-2:]!=(trace.parent.name,trace.name)
            or _argument(v,'--native-exit')!='0'
            or _argument(c,'--configuration')!=case['configuration']
            or _argument(c,'--controller')!=case['controller']
            or _argument(c,'--preview')!=('on' if case['preview_enabled'] else 'off')
            or _argument(c,'--task')!=case['task']):
        raise ValueError('native_command_binding')


def step_errors(prediction,actual):
    p=np.asarray(prediction,dtype=float);t=np.asarray(actual,dtype=float)
    if p.shape!=t.shape or p.ndim!=2 or p.shape[1]!=11 or not np.isfinite(p).all() or not np.isfinite(t).all():
        raise ValueError('prefix_metric_input')
    pq=p[:,1:5]/np.linalg.norm(p[:,1:5],axis=1,keepdims=True)
    tq=t[:,1:5]/np.linalg.norm(t[:,1:5],axis=1,keepdims=True)
    delta=p[:,5:]-t[:,5:]
    return dict(depth_m=(p[:,0]-t[:,0]).tolist(),
        attitude_rad=(2*np.arccos(np.clip(np.abs(np.sum(pq*tq,axis=1)),0,1))).tolist(),
        linear_velocity_norm_m_s=np.linalg.norm(delta[:,:3],axis=1).tolist(),
        angular_velocity_norm_rad_s=np.linalg.norm(delta[:,3:],axis=1).tolist(),
        velocity_component_error=delta.tolist())


def predict_prefix(origin,state,command,predictors):
    """Intentionally has no ground-truth/future-observation argument."""
    micro=np.tile(np.asarray(command,dtype=np.float32),(2,1))
    return {name:origin.forecast(state,micro,predictor) for name,predictor in predictors.items()}


def _aggregate(rows):
    result=[]
    for model in sorted({r['model'] for r in rows}):
        group=[r for r in rows if r['model']==model];complete=[r for r in group if r['complete']]
        horizons=[]
        for tick in range(4):
            available=[r for r in group if r['completed_physics']>tick]
            metrics={}
            if available:
                for metric in available[0]['step_errors']:
                    values=np.asarray([r['step_errors'][metric][tick] for r in available])
                    metrics[metric]=dict(rmse=np.sqrt(np.mean(values*values,axis=0)).tolist(),
                        mean_absolute=np.mean(np.abs(values),axis=0).tolist(),
                        maximum_absolute=np.max(np.abs(values),axis=0).tolist())
            horizons.append(dict(substep=tick+1,available=len(available),missing=len(group)-len(available),metrics=metrics))
        result.append(dict(model=model,total_prefixes=len(group),complete_prefixes=len(complete),
            failed_prefixes=len(group)-len(complete),
            predicted_support_violations=sum(r['predicted_support_violation'] is not None for r in group),
            by_substep=horizons))
    return result


def analyze_trace(trace,assets,model_directory,*,collector_exit=None,validation_exit=None):
    trace=Path(trace);parent=trace.parent;read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
    acceptance_path=parent/'acceptance.json'
    collector_path=Path(collector_exit) if collector_exit else parent.parent/(parent.name+'.exit.json')
    validation_path=Path(validation_exit) if validation_exit else parent.parent/(parent.name+'-validation.exit.json')
    payload=trace.read_bytes();data=json.loads(gzip.decompress(payload));acceptance=read(acceptance_path)
    collector=read(collector_path);validation=read(validation_path)
    validate_admission(data,acceptance,collector,validation,sha(payload))
    _native_binding(data,trace,collector,validation)
    cfg=data['case']['configuration'];context=assets.context(cfg);domain=assets.domains[cfg]
    predictors={};identities={};priors=[]
    fit_sources={name:digest for d in assets.domains.values() for name,digest in d.fit_sources}
    for ridge,digest in MODEL_CONTENT_SHA256.items():
        path=Path(model_directory)/f'pooled__learned_{ridge}.json';model_payload=path.read_bytes();record=json.loads(model_payload)
        prior,_=validate_record(record,expected_sha256=digest);priors.append(prior)
        if record['physical_prior']['fit_episode_hashes']!=fit_sources:raise ValueError('common_fit_sources')
        key='learned_'+ridge;predictors[key]=prepare_learned(record,context,expected_sha256=digest)
        identities[key]=dict(file_sha256=sha(model_payload),content_sha256=digest)
    if (not np.array_equal(priors[0].matrix[:,10:16],priors[1].matrix[:,10:16])
            or priors[0].angular_damping!=priors[1].angular_damping):raise ValueError('matched_prior_mismatch')
    predictors['matched_physics']=PhysicalPredictor(priors[0],context,identified=True)
    identities['matched_physics']=dict(same_data_prior=True,common_support_model_sha256=assets.model_sha256,
        velocity_matrix_sha256=sha(priors[0].matrix[:,10:16].tobytes()),
        angular_damping=priors[0].angular_damping)
    initial=data['reset_record']['snapshot'];steps=data['substeps']
    if (len(steps)!=240 or np.any(np.asarray(initial['actuator_speed_n'])!=0)
            or np.any(np.asarray(initial['_thruster_dynamics_time_s'])!=0)):
        raise ValueError('prefix_reset_or_count')
    episode='executed-prefix:'+sha(payload);live=CausalCommandState(cfg,context,episode_id=episode,zero_rotor_reset_verified=True)
    rows=[];paired_model_differences=[];max_rotor_error=0.;max_clock_error=0.
    for index in range(0,240,4):
        pair=steps[index:index+4];before=pair[0]['before'];state=np.asarray(before['state_11'][0])
        command=np.asarray(pair[0]['execution_command_v55']['command'],dtype=np.float32)
        for offset,sub in enumerate(pair):
            issued=sub['execution_command_v55']
            if issued['physics_index']!=index+offset or not np.array_equal(np.asarray(issued['command'],dtype=np.float32),command):
                raise ValueError('prefix_command_hold')
        origin=live.snapshot(configuration=cfg,context=context,origin_control=index//2,episode_id=episode)
        rotor_error=float(np.max(np.abs(origin._actuator.current()-np.asarray(before['actuator_speed_n'][0]))))
        clock_error=abs(origin._actuator.elapsed_time-float(before['_thruster_dynamics_time_s'][0]))
        if rotor_error>1e-3 or clock_error>1e-7:raise ValueError('prefix_causal_actuator_reconstruction')
        max_rotor_error=max(max_rotor_error,rotor_error);max_clock_error=max(max_clock_error,clock_error)
        forecasts=predict_prefix(origin,state,command,predictors)
        # Future observations are accessed for scoring only after all forecasts.
        actual=np.asarray([s['state_after_physics_11'][0] for s in pair])
        for name,forecast in forecasts.items():
            predicted=np.asarray(forecast['predictions']);count=len(predicted)
            rows.append(dict(origin_physics=index,model=name,complete=forecast['complete'] and count==4,
                completed_physics=count,failure=forecast['failure'],command=command.tolist(),
                predicted_support_violation=domain.check_states(predicted) if count else {'reason':'no_prediction'},
                step_errors=step_errors(predicted,actual[:count]) if count else None))
        physical=forecasts['matched_physics']
        for name in MODEL_CONTENT_SHA256:
            key='learned_'+name;learned=forecasts[key]
            common=min(len(physical['predictions']),len(learned['predictions']))
            paired_model_differences.append(dict(origin_physics=index,model=key,against='matched_physics',
                comparable_substeps=common,model_to_model_difference_not_truth_error=True,
                step_difference=step_errors(learned['predictions'][:common],physical['predictions'][:common]) if common else None))
        if live.physics_index!=index:raise ValueError('prediction_advanced_execution_history')
        for offset in range(4):live.record_issued(command,physics_index=index+offset,episode_id=episode)
    return dict(trace=str(trace),trace_sha256=sha(payload),case=data['case'],configuration=cfg,
        acceptance_sha256=sha(acceptance_path.read_bytes()),
        collector_exit_sha256=sha(collector_path.read_bytes()),validator_exit_sha256=sha(validation_path.read_bytes()),
        server_acceptance_reused_not_rerun=True,prefix_prediction_only=True,
        analysis_platform=analysis_platform(),historical_source_gpu=data.get('gpu'),
        numerical_interpretation=dict(platform_error_floor_calibrated=False,
            warning='Report absolute errors alongside percentages. Differences around 1e-7 state units can be comparable to observed float32 cross-platform allocation/replay discrepancies; do not interpret these alone as learned-model benefit.',
            historical_uuv4_cross_platform_diagnostic=dict(prediction_max_absolute_difference=2.0914622546889172e-7,
                cost_max_absolute_difference=3.559534537782294e-10,pwm_max_absolute_difference=5.21540641784668e-8,
                source_files=['docs/evidence/phase9/preview-v80-20260926/uuv4-off-crossplatform-diagnostic.json',
                              'docs/evidence/phase9/preview-v80-20260926/uuv4-off-platform-comparison.json'],
                evidence_scope='separate v80 Windows/Linux full planned-horizon replay; not a measured four-step error floor',
                universal_error_bound=False,not_a_feasibility_or_acceptance_tolerance=True)),
        actual_controller=data['case']['controller'],model_identities=identities,
        causal_rotor_max_error=max_rotor_error,causal_clock_max_error=max_clock_error,
        completed_history_physics=live.physics_index,rows=rows,summary=_aggregate(rows),
        paired_model_differences=paired_model_differences)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--trace',type=Path,action='append',required=True)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--assets',type=Path)
    parser.add_argument('--models',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    assets=load_analysis_assets(args.root,args.assets)
    models=args.models or args.root/'docs/evidence/phase9/learned-velocity-v81-20260926/normalized-quaternion'
    results=[analyze_trace(trace,assets,models) for trace in args.trace]
    output=dict(schema='executed-prefix-prediction-v82/1',prefix_prediction_only=True,
        counterfactual_control_benefit=False,new_fits=0,new_physics_runs=0,
        conditioning='actual current state + independently reconstructed past actuator memory + same executed command',
        horizon_physics=4,future_measured_state='scoring only; never update within prefix',
        interpretation='compare model accuracy on identical executed actions; neither establishes nor is required for control benefit',
        traces=results)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8') as stream:json.dump(plain(output),stream,indent=2,allow_nan=False)
    print(json.dumps(dict(output=str(args.output),traces=len(results),prefixes_per_model=sum(len(r['rows'])//3 for r in results))))


if __name__=='__main__':main()
