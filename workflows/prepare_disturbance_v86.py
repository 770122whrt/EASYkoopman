"""Freeze current experiment sources and the pre-disturbance physical artifact."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from workflows.protocol_v86 import protocol
from workflows.disturbance_data_v86 import ROOT,PHYSICAL_PATH,PHYSICAL_SHA256,frozen_physics,verify_manifest


def prepare(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);frozen_physics()
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    paths={p for p in tracked if p.endswith('.py') and
        (p.startswith(('koopman/','workflows/','easyuuv_nc/','tests/')) or '/' not in p)}
    # Only this explicitly versioned implementation; never sweep old untracked raw data.
    for folder in ('koopman','workflows','easyuuv_nc','tests'):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*v86.py'))
    paths.add(PHYSICAL_PATH)
    paths.add('easyuuv_nc/data/embodiment/embodiment.usd')
    manifest=dict(schema='v86-source-freeze',protocol=protocol(),physical_sha256=PHYSICAL_SHA256,
        git_base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)})
    path=output/'manifest.json';path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    verify_manifest(path)
    with tarfile.open(output/'source.tar.gz','w:gz') as archive:
        for p in sorted(paths):archive.add(ROOT/p,arcname=p,recursive=False)
        archive.add(path,arcname='v86-manifest.json')
    return dict(files=len(paths),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        bundle_sha256=hashlib.sha256((output/'source.tar.gz').read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    print(json.dumps(prepare(p.parse_args().output)),flush=True)
