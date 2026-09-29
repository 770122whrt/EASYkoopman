"""Bounded joint-branch fallback; preserve every accepted v28 source solution.

The fallback searches all controllable command axes and refines after crossing
deadzone branches. It does not change the plant, demand or acceptance limits.
"""
import itertools
import numpy as np
from workflows.feedback_inverse_v28 import solve_feasible_control as previous_solve,batch_source_map,deadzone_distance,MINIMUM_DEADZONE_DISTANCE
from workflows.workpoint_v27 import mechanics,_steady,ACCELERATION_TOLERANCE
from workflows.control_seam_v23 import ControlKernel

def solve_feasible_control(name,target):
    previous=previous_solve(name,target)
    if previous['within_tolerance'] and deadzone_distance(previous['pwm_raw'])>MINIMUM_DEADZONE_DISTANCE:return previous
    target=np.asarray(target,dtype=float);m=mechanics(name);active=np.flatnonzero(m['control_mask_4'])
    k=ControlKernel(name);scale=np.r_[[m['mass_kg']]*3,m['inertia_kg_m2']]
    def residual(u):return (_steady(k,u)[0]-target)/scale/ACCELERATION_TOLERANCE
    def score(u):
        r=residual(u);raw=k.command(u,pre_tam=True)['pwm_raw']
        if np.max(np.abs(raw))>.95 or deadzone_distance(raw)<=MINIMUM_DEADZONE_DISTANCE:return (np.inf,np.inf)
        return (float(np.max(np.abs(r))),float(r@r))
    start=np.asarray(previous['command_4']);offsets=np.asarray(list(itertools.product((-.04,0.,.04),repeat=len(active))))
    seeds=np.tile(start,(len(offsets),1));seeds[:,active]+=offsets;seeds=np.clip(seeds,-.95,.95).astype(np.float32)
    w,raw=batch_source_map(k,seeds);r=(w-target)/scale/ACCELERATION_TOLERANCE
    maxima=np.max(np.abs(r),1);norms=np.sum(r*r,1)
    invalid=(np.max(np.abs(raw),1)>.95)|(np.min(np.abs(np.abs(raw.astype(float))-float(np.float32(.02))),1)<=MINIMUM_DEADZONE_DISTANCE)
    maxima[invalid]=np.inf
    candidates=[start]+[seeds[i].astype(float) for i in np.lexsort((norms,maxima))[:16] if np.isfinite(maxima[i])]
    mapping=np.stack([k.command(np.eye(4)[j],pre_tam=True)['pwm_raw'] for j in active],1)
    best=start.copy();best_score=score(best);iterations=0
    for u in candidates:
        for _ in range(24):
            iterations+=1;s=score(u)
            if s<best_score:best,best_score=u.copy(),s
            if best_score[0]<=1:break
            r=residual(u);h=1e-3
            jac=np.stack([(residual(np.clip(u+np.eye(4)[j]*h,-.95,.95))-residual(np.clip(u-np.eye(4)[j]*h,-.95,.95)))/(2*h) for j in active],1)
            delta=np.linalg.lstsq(jac,-r,rcond=1e-8)[0]
            trials=[u.copy()]
            for fraction in (1.,.5,.25,.125,.0625):
                v=u.copy();v[active]+=fraction*delta;trials.append(np.clip(v,-.95,.95))
            for row,pwm in zip(mapping,k.command(u,pre_tam=True)['pwm_raw']):
                norm=float(row@row)
                if norm==0:continue
                for edge in (-.020004,-.019996,.019996,.020004):
                    v=u.copy();v[active]+=(edge-pwm)*row/norm;trials.append(np.clip(v,-.95,.95))
            following=min(trials,key=score)
            if np.array_equal(following,u):break
            u=following
        s=score(u)
        if s<best_score:best,best_score=u.copy(),s
        if best_score[0]<=1:break
    u=best.astype(np.float32);w,sent=_steady(k,u);error=(w-target)/scale;margin=float(1-np.max(np.abs(sent['pwm_raw'])))
    return {'command_4':u.astype(float).tolist(),'target_wrench_6_n_nm':target.tolist(),
        'steady_wrench_6_n_nm':w.tolist(),'acceleration_error_6':error.tolist(),'pwm_raw':sent['pwm_raw'].astype(float).tolist(),
        'pwm_headroom':margin,'within_tolerance':bool(np.all(np.abs(error)<=ACCELERATION_TOLERANCE) and margin>=.05),
        'exact_equilibrium':bool(np.max(np.abs(error))<1e-6),'iterations':previous['iterations']+iterations,
        'refinement':'all_controllable_axes_branch_seeds_and_post_crossing_refinement_v31',
        'minimum_deadzone_distance_pwm':deadzone_distance(sent['pwm_raw']),'joint_branch_seed_count':len(seeds),
        'previous_failed_command_4':previous['command_4']}
