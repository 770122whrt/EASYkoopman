"""Strict matrix source identity and shared native-trace acceptance adapters."""
from functools import partial
import hashlib
import json
from pathlib import Path
from workflows import protocol_v88 as spec
from workflows.disturbance_data_v86 import ROOT,PHYSICAL_PATH,PHYSICAL_SHA256,context,frozen_physics
from workflows.disturbance_data_v86 import verify_manifest as _verify,load_episode as _load,validate_trace as _validate
from workflows.fit_disturbance_v87 import load_record

MODEL_PATH='docs/evidence/phase9/diverse-v87-20260929/server/model.json'
MODEL_SHA256='5857a0e8d09cd04e33112b457b6a60f8b4147f3819815634edb6149ac95e137e'
SUPPORT_PATH='docs/evidence/phase9/matrix-v88-20260929/support.json'
REQUIRED_SOURCES={MODEL_PATH,SUPPORT_PATH,PHYSICAL_PATH,'koopman/control_support_v88.py',
    'workflows/protocol_v88.py','workflows/disturbance_data_v88.py',
    'workflows/collect_disturbance_data_v88.py','workflows/evaluate_disturbance_v88.py',
    'workflows/prepare_disturbance_v88.py','workflows/freeze_support_v88.py',
    'workflows/solve_disturbance_v88.py'}


def frozen_model(path=ROOT/MODEL_PATH):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=MODEL_SHA256:
        raise ValueError('v88_frozen_model_changed')
    return load_record(path)


def verify_manifest(path):
    manifest=json.loads(Path(path).read_text(encoding='utf8'))
    if manifest.get('schema')!='v88-source-freeze' or not REQUIRED_SOURCES<=set(manifest.get('files',{})):
        raise ValueError('v88_manifest_sources')
    if manifest['files'][MODEL_PATH]!=MODEL_SHA256:raise ValueError('v88_frozen_model_manifest')
    return _verify(path,spec=spec)


load_episode=partial(_load,spec=spec)
validate_trace=partial(_validate,spec=spec)
