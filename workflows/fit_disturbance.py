"""One frozen fit on diverse train episodes; no validation/test refitting."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from koopman.disturbance_lifted_v86 import fit,prepare
from koopman.lifted_propagation_v84 import seal,coordinates
from workflows.disturbance_data import (context,frozen_physics,load_episode,verify_manifest,PHYSICAL_SHA256,
    write_new,execution_provenance)
from workflows.disturbance_protocol import get_protocol

SPEC=get_protocol("v87")
cases,protocol,RIDGE=SPEC.cases,SPEC.protocol,SPEC.RIDGE


def training_arrays(episodes):
    if [e['case'] for e in episodes]!=[q for q in cases() if q['role']=='train']:
        raise ValueError('v87_training_inventory')
    if len({e['trace_sha256'] for e in episodes})!=16:raise ValueError('v87_duplicate_training')
    parts=[(e,0 if i==0 else 256) for i,e in enumerate(episodes)]
    return (np.concatenate([e['states'][start:-1] for e,start in parts]),
            np.concatenate([e['states'][start+1:] for e,start in parts]),
            np.concatenate([e['inputs'][start:] for e,start in parts]))


def train(data,manifest,output,*,source_archive=None):
    if Path(output).exists():raise FileExistsError(output)
    sha=verify_manifest(manifest,spec=SPEC,source_archive=source_archive)
    episodes=[load_episode(Path(data)/q['run_id'],sha,spec=SPEC) for q in cases() if q['role']=='train']
    x,y,u=training_arrays(episodes);prior,physical=frozen_physics()
    record=fit(x,y,u,context(),physical,ridge=RIDGE)
    record.update(physical_prior=prior,physical_file_sha256=PHYSICAL_SHA256,protocol=protocol(),
        collection_manifest_sha256=sha,fit_episode_hashes={e['case']['run_id']:e['trace_sha256'] for e in episodes},
        training_range=dict(state_min=x.min(0).tolist(),state_max=x.max(0).tolist(),
            max_linear_speed=float(np.max(np.linalg.norm(x[:,5:8],axis=1))),
            max_angular_speed=float(np.max(np.linalg.norm(x[:,8:],axis=1)))))
    record.update(execution_provenance(manifest,source_archive))
    record=seal(record);write_new(output,record);return record


def load_record(path):
    record=json.loads(Path(path).read_text(encoding='utf8'))
    if record.get('content_sha256')!=seal(record)['content_sha256']:raise ValueError('v87_model_hash')
    prior,physical=frozen_physics()
    if (record['physical_prior']!=prior or record['physical_file_sha256']!=PHYSICAL_SHA256
            or record['protocol']!=protocol() or record['lifted']['ridge']!=RIDGE
            or record['lifted']['training_rows']!=16640
            or len(set(record['fit_episode_hashes'].values()))!=16
            or set(record['fit_episode_hashes'])!={q['run_id'] for q in cases() if q['role']=='train'}):
        raise ValueError('v87_frozen_model_contract')
    for kind in ('koopman','hybrid'):prepare(record,context(),physical,kind=kind)
    return record,physical


def main():
    p=argparse.ArgumentParser(description='Fit v87 training protocol only; no validation/test selection')
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-archive',type=Path)
    a=p.parse_args();train(a.data,a.manifest,a.output,source_archive=a.source_archive)


if __name__=='__main__':main()
