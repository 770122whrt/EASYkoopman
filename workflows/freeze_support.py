"""Freeze a common envelope using only already-admitted v87 training traces."""
import argparse
import hashlib
from pathlib import Path
from koopman.control_support_v88 import derive_record,restore_domain,MODEL_SHA
from koopman.lifted_propagation_v84 import seal
from workflows.disturbance_data import load_episode,verify_manifest,write_new,execution_provenance
from workflows.fit_disturbance import load_record
from workflows.disturbance_protocol import get_protocol

SPEC=get_protocol("v87")
cases=SPEC.cases
from koopman.bounded_mpc_v44 import load_fit_domains

TRAIN_MANIFEST_SHA='a79174de72c5b3c3e5dce1f88c634b78c4bba76108486a3783c848dc708f7285'
OLD_MODEL='source/results/phase8.4-sparse-world-pilot-v30-20260913/models/nonlinear__pooled.json'


def freeze(data,manifest,model,assets,output,*,source_archive=None):
    if Path(output).exists():raise FileExistsError(output)
    sha=verify_manifest(manifest,spec=SPEC,source_archive=source_archive)
    if sha!=TRAIN_MANIFEST_SHA:raise ValueError('v88_training_manifest')
    if hashlib.sha256(Path(model).read_bytes()).hexdigest()!=MODEL_SHA:raise ValueError('v88_frozen_model')
    learned,_=load_record(model)
    old=load_fit_domains(assets,Path(assets)/OLD_MODEL)['base']
    episodes=[load_episode(Path(data)/q['run_id'],sha,spec=SPEC) for q in cases() if q['role']=='train']
    record=derive_record(old,episodes,MODEL_SHA,learned['fit_episode_hashes'])
    record=seal(dict(record,training_source_manifest_sha256=sha))
    domain=restore_domain(record,old,MODEL_SHA,learned['fit_episode_hashes'])
    write_new(output,record)
    return dict(support_sha256=hashlib.sha256(Path(output).read_bytes()).hexdigest(),
        domain_identity=domain.identity,training_episodes=len(episodes),model_fits=0,
        **execution_provenance(manifest,source_archive),
        old_bounds=old.record(),new_bounds=domain.record())


if __name__=='__main__':
    import json
    p=argparse.ArgumentParser()
    for key in ('data','manifest','model','assets','output'):p.add_argument('--'+key,required=True)
    p.add_argument('--source-archive',type=Path)
    a=p.parse_args();print(json.dumps(freeze(a.data,a.manifest,a.model,a.assets,a.output,source_archive=a.source_archive)),flush=True)
