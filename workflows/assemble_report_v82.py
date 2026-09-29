"""Bind accepted live trajectories before writing descriptive model comparisons."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from koopman.preview_solver_v82 import load_model,model_identity,verify_support
from workflows.diagnose_separation_v79 import prepare
from workflows.identify_sparse_world_v30 import from_record
from workflows.report_koopman_v82 import actual_metrics,check_pair
from workflows.analyze_executed_prediction_v82 import _native_binding
from koopman.control_objective_v44 import tracking_terms,control_mask

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidence/phase9'


def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_trace(stage,name,manifest):
    folder=stage/'final-return';trace=folder/name/'trace.json.gz';data=json.loads(gzip.decompress(trace.read_bytes()))
    server=read(trace.parent/'acceptance.json')
    local_file=stage/(name+'-local-portable-acceptance.json')
    if not local_file.exists():local_file=stage/(name+'-local-acceptance.json')
    if local_file.exists():
        local=read(local_file);validation_scope='original_server_and_full_local_portable_recheck'
    elif name=='uuv4-learned-0.001-on-r1':
        failure_file=stage/(name+'-local-portable-failure.json');failure=read(failure_file)
        if failure['trace_sha256']!=sha(trace) or failure['full_local_acceptance'] is not False:
            raise ValueError('report_local_failure_binding')
        local_file=folder/(name+'-strict-recheck.json');local=read(local_file)
        receipt=read(folder/'strict-recheck-uuv4-001.exit.json')
        if receipt['native_exit']!=0 or receipt['group_stopped'] is not True:raise ValueError('report_strict_recheck_exit')
        if (local['scope']!='same_native_runtime_strict_independent_recheck'
                or not local['same_native_python_path'] or local['source_manifest_sha256']!=sha(manifest)):
            raise ValueError('report_strict_recheck_binding')
        validation_scope='original_server_and_strict_same_runtime_recheck_windows_causal_preview_failed'
    else:raise ValueError('report_missing_independent_recheck:'+name)
    for record in (server,local):
        if (record['trace_sha256']!=sha(trace) or record['physics_steps']!=240
                or record['status']!='accepted_bounded_simulation_time_closed_loop'
                or record['actual_pwm_checks']!=240 or record['backend_allocation_checks']!=60):
            raise ValueError('report_acceptance_binding:'+name)
    receipts=[]
    for suffix in ('','-validation'):
        receipt=read(folder/(name+suffix+'.exit.json'))
        if receipt['native_exit']!=0 or receipt['group_stopped'] is not True:raise ValueError('report_native_exit:'+name)
        receipts.append(receipt)
    _native_binding(data,trace,*receipts)
    if data['source_manifest_sha256']!=sha(manifest):raise ValueError('report_source_binding:'+name)
    return data,dict(trace=str(trace.relative_to(ROOT)),trace_sha256=sha(trace),validation_scope=validation_scope,
        server_acceptance_sha256=sha(trace.parent/'acceptance.json'),independent_recheck_sha256=sha(local_file))


def main():
    physical_stage=EVIDENCE/'preview-v80-20260926';learned_stage=EVIDENCE/'learned-control-v82-20260926'
    mp=physical_stage/'source-manifest-r3.json';ml=learned_stage/'source-manifest-r2.json'
    pfiles=read(mp)['files'];lfiles=read(ml)['files']
    for path,digest in pfiles.items():
        if lfiles.get(path)!=digest:raise ValueError('report_common_source:'+path)
    for path,digest in lfiles.items():
        if path.endswith('.py') and sha(ROOT/path)!=digest:raise ValueError('report_local_source:'+path)
    for stage in (physical_stage,learned_stage):
        verify=read(stage/'final-return-verified.json')
        if verify['archive_sha256']!=sha(stage/'final-return.tar.gz'):raise ValueError('report_return_archive')
        inventory=read(stage/'final-return/final-return.json')
        for rel,digest in inventory['files'].items():
            if sha(stage/'final-return'/rel)!=digest:raise ValueError('report_return_file:'+rel)
    assets=prepare(ROOT)[1];old=from_record(read(assets.model_path));traces={};rows=[]
    for cfg in ('base','uuv4'):
        for arm in ('feedback','identified-off','identified-on'):
            name=cfg+'-'+arm+'-r1';data,binding=accepted_trace(physical_stage,name,mp);traces[name]=data
            rows.append(dict(case=name,configuration=cfg,arm=arm,**binding,**actual_metrics(data)))
    queue=read(learned_stage/'planned-queue.json');pairings=[]
    expected={c+'-learned-'+r+'-on-r1' for c in ('base','uuv4') for r in ('0.001','0.1')}
    if len(queue)!=4 or {q['name'] for q in queue}!=expected:
        raise ValueError('report_expected_four_unique_learning_cases')
    for item in queue:
        name=item['name'];data,binding=accepted_trace(learned_stage,name,ml)
        loaded=load_model(ROOT/item['model_path'],item['model_sha256']);verify_support(loaded,assets)
        if data['model']['model_identity']!=model_identity(loaded,'learned_velocity'):raise ValueError('report_model_identity')
        prior=from_record(loaded.record['physical_prior'])
        if (not np.array_equal(prior.damping,old.damping) or not np.array_equal(prior.quadratic,old.quadratic)
                or prior.angular_damping!=old.angular_damping):raise ValueError('report_physical_prior')
        # Compare the active projected velocity map as well as direct-equation parameters.
        if not np.array_equal(prior.matrix[:,10:16],old.matrix[:,10:16]):raise ValueError('report_physical_map')
        baseline=item['configuration']+'-identified-on-r1';check_pair(traces[baseline],data)
        arm='learned_'+str(loaded.record['ridge']);traces[name]=data
        rows.append(dict(case=name,configuration=item['configuration'],arm=arm,**binding,**actual_metrics(data)))
        pairings.append(dict(physical=baseline,learned=name,matched_prior=True,matched_task_reset_mechanics=True,
            prediction_file_sha256=loaded.file_sha256,physical_trajectory_explicitly_reused=True))
    for row in rows:
        feedback=next(r for r in rows if r['configuration']==row['configuration'] and r['arm']=='feedback')
        physical=next(r for r in rows if r['configuration']==row['configuration'] and r['arm']=='identified-on')
        for metric in ('normalized_tracking_score','actual_objective'):
            row[metric+'_gain_vs_feedback_percent']=100*(1-row[metric]/feedback[metric])
            row[metric+'_gain_vs_physical_on_percent']=100*(1-row[metric]/physical[metric])
    report=dict(schema='koopman-mpc-v82-descriptive-control-report/1',status='all_ten_native_runtime_accepted_local_scope_reported',
        scope='two_known_configurations_one_2s_development_task_each',common_source_files=len(pfiles),
        unseen_configuration_closed_loop_proven=False,statistical_significance_claimed=False,real_time_qualified=False,
        pairings=pairings,rows=rows)
    output=learned_stage/'control-comparison.json'
    with output.open('x',encoding='utf8') as f:json.dump(report,f,indent=2,allow_nan=False)
    fields=['configuration','arm','normalized_tracking_score','normalized_tracking_score_gain_vs_feedback_percent',
        'normalized_tracking_score_gain_vs_physical_on_percent','actual_objective','actual_objective_gain_vs_feedback_percent',
        'actual_objective_gain_vs_physical_on_percent','depth_rmse_m','attitude_rmse_rad','control_squared_integral',
        'cycle_median_ms','cycle_p95_ms','terminal_depth_error_m','terminal_attitude_error_rad']
    with (learned_stage/'control-comparison.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    series=[]
    for row in rows:
        d=traces[row['case']];x=np.vstack([d['reset_record']['snapshot']['state_11'][0],
            [s['state_after_physics_11'][0] for s in d['substeps']]])
        terms=tracking_terms(x,d['case']['reference'],control_mask(row['configuration']))
        series.append(dict(case=row['case'],configuration=row['configuration'],arm=row['arm'],
            trace_sha256=row['trace_sha256'],simulation_time_s=(np.arange(241)/120).tolist(),
            depth_error_mm=(1000*np.sqrt(terms['depth'])).tolist(),
            controllability_aware_attitude_error_mrad=(1000*np.sqrt(terms['attitude'])).tolist()))
    with (learned_stage/'actual-error-series.json').open('x',encoding='utf8') as f:json.dump(series,f,indent=2)
    print(json.dumps(dict(output=str(output),rows=len(rows),pairings=len(pairings))))


if __name__=='__main__':main()
