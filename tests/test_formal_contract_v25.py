import importlib.util
import json
from pathlib import Path
import pytest


def module():
    assert importlib.util.find_spec('workflows.formal_contract_v25')
    from workflows import formal_contract_v25
    return formal_contract_v25


def test_proposal_inventory_is_exact_and_role_isolated():
    m=module();p=m.proposal();m.validate_proposal(p)
    assert len(p['entries'])==80
    assert sum(e['intervals'] for e in p['entries'])==37120
    assert sum(e['role']=='test' for e in p['entries'])==24
    assert len({e['run_id'] for e in p['entries']})==80


@pytest.mark.parametrize('mutation',['seed_overlap','extra_configuration','wrong_masked_amplitude','extra_case','wrong_horizon'])
def test_modified_proposal_is_rejected(mutation):
    m=module();p=m.proposal()
    if mutation=='seed_overlap':p['entries'][1]['seed']=8461
    elif mutation=='extra_configuration':p['entries'][0]['configuration']='heavy_duty'
    elif mutation=='wrong_masked_amplitude':p['entries'][0]['amplitudes'][0]=.1
    elif mutation=='extra_case':p['entries'].append(p['entries'][0].copy())
    else:p['entries'][1]['intervals']=128
    with pytest.raises(ValueError,match='formal_proposal_mismatch'):m.validate_proposal(p)


def test_pending_approval_cannot_authorize_a_case():
    m=module();p=m.proposal();policy=m.analysis_policy()
    with pytest.raises(ValueError,match='formal_d23_not_approved'):
        m.authorize(p,policy,{'decision':'pending'},'a'*40,p['entries'][0]['run_id'])


def test_approval_binds_exact_protocol_policy_and_source():
    m=module();p=m.proposal();policy=m.analysis_policy();source='a'*40
    approval={'approval_record_version':'phase8.4-d23-v25','decision':'approved','experiment_id':p['experiment_id'],'role_protocol_sha256':m.digest(p),'analysis_policy_sha256':m.digest(policy),'source_commit':source,'attestation_scope':'protocol_and_source_hash_binding_only','identity_assurance':'none'}
    case,binding=m.authorize(p,policy,approval,source,p['entries'][0]['run_id'])
    assert case==p['entries'][0] and binding['source_commit']==source
    for key in ['source_commit','role_protocol_sha256','analysis_policy_sha256']:
        bad=approval.copy();bad[key]='b'*len(bad[key])
        with pytest.raises(ValueError,match='formal_d23_binding'):m.authorize(p,policy,bad,source,case['run_id'])


def test_test_access_requires_source_bound_validation_freeze():
    m=module();p=m.proposal();case=next(e for e in p['entries'] if e['role']=='test')
    with pytest.raises(ValueError,match='formal_test_gate'):
        m.validate_stage(case,None,'a'*40,m.digest(p))
    preflight=p['entries'][0];m.validate_stage(preflight,None,'a'*40,m.digest(p))


def test_stage_gate_cannot_claim_eight_preflights_with_one_arbitrary_file():
    m=module();p=m.proposal();case=next(e for e in p['entries'] if e['role']=='fit')
    gate={'status':'all_eight_preflights_accepted','source_commit':'a'*40,'role_protocol_sha256':m.digest(p),
          'analysis_policy_sha256':m.digest(m.analysis_policy()),'configurations':p['configurations'],
          'artifact_sha256':{'arbitrary.txt':'b'*64}}
    with pytest.raises(ValueError,match='formal_preflight_inventory'):
        m.validate_stage(case,gate,'a'*40,m.digest(p))


def test_unapproved_public_entry_never_imports_or_invokes_simulation(tmp_path,monkeypatch):
    m=module();p=m.proposal();policy=m.analysis_policy()
    paths=[]
    for name,value in [('roles.json',p),('policy.json',policy),('approval.json',{'decision':'pending'})]:
        f=tmp_path/name;f.write_text(json.dumps(value));paths.append(str(f))
    monkeypatch.setattr(m,'source_identity',lambda:'a'*40)
    def forbidden(*args,**kwargs):raise AssertionError('simulation_started_without_approval')
    monkeypatch.setattr(m,'run_authorized',forbidden)
    with pytest.raises(ValueError,match='formal_d23_not_approved'):
        m.main(['--roles',paths[0],'--policy',paths[1],'--approval',paths[2],'--case',p['entries'][0]['run_id'],'--execute'])


def test_private_collector_rejects_missing_approval_before_runtime_or_output():
    m=module()
    from workflows.collect_formal_v25 import run_authorized_case
    with pytest.raises((ValueError,KeyError)):
        run_authorized_case(m.proposal()['entries'][0],{'source_commit':'a'*40})


def test_preflight_acceptance_rejects_native_failure_without_creating_gate(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m,'source_identity',lambda:'a'*40)
    transfer=tmp_path/'transfer';(transfer/'preflight').mkdir(parents=True)
    first=m.proposal()['entries'][0]
    (transfer/'preflight'/(first['run_id']+'.exit_status')).write_text('1')
    with pytest.raises(ValueError,match='formal_preflight_native_exit'):
        m.accept_preflights(tmp_path,transfer)
    assert not (tmp_path/m.RESULT_RELATIVE/'preflight-gate.json').exists()


def test_stage_runner_pending_approval_stops_before_output(tmp_path,monkeypatch):
    from workflows import run_formal_stage_v25 as runner
    m=module();transfer=tmp_path/'transfer';transfer.mkdir()
    for name,value in [('role_protocol.json',m.proposal()),('analysis_policy.json',m.analysis_policy()),('d23_approval.json',{'decision':'pending'})]:
        (transfer/name).write_text(json.dumps(value))
    monkeypatch.setattr(runner,'source_identity',lambda:'a'*40)
    with pytest.raises(ValueError,match='formal_d23_not_approved'):
        runner.prepare(tmp_path,transfer,'preflight')
    assert not (transfer/'preflight').exists()


def test_formal_topology_wrapper_rejects_configuration_aliasing():
    from workflows.collect_formal_v25 import validate_interval
    row={'before':{'telemetry':{'configuration':'uuv6'}},'command':{'telemetry':{'configuration':'uuv6'}}}
    with pytest.raises(ValueError,match='formal_trace_configuration_mismatch'):
        validate_interval([row,row],configuration='uuv6_angled')


@pytest.mark.parametrize('configuration',['base','long_body','heavy_moderate','asymmetric','uuv6','uuv6_angled','uuv4','uuv4_angled'])
def test_all_public_topologies_keep_count_mask_and_interval_validation(configuration):
    from workflows.collect_formal_v25 import validate_interval
    from easyuuv_nc.embodiments import qualification_record
    from test_validate_control_trace_v23 import row
    q=qualification_record(configuration);rows=[row(1),row(2)];n=q['thruster_count']
    for r in rows:
        for snapshot in (r['before'],r['command']):
            snapshot['telemetry']['configuration']=configuration
            snapshot['telemetry']['control_mask_4']=[list(q['control_mask'])]
            snapshot['telemetry']['motor_pwm_n']=[[.1]*n]
            snapshot['actuator_speed_n']=[[1.]*n]
            snapshot['_last_motor_values_raw']=[[.1]*n]
        r['actuator_update']['speed_command_n']=[[2.]*n]
    validate_interval(rows,configuration=configuration)
