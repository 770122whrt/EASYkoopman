"""Current 30 Hz environment configuration and physical context readback checks."""
import numpy as np
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS,qualification_record
from koopman.prepared_physics import _context_key
from koopman.physics_context import PhysicalContext

def configure_environment(cfg, configuration, seed):
    if configuration not in EMBODIMENT_CONFIGS or type(seed) is not int:
        raise ValueError('runtime_environment_request')
    cfg.scene.num_envs=1;cfg.eval_mode=True;cfg.cap_episode_length=False;cfg.reference_mode='step'
    cfg.disturbance_cfg.mode='none';cfg.noise_cfg.enable_noise=False
    cfg.domain_randomization.use_custom_randomization=False
    cfg.control_history_reset_mode='episode_local_v1';cfg.inertia_sync_mode='declared_v1'
    cfg.physics_initialization_mode='authored_static_v1';cfg.initial_embodiment_type=configuration
    cfg.control_input_mode='direct_pre_tam_v24';cfg.seed=seed;cfg.starting_depth=5.5;cfg.ground_plane_mode='grid'
    cfg.decimation=4;cfg.control_rate_hz_v67=30;cfg.sim.render_interval=4


def check_runtime_context(snapshot, configuration, expected):
    """Compare actual PhysX mechanics AND declared hydrodynamics with fit context."""
    try:
        t=snapshot['telemetry'];b=snapshot['backend'];q=qualification_record(configuration)
        count=q['thruster_count'];declared=EMBODIMENT_CONFIGS[configuration]
        def array(value,shape):
            a=np.asarray(value,dtype=float)
            if a.shape!=shape or not np.isfinite(a).all():raise ValueError('shape_or_finite')
            return a
        def same(value,target,shape,atol):
            a=array(value,shape)
            if not np.allclose(a,target,rtol=0,atol=atol):raise ValueError('value_mismatch')
            return a
        if t['configuration']!=configuration:raise ValueError('configuration')
        mass=same(b['mass_kg'],[[expected.mass]],(1,1),1e-5)
        same(t['mass_kg'],mass,(1,1),1e-5)
        inverse=array(b['inverse_mass_per_kg'],(1,1)).astype(np.float32)
        if not np.array_equal(inverse,np.float32(1)/mass.astype(np.float32)):raise ValueError('inverse_mass')
        inertia=same(b['inertia_9'],np.diag(expected.inertia).reshape(1,9),(1,9),1e-6)
        same(t['inertia_diagonal_kg_m2'],expected.inertia[None],(1,3),1e-6)
        same(b['gravity_world_m_s2'],[0,0,-expected.gravity],(3,),1e-6)
        same(b['gravity_disabled'],[[0]],(1,1),0)
        same(t['control_mask_4'],[q['control_mask']],(1,4),0)
        same(t['thruster_dynamics_time_constant_s'],[declared['dyn_time_constant']],(1,),1e-7)
        observed=PhysicalContext(float(mass.item()),inertia.reshape(3,3).diagonal(),
            array(t['com_to_cob_offset_m'],(1,3))[0],array(t['volume_m3'],(1,1)).item(),
            array(t['drag_multiplier'],(1,)).item(),float(t['water_density_kg_m3']),
            float(t['dynamic_viscosity_pa_s']),expected.gravity)
        a=np.array(_context_key(observed));target=np.array(_context_key(expected))
        # Readback float32 conventions already used in the accepted fit adapter.
        tolerances=np.array([1e-5,*([1e-6]*6),1e-8,1e-6,1e-5,1e-9,1e-6])
        if np.any(np.abs(a-target)>tolerances):raise ValueError('fit_context_mismatch')
        return dict(accepted=True,configuration=configuration,observed_context_key=a.tolist(),
                    fit_context_key=target.tolist(),absolute_difference=np.abs(a-target).tolist(),
                    absolute_tolerances=tolerances.tolist(),actuator_tau_s=declared['dyn_time_constant'])
    except (KeyError,ValueError,TypeError,IndexError) as exc:
        raise ValueError('runtime_context:'+str(exc)) from exc
