"""Verify final server evidence and replay only newly returned uuv4 cases."""
from pathlib import Path
import gzip
import hashlib
import json
import tarfile
from workflows.diagnose_separation_v79 import prepare
from workflows.analyze_executed_prediction_v82 import _native_binding
from workflows.validate_portable_v82 import validate

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'docs/evidence/phase9/learned-control-v82-20260926'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    expected=read(STAGE/'final-archive-receipt.json')
    archive=STAGE/'final-return.tar.gz';dest=STAGE/'final-return'
    assert sha(archive)==expected['archive_sha256']
    dest.mkdir(exist_ok=False)
    with tarfile.open(archive,'r:gz') as t:
        for m in t.getmembers():
            target=(dest/m.name).resolve()
            if not target.is_relative_to(dest.resolve()) or not m.isfile():raise ValueError('unsafe_archive_member')
        t.extractall(dest,filter='data')
    inv=read(dest/'final-return.json')
    assert len(inv['cases'])==4
    for rel,h in inv['files'].items():assert sha(dest/rel)==h,rel
    manifest=read(STAGE/'source-manifest-r2.json')
    for rel,h in manifest['files'].items():
        if rel.endswith('.py'):assert sha(ROOT/rel)==h,rel
    assets=prepare(ROOT)[1];verified=[]
    for q in read(STAGE/'planned-queue.json'):
        name=q['name'];p=dest/name/'trace.json.gz';data=json.loads(gzip.decompress(p.read_bytes()))
        server=read(p.parent/'acceptance.json')
        assert server['trace_sha256']==sha(p) and server['status']=='accepted_bounded_simulation_time_closed_loop'
        native=read(dest/(name+'.exit.json'));validator=read(dest/(name+'-validation.exit.json'))
        for r in (native,validator):assert r['native_exit']==0 and r['group_stopped']
        _native_binding(data,p,native,validator)
        assert data['source_manifest_sha256']==sha(STAGE/'source-manifest-r2.json')
        target=STAGE/(name+'-local-portable-acceptance.json')
        if target.exists():
            local=read(target);assert local['trace_sha256']==sha(p)
        else:
            try:
                local=validate(data,assets,0,manifest=manifest,learned_model=ROOT/q['model_path'],learned_sha256=q['model_sha256'])
            except ValueError as error:
                if name!='uuv4-learned-0.001-on-r1' or str(error)!='causal_preview':raise
                failure=dict(status='cross_platform_causal_preview_not_reproduced',error=str(error),trace_sha256=sha(p),
                    full_local_acceptance=False,original_gates_unchanged=True,
                    diagnostic='uuv4-001-causal-preview-diagnostic.json')
                with (STAGE/(name+'-local-portable-failure.json')).open('x') as f:json.dump(failure,f,indent=2)
                local=read(dest/(name+'-strict-recheck.json'));receipt=read(dest/'strict-recheck-uuv4-001.exit.json')
                assert receipt['native_exit']==0 and receipt['group_stopped']
                assert local['scope']=='same_native_runtime_strict_independent_recheck'
                assert local['trace_sha256']==sha(p) and local['source_manifest_sha256']==sha(STAGE/'source-manifest-r2.json')
                assert local['same_native_python_path'] and local['verified_source_files']==len(manifest['files'])
                assert local['validator_sha256']==manifest['files']['workflows/validate_learned_v82.py']
                assert local['prediction_artifact_sha256']==q['model_sha256']
                assert read(STAGE/'uuv4-001-causal-preview-diagnostic.json')['all_other_gates_passed']
            else:
                local['trace_sha256']=sha(p)
                with target.open('x',encoding='utf8') as f:json.dump(local,f,indent=2,allow_nan=False)
        assert local['physics_steps']==240 and local['actual_pwm_checks']==240 and local['decision_audits']==59
        verified.append(dict(case=name,full_local_acceptance=target.exists(),recheck_scope=local.get('scope')))
        print(name+' '+str(verified[-1]),flush=True)
    for receipt in (dest/'analysis-tools').glob('*.receipt.json'):
        record=read(receipt);output=receipt.with_name(receipt.name.replace('.receipt.json','.json'))
        assert record['output_sha256']==sha(output)
        assert record['same_native_python_path'] and record['frozen_source_files_verified']==len(manifest['files'])
        for rel,h in record['analysis_source_sha256'].items():assert sha(receipt.parent/rel)==h
    record=dict(archive_sha256=sha(archive),inner_files_verified=len(inv['files']),
        local_frozen_python_sources_verified=sum(p.endswith('.py') for p in manifest['files']),
        server_frozen_source_files_verified=inv['frozen_source_files_verified'],
        verified_cases=verified,charged_seconds=inv['charged_seconds'],
        physical_starts=inv['physical_starts'],local_full_portable_revalidation=all(r['full_local_acceptance'] for r in verified))
    with (STAGE/'final-return-verified.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
    print(json.dumps(record),flush=True)

if __name__=='__main__':main()
