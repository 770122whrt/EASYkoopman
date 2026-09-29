"""Supplementary cross-platform revalidation of an already frozen v80/v82 trace.

The server's original acceptance remains required. Private module instances keep
the frozen validators unchanged. Only stored float64 forecast/cost comparisons
use portability tolerances; physical gates, causal command checks, selection
dominance, model identity, receipts and native cleanup retain their original rules.
"""
import hashlib
import importlib.util
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PREDICTION_ATOL=1e-6
COST_ATOL=1e-8


def _private_module(relative,manifest):
    path=ROOT/relative;digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest['files'].get(relative)!=digest:raise ValueError('portable_frozen_source:'+relative)
    spec=importlib.util.spec_from_file_location('_portable_'+path.stem,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def validate(data,assets,native_exit,*,manifest,**model_binding):
    """Supplement, never replace, server acceptance and artifact hash verification."""
    observed=[]
    def record(actual,expected,label,limit):
        a=np.asarray(actual,dtype=float);b=np.asarray(expected,dtype=float)
        if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError('portable_shape_or_finite:'+label)
        error=float(np.max(abs(a-b)))
        observed.append(dict(label=label,max_abs_error=error,allowed_atol=limit))

    decision=_private_module('workflows/validate_preview_decision_v79.py',manifest)
    original_decision_same=decision._same
    def decision_same(actual,expected,label,atol=1e-7):
        if label in ('recorded_cost','recorded_predictions'):
            atol=COST_ATOL if label=='recorded_cost' else PREDICTION_ATOL
            record(actual,expected,label,atol)
        return original_decision_same(actual,expected,label,atol=atol)
    decision._same=decision_same
    if data['schema']=='preview-control-v80':relative='workflows/validate_preview_v80.py'
    elif data['schema']=='learned-control-v82':relative='workflows/validate_learned_v82.py'
    else:raise ValueError('portable_schema')
    outer=_private_module(relative,manifest);outer.audit_decision=decision.audit_decision
    original_outer_same=outer.same
    def outer_same(a,b,*,atol=1e-6,label='values'):
        if label in ('plan_cost','independent_plan_replay'):
            atol=COST_ATOL if label=='plan_cost' else PREDICTION_ATOL
            record(a,b,label,atol)
        return original_outer_same(a,b,atol=atol,label=label)
    outer.same=outer_same
    result=outer.validate(data,assets,native_exit,**model_binding)
    result['scope']='supplementary_portable_full_revalidation'
    result['server_original_acceptance_required']=True
    result['portable_comparisons']=observed
    result['portable_prediction_atol']=PREDICTION_ATOL
    result['portable_cost_atol']=COST_ATOL
    result['physical_and_selection_gates_unchanged']=True
    result['portable_adapter_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result
