"""Package approved coverage; copy control modules byte-for-byte from frozen r3."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

CONFIGURATIONS=('uuv4','long_body','uuv6','uuv6_angled','uuv4_angled','heavy_moderate')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def package(root,output,*,allocation_warmup=False):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    prior=root/'docs/evidence/phase9/rate30-primary-v67-20260921'
    old=prior/'rate30-bundle-r3';manifest=json.loads((old/'MANIFEST.json').read_text())
    files={name:old/name for name in manifest['files_sha256'] if name not in ('protocol.json','supervisor.py','bin/check_rate30_worker_v67.py')}
    for name,path in files.items():
        if sha(path)!=manifest['files_sha256'][name]:raise ValueError('frozen_addon_changed')
    files['supervisor.py']=root/'workflows/supervise_multiconfig_v68.py'
    for name in ('check_multiconfig_worker_v68','analyze_failure_v68'):files['bin/'+name+'.py']=root/'workflows'/ (name+'.py')
    files['workflows/validate_support_failure_v68.py']=root/'workflows/validate_support_failure_v68.py'
    if allocation_warmup:files['bin/runtime_prepare_v61.py']=root/'workflows/runtime_prepare_v69.py'
    for name,source in files.items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
    protocol=json.loads((old/'protocol.json').read_text());templates=[q for q in protocol['cases'] if q['configuration']=='base']
    protocol.update(schema='phase9-multiconfiguration-v68',configuration_order=list(CONFIGURATIONS),
        authorization='User explicitly approved configuration-isolated support NO_GO, six further configurations, at most24cases/28minutes/zero_fit on2026-09-21',
        inherited_status=dict(base='four_arms_accepted_r3',asymmetric='support_no_go_at10physics_steps_r3'),
        limits=dict(total_seconds=1680,case_seconds=180,attempts=25,new_bytes_per_host=8*1024**2,retained_research_bytes_per_host=256*1024**2),
        expansion_gate='support_only_NO_GO_after_failed_prefix_reconstruction_isolates_configuration; any_other_failure_stops_all',
        cases=[dict(q,configuration=name,case_id=q['case_id'].replace('base-',name+'-',1)) for name in CONFIGURATIONS for q in templates])
    historical={}
    for name in ('base-pitch-feedback','base-pitch-mpc','base-depth-feedback','base-depth-mpc','asymmetric-pitch-feedback'):
        for filename in ('native.json','analysis.json','output/diagnostic.json.gz'):
            source=prior/'r3/results'/name/filename
            if source.exists():historical['/root/EASYkoopman-phase9-rate30-v67-r3-20260921/results/'+name+'/'+filename]=sha(source)
    protocol['historical_files_sha256']=historical
    if allocation_warmup:
        previous=root/'docs/evidence/phase9/multiconfig-v68-20260921/results'
        remote='/root/EASYkoopman-phase9-multiconfig-v68-20260921/results/'
        for relative in ('cpu-check/readiness.json','cpu-check/native.json','stage-result.json',
                         'uuv4-pitch-feedback/native.json','uuv4-pitch-feedback/output/diagnostic.json.gz'):
            historical[remote+relative]=sha(previous/relative)
        protocol.update(schema='phase9-multiconfiguration-v69-allocation-preparation',
            inherited_cpu_readiness_path=remote+'cpu-check/readiness.json',
            preparation_change='warm original topology-specific pinv/WLS on private tensors before unchanged reset snapshot gate; no state advance',
            historical_new_run_wall_seconds=read_stage_wall(previous),
            extra_allocation_probe_upper_seconds=30.,physical_starts_already_consumed=1)
        protocol['limits'].update(total_seconds=1540,attempts=23,new_bytes_per_host=7*1024**2)
    (output/'protocol.json').write_text(json.dumps(protocol,indent=2))
    m=dict(schema='phase9-multiconfiguration-addon-v68',files_sha256={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    (output/'MANIFEST.json').write_text(json.dumps(m,indent=2))
    archive=output.with_suffix('.tar.gz')
    with tarfile.open(archive,'x:gz') as tar:
        for name in [*m['files_sha256'],'MANIFEST.json']:tar.add(output/name,arcname=name,recursive=False)
    return dict(bundle=str(output),archive=str(archive),manifest_sha256=sha(output/'MANIFEST.json'),archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,
                unchanged_runtime_files=[n for n in files if n in manifest['files_sha256'] and sha(output/n)==manifest['files_sha256'][n]])

def read_stage_wall(previous):return json.loads((previous/'stage-result.json').read_text())['wall_seconds']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--allocation-warmup',action='store_true');args=p.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parents[1],args.output,allocation_warmup=args.allocation_warmup)))
