"""Fresh paired disturbance-strength evaluation with all v87 model parameters frozen."""
import numpy as np

VERSION='v88'
COLLECTOR='workflows.collect_disturbance_data_v88'
LEVELS=(0.,.1,.3)


def cases():
    return [dict(run_id=f'v88-base-{role}-drag{int(100*fraction):02d}-{base+i}-{signal}',
        configuration='base',role=role,seed=base+i,excitation=signal,amplitude_scale=scale,
        controls=320,hidden_drag_fraction=fraction)
        for role,scale,base in [('validation',1.25,88000),('test',1.75,88100)]
        for fraction in LEVELS for i,signal in enumerate(('prbs','multisine','chirp','pulses'))]


def protocol():
    return dict(schema='disturbance-experiment-v88',cases=cases(),history_states=1,
        physics_dt=1/120,control_dt=1/30,prediction_horizon=80,
        prediction_origins=[384,640,896,1152],solver_origins=[384,896],
        max_depth_rmse_m=.002,max_attitude_rmse_rad=.004,initialization='current_state_only',
        disturbance='extra_quadratic_drag_plant_only',fractions=list(LEVELS),
        model_families=['physics','koopman','hybrid'],test_selection=False,
        model_fits=0,frozen_model_version='v87',paired_excitation_across_levels=True,
        configuration_generalization_claim=False,online_learning=False,
        closed_loop_admission='original_all_model_prediction_and_solver_gates')


def excitation(q):
    if q not in cases():raise ValueError('v88_case')
    # Same fixed v87 waveform algorithm, with fresh role-separated seeds.
    rng=np.random.default_rng(q['seed']);n=256;t=np.arange(n)/30
    out=np.zeros((320,4),np.float32)
    for axis,amp in enumerate([2.,1.,.5,.25]):
        phase=rng.uniform(-np.pi,np.pi,3)
        if q['excitation']=='prbs':
            dwell=int(rng.choice([8,12,16,24]));signs=rng.choice([-1.,1.],int(np.ceil(n/dwell)))
            v=np.repeat(signs,dwell)[:n]
        elif q['excitation']=='multisine':
            frequency=rng.uniform([.12,.4,.9],[.3,.8,1.7])
            v=np.sin(2*np.pi*t[:,None]*frequency+phase).sum(1)/2
        elif q['excitation']=='chirp':
            low=float(rng.uniform(.1,.3));high=float(rng.uniform(1.2,2.4))
            if rng.random()<.5:low,high=high,low
            v=np.sin(2*np.pi*(low*t+.5*(high-low)*t*t/(n/30))+phase[0])
        else:
            duration=int(rng.choice([16,24,32]))
            block=np.r_[np.linspace(0,1,8),np.ones(duration),np.linspace(1,0,8),np.zeros(8)]
            wave=np.r_[block,-block];v=np.roll(np.resize(wave,n),int(rng.integers(0,len(wave))))
        v-=v.mean();v/=max(1.,float(np.max(abs(v))))
        out[64:,axis]=amp*q['amplitude_scale']*v
    return out
