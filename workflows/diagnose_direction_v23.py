"""Execute the predeclared fixed direction assay; never a formal model search."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from koopman.diagnostics_v23 import SourceOnlyReader, reserve_output, json_safe
from koopman.direction_probe_v23 import DirectionProbe, fit_probe_coefficients, complete_macro
from koopman.evaluation_v21 import DatasetFormalLocoBackendV21, load_protocol_episode_registry_v21
from koopman.model_v21 import build_observable_features_v21, build_increment_targets_v21
from koopman.metrics_v21 import RolloutEpisodeV21, rollout_episode_v21, OFFICIAL_ROLLOUT_POLICY_V21, _metric_values
from koopman.so3_v21 import apply_increment_target_v21
from workflows.diagnose_koopman_v23 import SOURCE_COMMIT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    mechanism_path=ROOT/'docs/evidence/phase8_3/repair-20260912/mechanism.json'
    mechanism=json.loads(mechanism_path.read_text(encoding='utf8'))
    sources=tuple(mechanism['per_configuration'])
    root=ROOT/'source/results/koopman_phase8_2/dataset'
    role=ROOT/'protocols/phase8_1/main_role_assignment_protocol.json'
    analysis=ROOT/'protocols/phase8_1/analysis_policy.json'
    assert sha(role)=='083d5eae3729e9939287345ab258dbfe4b4c8ca71ab769c2fd8616431a649417'
    assert sha(analysis)=='7a790b43d0f1581b8995ccdcbd9b6d259cb09bc8fe2268201400243d05f1e18c'
    registry=load_protocol_episode_registry_v21(role_protocol_path=role,inventory_path=root/'dataset_inventory.json')
    expected={b['episode_id']:b for b in mechanism['allowlist']}
    bindings=tuple(b for b in registry.episodes if b.episode_id in expected)
    assert len(bindings)==35 and all(b.to_dict()==expected[b.episode_id] for b in bindings)
    fits=tuple(b for b in bindings if b.role=='fit')
    vals=tuple(b for b in bindings if b.role=='validation')
    assert len(fits)==14 and len(vals)==21
    backend=DatasetFormalLocoBackendV21(dataset_root=root,analysis_policy_path=analysis,expected_source_commit=SOURCE_COMMIT,expected_evidence_level='server_isaac_smoke')
    reader=SourceOnlyReader(backend,bindings)
    out=reserve_output(ROOT/'docs/evidence/phase8_3',args.run_id)
    paths=[Path(__file__),ROOT/'koopman/direction_probe_v23.py',ROOT/'koopman/diagnostics_v23.py',ROOT/'koopman/model_v21.py',ROOT/'koopman/metrics_v21.py',ROOT/'koopman/so3_v21.py',ROOT/'.planning/phases/08.3-control-identification-forensics/08.3-01-PLAN.md',mechanism_path]
    report={'status':'started','evidence_level':'local_archived_source_exploratory_direction_assay',
            'model_handoff':False,'formal_selection':False,'validation_previously_inspected':True,
            'settings':{'ridge':1e-8,'normalization':'none','features':'so3_identity_v1','fit_count':8,'dt':1/60,
                        'horizons':[5,20,60,512],'origin':0,'one_step':'teacher_forced_all_512',
                        'kinematics':'forward Euler, current body velocity to world z; body-right rotation'},
            'inputs_sha256':{str(p.relative_to(ROOT)):sha(p) for p in paths},
            'allowlist':[b.to_dict() for b in bindings], 'opens':[], 'fits':{}, 'episodes':[]}
    for p in [Path(__file__),ROOT/'koopman/direction_probe_v23.py',paths[6]]:
        (out/(p.name+'.txt')).write_bytes(p.read_bytes())
    def save():
        report['opens']=[b.to_dict() for b in reader.opened]
        (out/'report.json').write_text(json.dumps(json_safe(report),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    save()
    try:
        loaded=[(b,reader.open_episode(b)) for b in fits]
        arrays={}
        for name in ('pooled',*sources):
            chosen=[(b,d) for b,d in loaded if name=='pooled' or b.configuration==name]
            x=np.concatenate([build_observable_features_v21(d.state_11,d.actuator_memory_4,d.virtual_control_4,'so3_identity_v1') for b,d in chosen])
            y=np.concatenate([build_increment_targets_v21(d.state_11,d.Y) for b,d in chosen])
            c,audit=fit_probe_coefficients(x,y,ridge=1e-8)
            arrays[name]=c
            report['fits'][name]={'episodes':[b.episode_id for b,d in chosen], 'samples':len(x),'diagnostics':audit,
                'coefficient_sha256':hashlib.sha256(c.tobytes()).hexdigest(),
                'velocity_state_block_spectral_radius':float(max(abs(np.linalg.eigvals(np.eye(6)+c[1:7,8:14]))))}
        np.savez(out/'coefficients.npz',**arrays)
        report['coefficient_file_sha256']=sha(out/'coefficients.npz')
        report['sealed_before_validation']=[b.episode_id for b in reader.opened]
        assert len(reader.opened)==14 and all(b.role=='fit' for b in reader.opened)
        report['status']='fit_sealed';save();print('8 fits sealed before validation',flush=True)
        for binding in vals:
            d=reader.open_episode(binding); ep=RolloutEpisodeV21.from_dataset(d)
            assert ep.transition_count==512 and abs(ep.control_dt_s-1/60)<1e-12
            models={'persistence':DirectionProbe(np.zeros((10,22)),dt=ep.control_dt_s),
                'constant_twist':DirectionProbe(np.zeros((10,22)),dt=ep.control_dt_s,kinematic_pose=True),
                'pooled':DirectionProbe(arrays['pooled'],dt=ep.control_dt_s),
                'per_configuration':DirectionProbe(arrays[binding.configuration],dt=ep.control_dt_s),
                'per_configuration_kinematic':DirectionProbe(arrays[binding.configuration],dt=ep.control_dt_s,kinematic_pose=True)}
            entry={'episode_id':binding.episode_id,'configuration':binding.configuration,'excitation':binding.family_repetition,'models':{}}
            truth=build_increment_targets_v21(d.state_11,d.Y)
            for name,model in models.items():
                delta=model.predict_increment(d.state_11,d.actuator_memory_4,d.virtual_control_4)
                pred=np.asarray([apply_increment_target_v21(x,dx) for x,dx in zip(d.state_11,delta,strict=True)])
                results={'one_step':{'status':'success','metrics':_metric_values(pred,d.Y),'increment_rmse_10':np.sqrt(np.mean((delta-truth)**2,axis=0))}}
                for h in report['settings']['horizons']:
                    trace=rollout_episode_v21(model,ep,start=0,steps=h,policy=OFFICIAL_ROLLOUT_POLICY_V21)
                    results[str(h)]={'status':trace.status,'reason':trace.reason_code,'completed':trace.completed_transition_count,
                        'metrics':_metric_values(trace.predictions,ep.targets_11[:h]) if trace.status=='success' else None}
                entry['models'][name]=results
            report['episodes'].append(entry);save();print(binding.configuration,binding.family_repetition,{n:r['512']['status'] for n,r in entry['models'].items()},flush=True)
        names=tuple(report['episodes'][0]['models'])
        report['summary']={}
        for name in names:
            report['summary'][name]={h:complete_macro([e['models'][name][h] for e in report['episodes']]) for h in ('one_step','5','20','60','512')}
        report['status']='completed_exploratory_no_selection';save()
    except Exception as exc:
        report['status']='failed';report['exception']=f'{type(exc).__name__}: {exc}';save();raise
    print(out,flush=True)


if __name__=='__main__':
    main()
