import copy
import json
from pathlib import Path
import pytest
from workflows.supervise_multiconfig_v68 import classify

def native(code=0):
    return dict(native_exit=code,reason='completed',group_stopped=True,remaining_group_pids=[],
        analysis=dict(native_exit=0,reason='completed',group_stopped=True,remaining_group_pids=[]))

def test_isolation_is_not_success():
    assert classify(native(),dict(status='physical_and_causal_replay_passed'))=='accepted'
    assert classify(native(1),failure=dict(status='configuration_support_no_go'))=='configuration_no_go'
    assert classify(native(1))=='global_stop'

@pytest.mark.parametrize('kind',['timeout','cleanup','analysis_exit','wrong_failure','wrong_native'])
def test_unclassified_or_infrastructure_failure_is_global(kind):
    n=native(1);failure=dict(status='configuration_support_no_go')
    if kind=='timeout':n['reason']='timeout'
    if kind=='cleanup':n['remaining_group_pids']=[123]
    if kind=='analysis_exit':n['analysis']['native_exit']=1
    if kind=='wrong_failure':failure['status']='unknown'
    if kind=='wrong_native':n['native_exit']=137
    assert classify(n,failure=failure)=='global_stop'

def test_bundle_copies_frozen_control_and_bounds_new_cases(tmp_path):
    from workflows.package_multiconfig_v68 import package
    root=Path(__file__).resolve().parents[1]
    result=package(root,tmp_path/'bundle')
    p=json.loads((tmp_path/'bundle/protocol.json').read_text())
    assert len(p['cases'])==24 and len(p['configuration_order'])==6
    assert p['limits']['total_seconds']==1680 and p['limits']['new_bytes_per_host']==8*1024**2
    assert all(c['controls']==60 and c['control_rate_hz']==30 and c['defer_gc'] for c in p['cases'])
    assert 'koopman/rate30_v67.py' in result['unchanged_runtime_files']
    assert 'bin/collect_effects_v67.py' in result['unchanged_runtime_files']
    assert all('base-' not in c['case_id'] and 'asymmetric-' not in c['case_id'] for c in p['cases'])

def test_preparation_fix_debits_failed_run_and_keeps_control_unchanged(tmp_path):
    from workflows.package_multiconfig_v68 import package
    root=Path(__file__).resolve().parents[1]
    result=package(root,tmp_path/'bundle',allocation_warmup=True)
    p=json.loads((tmp_path/'bundle/protocol.json').read_text())
    assert p['historical_new_run_wall_seconds']+p['extra_allocation_probe_upper_seconds']+p['limits']['total_seconds']<=1680
    assert p['limits']['attempts']+p['physical_starts_already_consumed']==24
    assert 'koopman/rate30_v67.py' in result['unchanged_runtime_files']
    assert 'bin/runtime_prepare_v61.py' not in result['unchanged_runtime_files']
    assert p['inherited_cpu_readiness_path'] in p['historical_files_sha256']


def test_inheritance_requires_real_accepted_complete_case(tmp_path):
    import gzip
    from workflows.supervise_multiconfig_v68 import accepted_prior_case
    folder=tmp_path/'case';(folder/'output').mkdir(parents=True)
    case=dict(case_id='uuv4-pitch-feedback',controls=60)
    (folder/'native.json').write_text(json.dumps(native()))
    (folder/'analysis.json').write_text(json.dumps(dict(status='physical_and_causal_replay_passed',case=case)))
    data=dict(case=case,status='diagnostic_returned',cleanup_errors=[],substeps=[{}]*240)
    with gzip.open(folder/'output/diagnostic.json.gz','wt') as f:json.dump(data,f)
    assert accepted_prior_case(folder,case)=='accepted'
    (folder/'native.json').write_text(json.dumps(native(-11)))
    with pytest.raises(ValueError,match='inherited_case_not_accepted'):accepted_prior_case(folder,case)


def test_separately_authorized_debugger_is_not_treated_as_research(tmp_path):
    from workflows.supervise_multiconfig_v68 import retained_research_bytes
    tool=tmp_path/'debugger';tool.mkdir();(tool/'library').write_bytes(b'abc')
    research=tmp_path/'research';research.mkdir()
    def scanner(path):
        assert path==research
        return 17
    assert retained_research_bytes([tool,research],scanner,debugger_root=str(tool))==17


def test_resource_amendment_needs_manifest_bound_launch_flag():
    from workflows.supervise_multiconfig_v68 import check_resource_approval
    p=dict(requires_resource_amendment_approval=True)
    for args in ([],['--resource-approval','other']):
        with pytest.raises(ValueError,match='explicit_resource'):check_resource_approval(p,'digest',args)
    check_resource_approval(p,'digest',['--resource-approval','digest'])
