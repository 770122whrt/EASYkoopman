"""Larger fixed motion experiment; unseen seeds, unchanged hidden drag and physics."""
import numpy as np
from workflows.protocol_v86 import case_spec as previous_case

VERSION='v87'
RIDGE=.001
COLLECTOR='workflows.collect_disturbance_data_v87'


def cases():
    rows=[]
    for role,scales,base in [('train',[.5,1.,1.5,2.],87000),('validation',[1.25],87100),('test',[1.75],87200)]:
        for scale in scales:
            for signal in ('prbs','multisine','chirp','pulses'):
                seed=base+len([r for r in rows if r['role']==role])
                rows.append(dict(run_id=f'v87-base-{role}-{seed}-{signal}',configuration='base',
                    role=role,seed=seed,excitation=signal,amplitude_scale=scale,controls=320,
                    hidden_drag_fraction=.2))
    return rows


def protocol():
    return dict(schema='disturbance-experiment-v87',cases=cases(),ridge=RIDGE,history_states=1,
        physics_dt=1/120,control_dt=1/30,prediction_horizon=80,
        prediction_origins=[384,640,896,1152],solver_origins=[384,896],
        max_depth_rmse_m=.002,max_attitude_rmse_rad=.004,initialization='current_state_only',
        disturbance='extra_quadratic_drag_fraction_0.2_plant_only',
        model_families=['physics','koopman','hybrid'],test_selection=False,
        startup_training='first_train_episode_only_256_rows',training_rows=16640,
        closed_loop_seconds=2,configuration_generalization_claim=False,
        environment_generalization_claim=False,online_learning=False)


def excitation(q):
    if q not in cases():raise ValueError('v87_case')
    rng=np.random.default_rng(q['seed']);n=256;t=np.arange(n)/30
    out=np.zeros((320,4),np.float32)
    for axis,amp in enumerate([2.,1.,.5,.25]):
        phase=rng.uniform(-np.pi,np.pi,3)
        if q['excitation']=='prbs':
            dwell=int(rng.choice([8,12,16,24]))
            signs=rng.choice([-1.,1.],int(np.ceil(n/dwell)))
            v=np.repeat(signs,dwell)[:n]
        elif q['excitation']=='multisine':
            frequency=rng.uniform([.12,.4,.9],[.3,.8,1.7])
            v=np.sin(2*np.pi*t[:,None]*frequency+phase).sum(1)/2
        elif q['excitation']=='chirp':
            low=float(rng.uniform(.1,.3));high=float(rng.uniform(1.2,2.4))
            if rng.random()<.5:low,high=high,low
            v=np.sin(2*np.pi*(low*t+.5*(high-low)*t*t/(n/30))+phase[0])
        else:
            # Longer bidirectional holds and smooth reversals, varying by axis.
            duration=int(rng.choice([16,24,32]))
            block=np.r_[np.linspace(0,1,8),np.ones(duration),np.linspace(1,0,8),np.zeros(8)]
            wave=np.r_[block,-block]
            v=np.roll(np.resize(wave,n),int(rng.integers(0,len(wave))))
        v-=v.mean();v/=max(1.,float(np.max(abs(v))))
        out[64:,axis]=amp*q['amplitude_scale']*v
    return out


def case_spec(configuration,controller,preview_enabled,task):
    q=previous_case(configuration,controller,preview_enabled,task)
    q['seed']=87300
    return q
