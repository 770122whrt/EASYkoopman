"""Bind the eighteen historical models to the six columns actually executed."""
import hashlib
import json
from pathlib import Path

import numpy as np

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS
from workflows.identify_sparse_world_v30 import from_record

ANCHOR = 'docs/evidence/phase8_4/command-prediction-v37-20260913/freeze.json'
ANCHOR_SHA = 'cdc7f663a5f746f0819e5c43159d8f326d48345ec310a996c14b941931f89ec4'
MODEL_ROOT = 'source/results/phase8.4-sparse-world-pilot-v30-20260913/models'
FIT_SOURCE = '1fbfed1d85051845fcd28d9d799ebe364450c8b6'
EXECUTION_FILES = (
    'koopman/sparse_world_edmd_v30.py', 'koopman/physical_prediction_v29.py',
    'koopman/projected_edmd_v24.py', 'koopman/physical_terms_v26.py',
    'koopman/command_prediction_v37.py', 'workflows/identify_sparse_world_v30.py',
    'workflows/control_seam_v23.py', 'workflows/actuator_replay_v28.py',
    'workflows/feedback_v31.py', 'workflows/identification_prediction_v32.py',
    'easyuuv_nc/control_v24.py', 'easyuuv_nc/embodiments.py',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_manifest(root):
    root = Path(root)
    if sha(root/ANCHOR) != ANCHOR_SHA:
        raise ValueError('formal_model_anchor')
    anchor = json.loads((root/ANCHOR).read_text(encoding='utf8'))
    execution = {}
    for name in EXECUTION_FILES:
        if sha(root/name) != anchor['source_sha256'][name]:
            raise ValueError('formal_existing_execution_changed:'+name)
        execution[name] = anchor['source_sha256'][name]
    inventory_path = 'docs/evidence/phase8_4/identification-fit-20260913-r17/cache-inventory.json'
    if sha(root/inventory_path) != anchor['input_sha256'][inventory_path]:
        raise ValueError('formal_fit_inventory')
    inventory = json.loads((root/inventory_path).read_text(encoding='utf8'))
    acceptance_path = 'docs/evidence/phase8_4/server-identification-20260913-r17/fit/acceptance.json'
    if sha(root/acceptance_path) != inventory['fit_acceptance_sha256']:
        raise ValueError('formal_fit_acceptance')
    acceptance = json.loads((root/acceptance_path).read_text(encoding='utf8'))
    if acceptance['training_eligible'] is not True or acceptance['source_commit'] != FIT_SOURCE:
        raise ValueError('formal_fit_role')
    models = {}
    for family in ('nonlinear', 'linear'):
        for scope in ['pooled'] + ['heldout-'+c for c in SUPPORTED_EMBODIMENTS]:
            name = family+'__'+scope
            path = MODEL_ROOT+'/'+name+'.json'
            if sha(root/path) != anchor['input_sha256'][path]:
                raise ValueError('formal_model_changed:'+name)
            record = json.loads((root/path).read_text(encoding='utf8'))
            model = from_record(record)
            configs = [c for c in SUPPORTED_EMBODIMENTS if scope != 'heldout-'+c]
            if (record['configurations'] != configs or record['fit_source'] != FIT_SOURCE
                    or record['family'] != family
                    or any(h != acceptance['trace_sha256'].get(q) for q, h in record['fit_episode_hashes'].items())):
                raise ValueError('formal_model_training_exclusion')
            models[name] = dict(path=path, sha256=anchor['input_sha256'][path], family=family,
                training_configurations=configs, fit_episode_hashes=record['fit_episode_hashes'],
                active_matrix_sha256=hashlib.sha256(np.asarray(model.matrix[:, 10:16], dtype='<f8').tobytes(order='C')).hexdigest())
    return dict(schema='projected-operational-model-manifest-v38', anchor_path=ANCHOR,
        anchor_sha256=ANCHOR_SHA, models=models, active_output_columns=list(range(10, 16)),
        active_observables=['world_v0', 'world_v1', 'world_v2', 'body_w0', 'body_w1', 'body_w2'],
        execution_sha256=execution, kinematics='advance_old_frame_velocity using predicted six velocities',
        input='v37 bounded4D preTAM two physical substeps with complete command-driven rotor history',
        complete_lift_recurrence=False, model_fits=0, model_handoff=False,
        equivalent_parameter_model='same D/Q physical parameter model; not an independent algorithm victory')


def validate_manifest(manifest, root):
    if manifest != build_manifest(root):
        raise ValueError('formal_operational_manifest')
    return manifest
