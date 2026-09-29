import numpy as np
import pytest

def test_new_validation_identity_and_excitation_are_disjoint():
    from workflows.identification_protocol_v32 import cases,pulse,protocol,validate_case
    from workflows.identification_protocol_v29 import cases as prior,pulse as prior_pulse
    qs=cases();old=prior();assert len(qs)==16
    assert all(q['role']=='validation' and q['training_eligible'] is False for q in qs)
    assert not ({q['seed'] for q in qs}&{q['seed'] for q in old})
    old_drives={prior_pulse(q).tobytes() for q in old}
    for q in qs:
        validate_case(q);assert pulse(q).tobytes() not in old_drives
        assert np.max(np.abs(pulse(q)),axis=0).shape==(4,)
        assert not pulse(q)[:128].any()
    assert protocol()['resource_cap']['collector_seconds']==5400
    assert protocol()['resource_cap']['native_processes_total_including_prior']==54

def test_repaired_policy_uses_same_target_and_original_tolerances():
    from workflows.feedback_v31 import FeedbackPolicy,parameters,validate_decision
    from workflows.feedback_v28 import FeedbackPolicy as Old,parameters as old_parameters
    p=parameters();before=old_parameters();p.pop('inverse_refinement');before.pop('inverse_refinement');assert p==before
    x=np.array([5.5,1,0,0,0,0,0,0,0,0,0.]);pulse=np.zeros(4)
    a=Old('base').decide(x,pulse);b=FeedbackPolicy('base').decide(x,pulse)
    assert a==b and validate_decision(b,x,pulse,'base')

def test_v32_runner_does_not_reopen_other_roles(tmp_path):
    from workflows.run_validation_v32 import prepare
    with pytest.raises(ValueError,match='validation_role_required'):prepare(tmp_path,tmp_path,'fit')

def test_v32_guard_does_not_admit_failed_native_zero():
    from workflows.identification_protocol_v32 import guarded_exit_code,cases
    q=cases()[0];source='a'*40
    d={'status':'completed_identification_pending_acceptance','request':q,'source_commit':source,'training_eligible':False,'model_fits':0}
    assert guarded_exit_code(0,d,q,source)==0
    assert guarded_exit_code(0,dict(d,status='failed_identification'),q,source)==1

def test_physics_and_sampling_body_unchanged_in_repaired_collector():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    before=(root/'workflows/collect_validation_v30.py').read_text()
    after=(root/'workflows/collect_validation_v32.py').read_text()
    for old,new in [('identification_protocol_v29','identification_protocol_v32'),('validation_release_v30','validation_release_v32'),('collect_validation_v30','collect_validation_v32'),('feedback_v28','feedback_v31')]:
        before=before.replace(old,new)
    assert before==after

def test_shared_ledger_inherits_failed_attempt_and_rejects_reset():
    from workflows.validation_release_v32 import validate_prior_budget
    from workflows.identification_protocol_v29 import cases
    a=[{'case':q['run_id'],'status':'exited','native_exit':0,'charged_seconds':1.} for q in cases() if q['role']!='validation']
    tail=['i29-asymmetric-validation-8806-prbs','i29-asymmetric-validation-8807-multisine','i29-base-validation-8800-prbs','i29-base-validation-8801-multisine','i29-long_body-validation-8802-prbs','i29-long_body-validation-8803-multisine']
    a += [{'case':q,'status':'exited','native_exit':int(i==5),'charged_seconds':1.} for i,q in enumerate(tail)]
    validate_prior_budget({'attempts':a,'charged_seconds':38.})
    with pytest.raises(ValueError):validate_prior_budget({'attempts':a,'charged_seconds':0.})
