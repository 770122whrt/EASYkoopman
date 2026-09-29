"""Assemble existing measured coverage; never infer unrun or failed pairs."""
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from workflows.compare_effects_v67 import classify_pair
import numpy as np


def summarize(repo):
    evidence=repo/'docs/evidence/phase9'
    current=evidence/'remaining-coverage-v73-20260921'
    roots=[evidence/'rate30-primary-v67-20260921/r3',evidence/'lifecycle-fix-v70-20260921',
        evidence/'uuv4-pairs-v71-20260921',current]
    cases={}; analyses={}; traces={}
    for root in roots:
        for folder in sorted((root/'results').iterdir()):
            p=folder/'output/diagnostic.json.gz'
            if not p.is_file():continue
            if folder.name in cases:raise ValueError('duplicate_primary_case')
            trace=json.loads(gzip.decompress(p.read_bytes()));traces[folder.name]=trace
            native=json.loads((folder/'native.json').read_text())
            complete=(folder/'analysis.json').is_file() and native['native_exit']==0
            if complete:analyses[folder.name]=json.loads((folder/'analysis.json').read_text())
            cases[folder.name]=dict(configuration=trace['case']['configuration'],complete=complete,
                exception=trace.get('exception'),physics_steps=len(trace['substeps']),
                native_exit=native['native_exit'],source=str(p.relative_to(repo)),
                trace_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    order=('base','asymmetric','uuv4','long_body','uuv6','uuv6_angled','uuv4_angled','heavy_moderate')
    rows={};pairs={}
    for name in order:
        expected=[f'{name}-{task}-{controller}' for task in ('pitch','depth') for controller in ('feedback','mpc')]
        rows[name]=dict(complete=[n for n in expected if n in cases and cases[n]['complete']],
            failed=[n for n in expected if n in cases and not cases[n]['complete']],not_run=[n for n in expected if n not in cases])
        for task in ('pitch','depth'):
            f,m=f'{name}-{task}-feedback',f'{name}-{task}-mpc'
            if f not in analyses or m not in analyses:continue
            commands=lambda n:np.asarray([r['decision']['packet']['command'] for r in traces[n]['intervals']])
            pair=classify_pair(analyses[f],analyses[m],command_difference=float(np.max(np.abs(commands(f)-commands(m)))))
            pair['cost_ratios_mpc_over_feedback']={k:analyses[m]['metrics'][k]/analyses[f]['metrics'][k]
                if analyses[f]['metrics'][k] else None for k in ('command_variation','applied_force_squared_N2_s','applied_torque_squared_Nm2_s')}
            pair['feedback_metrics']=analyses[f]['metrics'];pair['mpc_metrics']=analyses[m]['metrics']
            pairs[f'{name}-{task}']=pair
    stage=json.loads((current/'results/stage-result.json').read_text())
    audit=json.loads((current/'post-audit.json').read_text())
    for name,digest in audit['result_files_sha256'].items():
        if hashlib.sha256((current/name).read_bytes()).hexdigest()!=digest:raise ValueError('pullback_hash:'+name)
    if audit['original_dependency_changed'] or audit['addon_changed'] or audit['process_inventory'] or not audit['isaaclab_patch_unchanged']:
        raise ValueError('post_audit_failed')
    count=dict(configurations_attempted=len({v['configuration'] for v in cases.values()}),complete_cases=sum(v['complete'] for v in cases.values()),
        failed_cases=sum(not v['complete'] for v in cases.values()),not_run_cases=sum(len(v['not_run']) for v in rows.values()),
        complete_pairs=len(pairs),pair_verdicts=dict(Counter(v['verdict'] for v in pairs.values())))
    assert count['complete_cases']+count['failed_cases']+count['not_run_cases']==32
    return dict(status='bounded_coverage_report_terminal_global_stop',phase9_complete=False,
        counts=count,configurations=rows,cases=cases,pairs=pairs,
        v73_stage_result=stage,verified_pulled_files=len(audit['result_files_sha256']),
        physical_starts_v68_onward=8+stage['physical_starts'],
        conservative_server_seconds=800+stage['wall_seconds']+10,
        server_seconds_note='Prior800s reserve plus complete v73 wall826.347s plus10s final audit reserve; cap2400s',
        server_retained_bytes_at_audit=audit['retained_research_bytes'],debugger_bytes=audit['tool_bytes'],
        new_fits=0,background_processes=[],
        runtime_qualified=False,unseen_generalization_proven=False,unique_koopman_advantage_proven=False)


if __name__=='__main__':
    repo=Path(__file__).resolve().parents[1]
    result=summarize(repo)
    p=repo/'docs/evidence/phase9/remaining-coverage-v73-20260921/coverage-summary.json'
    with p.open('x',encoding='utf8') as f:json.dump(result,f,indent=2,ensure_ascii=False)
    print(json.dumps(result['counts']))
