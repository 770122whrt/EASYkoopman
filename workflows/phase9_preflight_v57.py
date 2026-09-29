"""Fixed interface preflight; new release approval is separate from v38."""
import hashlib
import json
from pathlib import Path

from workflows.runtime_assets_v56 import confined


CONFIGURATIONS=('base','long_body','heavy_moderate','asymmetric','uuv6','uuv6_angled','uuv4','uuv4_angled')
REQUIRED_RUNTIME_FILES=(
    'easyuuv_nc/env/easyuuv_env.py','SOURCE_MANIFEST.json','ASSET_RELOCATION.json',
    'koopman/solver_worker_v49.py','koopman/cached_checks_v53.py',
    'koopman/plan_continuity_v54.py','koopman/runtime_coordinator_v52.py',
    'workflows/runtime_assets_v56.py','workflows/isaac_execution_v55.py',
    'workflows/runtime_audit_v57.py',
    'workflows/runtime_episode_v57.py','workflows/phase9_preflight_v57.py',
    'workflows/collect_runtime_v57.py','workflows/validate_runtime_v57.py')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def cases():
    return [dict(case_id='p9-v57-'+name,configuration=name,seed=19000+i,controls=32,
                 reference=[5.5,1.,0.,0.,0.],reference_id='upright-z5.5-v57',model_key='nonlinear__pooled')
            for i,name in enumerate(CONFIGURATIONS)]


def proposal():
    return dict(schema='phase9-runtime-preflight-v57',cases=cases(),
        maximum_wall_seconds=1800,maximum_case_seconds=180,maximum_new_bytes=512*1024**2,
        maximum_processes='one_supervisor_one_collector_one_solver; sequential_cases_single_compute_thread',
        physics_dt_s=1/120,decimation=2,control_dt_s=1/60,full_cycle_budget_s=1/60,
        solver_request_timeout_ms=100,worker_startup_timeout_s=60,
        horizon=20,prefix_controls=8,require_at_least_one_mpc_activation=True,
        ordering='base_first_then_remaining_catalog_only_if_all_previous_cases_pass',
        on_failure='preserve_partial_execution_and_stop_stage_no_retry',
        maximum_new_physics_steps=512,model_fits=0,new_fits=0,formal_test_access=False,
        reference_changes=0,new_gpu_training=False,control_benefit_claim=False,
        claim='source_bound_actual_execution_and_measured_cycle_preflight_only',
        next_gate='matched_control_and_model_comparators_require_their_own_frozen_protocol')


def verify_release(root):
    root=Path(root).resolve();path=root/'PHASE9_RELEASE.json';payload=path.read_bytes();r=json.loads(payload)
    if (r.get('schema')!='phase9-executable-release-v57' or r.get('protocol_sha256')!=digest(proposal())
            or not set(REQUIRED_RUNTIME_FILES)<=set(r.get('files_sha256',{}))):
        raise ValueError('runtime_release_inventory_or_protocol')
    for rel,expected in r['files_sha256'].items():
        p=confined(root,rel)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError('runtime_release_source_hash:'+rel)
    return dict(release_sha256=hashlib.sha256(payload).hexdigest(),protocol_sha256=digest(proposal()),manifest=r)


def authorize_case(root,case,approval):
    if (not isinstance(approval,dict) or approval.get('schema')!='phase9-runtime-preflight-approval-v57'
            or approval.get('approved') is not True):
        raise ValueError('runtime_new_explicit_approval_required')
    if case not in cases():raise ValueError('runtime_case_scope')
    release=verify_release(root)
    if any(approval.get(k)!=release[k] for k in ('release_sha256','protocol_sha256')):
        raise ValueError('runtime_approval_binding')
    return dict(release_sha256=release['release_sha256'],protocol_sha256=release['protocol_sha256'],case=dict(case))
