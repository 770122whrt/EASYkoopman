"""Read-only dictionary/residual/solver audit of frozen v81/v82 evidence.

No fit, solve, simulator or deployment. Height translation is a model-structure
probe in the declared uniform still-water dynamics, not an observed experiment.
"""
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from koopman.learned_velocity_v81 import validate_record,prepare_learned,velocity_target
from koopman.sparse_world_edmd_v30 import feature_names,lift
from koopman.prepared_projected_v40 import prepare_projected
from workflows.identify_sparse_world_v30 import load_fit_cache

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'docs/evidence/phase9'
MODELS=STAGE/'learned-velocity-v81-20260926/normalized-quaternion'
OUT=STAGE/'architecture-audit-v83-20260926'
GROUPS={'pose':(0,10),'world_linear_body_angular_velocity':(10,16),
        'rotated_axis_velocity':(16,25),'quadratic_drag':(25,37),
        'buoyancy_restoring_gyro_linear_drag':(37,52),'constant':(52,53)}

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    start=time.monotonic();episodes=load_fit_cache(ROOT);names=feature_names('nonlinear')
    assert len(names)==53 and sum(b-a for a,b in GROUPS.values())==53
    rows=[]
    for key in ['pooled']+['loco_'+c for c in dict.fromkeys(e.case['configuration'] for e in episodes)]:
        modelpath=MODELS/(key+'__learned_0.1.json');record=read(modelpath)
        train=[e for e in episodes if e.case['configuration'] in record['physical_prior']['configurations']]
        assert {e.case['run_id']:e.trace_sha256 for e in train}==record['physical_prior']['fit_episode_hashes']
        phi=np.concatenate([lift(e.states[:-1],e.context,'nonlinear') for e in train])
        target=np.concatenate([velocity_target(e.states[:-1],e.states[1:],e.acceleration,e.context,
             record['physical_prior']['angular_damping']) for e in train])
        weights=np.tile(np.r_[np.full(256,1/3),np.ones(384)],len(train));wn=weights/weights.sum()
        assert hashlib.sha256(phi.tobytes()+target.tobytes()+weights.tobytes()).hexdigest()==record['audit']['fit_feature_target_sha256']
        mean=wn@phi;std=np.sqrt(wn@((phi-mean)**2));scale=np.maximum(std,1e-6)
        np.testing.assert_allclose(mean,record['feature_mean'],atol=1e-12,rtol=1e-12)
        np.testing.assert_allclose(scale,record['feature_scale'],atol=1e-12,rtol=1e-12)
        centered=(phi-mean)/scale;sv=np.linalg.svd(centered,compute_uv=False)
        tol=sv[0]*max(centered.shape)*np.finfo(float).eps;rank=int((sv>tol).sum())
        assert rank==record['audit']['centered_feature_rank']
        # Weighted summation leaves ~1e-14 centering noise on the exact constant.
        # Do not count the amplified scale-floor noise as a new data direction.
        constant_columns=np.ptp(phi,axis=0)==0
        corrected=centered.copy();corrected[:,constant_columns]=0
        structural_sv=np.linalg.svd(corrected,compute_uv=False)
        structural_rank=int((structural_sv>structural_sv[0]*max(corrected.shape)*np.finfo(float).eps).sum())
        relation=phi[:,10:13]-phi[:,16:25].reshape(-1,3,3).sum(axis=1)
        assert np.max(abs(relation))<1e-12 and np.all(phi[:,37:39]==0) and np.all(phi[:,-1]==1)
        item=dict(fold=key,training_rows=len(phi),features=53,centered_rank=rank,
            rank_tolerance=float(tol),standardized_singular_values=sv.tolist(),
            constant_cleaned_centered_rank=structural_rank,
            exact_constant_features=[names[i] for i in np.where(constant_columns)[0]],
            constant_centering_roundoff_max=float(np.max(abs((phi-mean)[:,constant_columns]))),
            exact_world_velocity_redundancy_max=float(np.max(abs(relation))),
            zero_variance_features=[names[i] for i in np.where(std==0)[0]],
            below_scale_floor_features=[dict(name=names[i],std=float(std[i])) for i in np.where(std<1e-6)[0]],
            models=[])
        for ridge in (.001,.1):
            p=MODELS/(key+f'__learned_{ridge:g}.json');rec=read(p);physical,k=validate_record(rec)
            assert rec['audit']['fit_feature_target_sha256']==record['audit']['fit_feature_target_sha256']
            delta=k-physical.matrix[:,10:16]
            residual=phi@delta;target_residual=target-phi@physical.matrix[:,10:16]
            np.testing.assert_allclose(np.sqrt(wn@((residual-target_residual)**2)),rec['audit']['weighted_velocity_rmse'],atol=1e-12)
            selected=episodes if key=='pooled' else [e for e in episodes if e.case['configuration']==key[5:]]
            probes=[]
            for e in selected:
                x=e.states[[256,384,512]].copy();u=e.acceleration[[256,384,512]]
                learned=prepare_learned(rec,e.context);prior=prepare_projected(physical,e.context)
                for shift in (-.25,.25):
                    shifted=x.copy();shifted[:,0]+=shift
                    assert np.all((shifted[:,0]>3.5)&(shifted[:,0]<7.5))
                    old=prior(x,u,e.context);new=prior(shifted,u,e.context)
                    physical_error=float(np.max(abs(old[:,5:]-new[:,5:])))
                    assert physical_error==0
                    old=learned(x,u,e.context);new=learned(shifted,u,e.context)
                    diff=new[:,5:]-old[:,5:]
                    probes.append(dict(configuration=e.case['configuration'],episode=e.case['run_id'],shift_m=shift,
                        physics_velocity_change=physical_error,
                        learned_linear_velocity_change_max_m_s=float(np.max(np.linalg.norm(diff[:,:3],axis=1))),
                        learned_angular_velocity_change_max_rad_s=float(np.max(np.linalg.norm(diff[:,3:],axis=1)))))
            item['models'].append(dict(ridge=ridge,model_sha256=sha(p),content_sha256=rec['content_sha256'],
                free_matrix_shape=list(k.shape),nominal_entries=int(k.size),
                train_velocity_rmse=rec['audit']['weighted_velocity_rmse'],
                physical_train_velocity_rmse=rec['audit']['physical_prior_weighted_velocity_rmse'],
                learned_height_coefficients=delta[0].tolist(),height_translation_probes=probes))
        rows.append(item)
    solver=[]
    for cfg in ('base','uuv4'):
        p=STAGE/'learned-control-v82-20260926/final-return/analysis-tools'/(cfg+'-initial-plans-same-runtime.json')
        d=read(p);assert len(d['cross_cells'])==9 and all(c['feasible'] for c in d['cross_cells'])
        for model in ('physics','learned_0.001','learned_0.1'):
            cells=[c for c in d['cross_cells'] if c['evaluation_model']==model]
            own=next(c for c in cells if c['plan_source']==model);best=min(cells,key=lambda c:c['cost'])
            solver.append(dict(configuration=cfg,evaluating_model=model,own_cost=own['cost'],
                best_observed_plan=best['plan_source'],best_observed_cost=best['cost'],
                decrease_from_own_percent=100*(1-best['cost']/own['cost']),
                original_solver=d['sources'][model]['solver'],source_sha256=sha(p)))
    output=dict(scope='frozen_dictionary_and_solver_readonly_audit',new_fits=0,new_solves=0,new_physics_runs=0,
        feature_groups={k:dict(count=b-a,names=names[a:b]) for k,(a,b) in GROUPS.items()},folds=rows,
        first_origin_solver_regression=solver,height_translation_is_model_structure_probe_not_real_trajectory=True,
        conclusion='53 features have structural redundancies; residual freedom and finite solve quality require separate tests',
        elapsed_seconds=time.monotonic()-start)
    OUT.mkdir(exist_ok=True)
    with (OUT/'result-r2.json').open('x',encoding='utf8') as f:json.dump(output,f,indent=2,allow_nan=False)
    print(json.dumps(dict(folds=len(rows),ranks=[r['centered_rank'] for r in rows],
        constant_cleaned_ranks=[r['constant_cleaned_centered_rank'] for r in rows],seconds=output['elapsed_seconds'])),flush=True)

if __name__=='__main__':main()
