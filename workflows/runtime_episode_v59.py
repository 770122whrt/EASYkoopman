"""Actual episode wiring; source/approval admission stays in the collector.

The complete cycle includes readback, arbitration, simulator step and substep
checks. Its deadline is distinct from the solver's 100ms rejection deadline.
No timing result here proves a hard real-time guarantee beyond measured runs.
"""
import time
import numpy as np

from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, qualification_record
from koopman.prepared_projected_v40 import _context_key
from koopman.projected_edmd_v24 import PhysicalContext


def configure_environment(cfg, configuration, seed):
    if configuration not in EMBODIMENT_CONFIGS or type(seed) is not int:
        raise ValueError('runtime_environment_request')
    cfg.scene.num_envs=1;cfg.eval_mode=True;cfg.cap_episode_length=False;cfg.reference_mode='step'
    cfg.disturbance_cfg.mode='none';cfg.noise_cfg.enable_noise=False
    cfg.domain_randomization.use_custom_randomization=False
    cfg.control_history_reset_mode='episode_local_v1';cfg.inertia_sync_mode='declared_v1'
    cfg.physics_initialization_mode='authored_static_v1';cfg.initial_embodiment_type=configuration
    cfg.control_input_mode='direct_pre_tam_v24';cfg.seed=seed;cfg.starting_depth=5.5;cfg.ground_plane_mode='grid'


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


def bind_runtime(session, assets, configuration, reference, *, reference_id, worker=None):
    """Build causal history from this actual reset, never from a fit initial row."""
    from koopman.cached_checks_v53 import CachedExecutionLedger,CachedTrackingFeedback
    from koopman.plan_continuity_v54 import RuntimeCoordinator
    if worker is not None and worker.state!='ready':raise ValueError('runtime_worker_not_ready')
    domain=assets.domains[configuration];context=assets.context(configuration)
    reset=session.reset_observation()
    context_audit=check_runtime_context(session.reset_record['snapshot'],configuration,context)
    policy=CachedTrackingFeedback(domain,context)
    seed=policy.prepare_startup(reset.state,reference)
    if seed['status']!='prepared':raise ValueError('runtime_startup:'+str(seed['reason']))
    ledger=CachedExecutionLedger(domain,context,reset,reference=reference,reference_id=reference_id,
                                 startup_command=seed['command'],steady=policy.steady)
    coordinator=RuntimeCoordinator(ledger,policy,worker)
    from workflows.runtime_audit_v57 import RecordingArbiter
    coordinator.arbiter=RecordingArbiter(ledger,config=coordinator.arbiter.config,clock=coordinator.clock)
    session.bind(coordinator)
    return dict(context_audit=context_audit,startup=seed,model_id=domain.model_id,
                support_id=domain.identity,execution_id=ledger._execution_id)


def run_intervals(session,env_step,reference,*,reference_id,controls,clock=time.perf_counter,sleep=time.sleep):
    if type(controls) is not int or not 1<=controls<=1024:raise ValueError('runtime_controls')
    period=1/60;origin=clock();maximum=0.;lateness_max=0.
    try:
        for i in range(controls):
            due=origin+i*period;start=clock();late=start-due
            if not np.isfinite(late) or late<0 or late>=period:raise ValueError('runtime_schedule_overrun')
            row=session.run_interval(env_step,reference,reference_id=reference_id)
            end=clock();elapsed=end-start
            row['external_cycle_wall_ms']=1000*elapsed;row['scheduled_start_lateness_ms']=1000*late
            maximum=max(maximum,1000*elapsed);lateness_max=max(lateness_max,1000*late)
            if not np.isfinite(elapsed) or elapsed<0 or end>due+period:
                raise ValueError('runtime_full_cycle_deadline')
            if row['status']!='completed_interval' or session.runtime.ledger.physics_index!=2*(i+1):
                raise ValueError('runtime_incomplete_receipts')
            # Fixed pacing; never issue a burst to catch up after a missed slot.
            remaining=due+period-clock()
            if remaining>0:sleep(remaining)
        if session.runtime.stats['mpc_activations']<1:raise ValueError('runtime_no_mpc_activation')
        return dict(completed_controls=controls,maximum_cycle_ms=maximum,
                    maximum_start_lateness_ms=lateness_max,seconds=clock()-origin,
                    simulated_seconds=controls/60,gate='bounded_interface_cycle_only_not_control_benefit')
    except BaseException as exc:
        session.runtime._stop('episode:'+str(exc))
        raise
