"""Predeclared base-only disturbance experiment; no test-driven selection."""
import numpy as np
from workflows.protocol_v80 import case_spec as previous_case

RIDGE = .001
FRACTION = .2


def cases():
    roles = ['train']*4+['validation']*2+['test']*2
    signals = ['prbs','multisine']*3+['chirp']*2
    return [dict(run_id=f'v86-base-{role}-{86010+i}-{signal}',configuration='base',
        role=role,seed=86010+i,excitation=signal,controls=160,hidden_drag_fraction=FRACTION)
        for i,(role,signal) in enumerate(zip(roles,signals))]


def validate_split(train, validation, test):
    groups = [train,validation,test]
    if any(group != [q for q in cases() if q['role']==role]
           for group,role in zip(groups,['train','validation','test'])):
        raise ValueError('v86_episode_split')


def protocol():
    return dict(schema='disturbance-experiment-v86',cases=cases(),ridge=RIDGE,history_states=1,
        physics_dt=1/120,control_dt=1/30,prediction_horizon=80,prediction_origins=[256,384,512],
        max_depth_rmse_m=.002,max_attitude_rmse_rad=.004,initialization='current_state_only',
        disturbance='extra_quadratic_drag_fraction_0.2_plant_only',
        model_families=['physics','koopman','hybrid'],test_selection=False,
        closed_loop_seconds=2,configuration_generalization_claim=False,
        environment_generalization_claim=False,online_learning=False)


def excitation(q):
    if q not in cases():raise ValueError('v86_case')
    rng = np.random.default_rng(q['seed']);n=96;t=np.arange(n)/96
    result=np.zeros((160,4),np.float32);phase=rng.uniform(-np.pi,np.pi,(4,3))
    if q['excitation']=='prbs':
        h=np.array([[1,1,1,1],[1,-1,1,-1],[1,1,-1,-1],[1,-1,-1,1]])
        pairs=rng.choice([-1,1],(8,4));pairs[:4]=h[rng.permutation(4)]*rng.choice([-1,1],4)
    for axis,amp in enumerate([2.,1.,.5,.25]):
        if q['excitation']=='prbs':
            v=np.repeat(np.column_stack([pairs[:,axis],-pairs[:,axis]]).reshape(-1),6)
        elif q['excitation']=='multisine':
            v=np.sin(2*np.pi*t[:,None]*np.array([1+axis,3+axis,5+axis])+phase[axis]).mean(1)
        else:
            low,high=1+axis/4,4+axis
            v=np.sin(2*np.pi*t*(low+.5*(high-low)*t)+phase[axis,0])
        result[64:,axis]=amp*v
    return result


def case_spec(configuration,controller,preview_enabled,task):
    if configuration!='base' or controller not in ('physics','koopman','hybrid'):
        raise ValueError('v86_closed_loop_scope')
    q=previous_case(configuration,'identified_physics',preview_enabled,task)
    q.update(controller=controller,seed=86030,hidden_drag_fraction=FRACTION)
    return q
