"""Execution wiring and mechanical admission, no Isaac physics claims."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest

from test_prepared_projected_v40 import context
from easyuuv_nc.embodiments import EMBODIMENT_CONFIGS, qualification_record


NAMES = ('base','long_body','heavy_moderate','asymmetric','uuv6','uuv6_angled','uuv4','uuv4_angled')


def snapshot(name='base'):
    c=context(name); q=qualification_record(name); e=EMBODIMENT_CONFIGS[name]
    return dict(telemetry=dict(configuration=name, mass_kg=[[c.mass]], inertia_diagonal_kg_m2=[c.inertia.tolist()],
        com_to_cob_offset_m=[c.cob.tolist()],volume_m3=[[c.volume]],drag_multiplier=[[c.drag_multiplier]],
        water_density_kg_m3=c.rho,dynamic_viscosity_pa_s=c.beta,
        thruster_dynamics_time_constant_s=[[e['dyn_time_constant']]*q['thruster_count']],
        control_mask_4=[list(q['control_mask'])]), backend=dict(mass_kg=[[c.mass]],
        inverse_mass_per_kg=[[float(np.float32(1)/np.float32(c.mass))]],
        inertia_9=[np.diag(c.inertia).reshape(-1).tolist()],gravity_world_m_s2=[0,0,-c.gravity],gravity_disabled=[[0]]))


@pytest.mark.parametrize('name',NAMES)
def test_catalog_context_must_match_actual_backend_and_declared_fields(name):
    from workflows.runtime_episode_v57 import check_runtime_context
    got=check_runtime_context(snapshot(name),name,context(name))
    assert got['accepted'] and got['configuration']==name


@pytest.mark.parametrize('bad',['physx_mass','declared_mass','inertia','off_diagonal','gravity','disabled',
                                'cob','volume','drag','rho','beta','tau','mask','configuration','nan'])
def test_mismatched_mechanics_cannot_reuse_a_fit_context(bad):
    from workflows.runtime_episode_v57 import check_runtime_context
    s=snapshot();t=s['telemetry'];b=s['backend']
    if bad=='physx_mass':b['mass_kg'][0][0]+=1
    if bad=='declared_mass':t['mass_kg'][0][0]+=1
    if bad=='inertia':b['inertia_9'][0][0]+=.01
    if bad=='off_diagonal':b['inertia_9'][0][1]=.01
    if bad=='gravity':b['gravity_world_m_s2'][0]=1
    if bad=='disabled':b['gravity_disabled'][0][0]=1
    if bad=='cob':t['com_to_cob_offset_m'][0][0]+=.01
    if bad=='volume':t['volume_m3'][0][0]+=.001
    if bad=='drag':t['drag_multiplier'][0][0]+=1
    if bad=='rho':t['water_density_kg_m3']+=1
    if bad=='beta':t['dynamic_viscosity_pa_s']+=.01
    if bad=='tau':t['thruster_dynamics_time_constant_s'][0][0]+=.01
    if bad=='mask':t['control_mask_4'][0][0]=0
    if bad=='configuration':t['configuration']='long_body'
    if bad=='nan':b['mass_kg'][0][0]=float('nan')
    with pytest.raises(ValueError,match='runtime_context'):
        check_runtime_context(s,'base',context('base'))


def test_runtime_configuration_sets_required_modes_before_environment_construction():
    from workflows.runtime_episode_v57 import configure_environment
    cfg=SimpleNamespace(scene=SimpleNamespace(),disturbance_cfg=SimpleNamespace(),
        noise_cfg=SimpleNamespace(),domain_randomization=SimpleNamespace())
    configure_environment(cfg,'uuv6',19001)
    assert cfg.scene.num_envs==1 and cfg.control_input_mode=='direct_pre_tam_v24'
    assert cfg.physics_initialization_mode=='authored_static_v1'
    assert cfg.control_history_reset_mode=='episode_local_v1' and cfg.inertia_sync_mode=='declared_v1'
    assert cfg.starting_depth==5.5 and cfg.ground_plane_mode=='grid'
    assert cfg.seed==19001 and cfg.initial_embodiment_type=='uuv6'


class Clock:
    def __init__(self):self.now=0.
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class Session:
    def __init__(self,clock,*,cost=.003,failure_at=None):
        self.clock=clock;self.cost=cost;self.failure_at=failure_at;self.calls=0
        self.runtime=SimpleNamespace(ledger=SimpleNamespace(physics_index=0),stats={'mpc_activations':1})
        self.stopped=None;self.runtime._stop=self.stop;self.interval_records=[]
    def stop(self,reason):self.stopped=reason
    def run_interval(self,step,reference,*,reference_id):
        self.calls+=1;self.clock.now+=self.cost
        if self.calls==self.failure_at:
            self.runtime.ledger.physics_index+=1
            raise RuntimeError('known_half_interval_failure')
        self.runtime.ledger.physics_index+=2
        result=dict(status='completed_interval',whole_cycle_wall_ms=self.cost*1000)
        self.interval_records.append(result);return result


def test_fixed_cycle_pacing_and_requested_count_are_not_changed():
    from workflows.runtime_episode_v57 import run_intervals
    clock=Clock();s=Session(clock)
    got=run_intervals(s,lambda _:None,[5.5,1,0,0,0],reference_id='ref',controls=4,clock=clock,sleep=clock.sleep)
    assert s.calls==4 and s.runtime.ledger.physics_index==8 and got['completed_controls']==4
    assert clock.now==pytest.approx(4/60)
    assert got['maximum_cycle_ms']==pytest.approx(3.)


def test_full_cycle_overrun_stops_before_next_command_and_keeps_executed_receipts():
    from workflows.runtime_episode_v57 import run_intervals
    clock=Clock();s=Session(clock,cost=.018)
    with pytest.raises(ValueError,match='full_cycle_deadline'):
        run_intervals(s,lambda _:None,[5.5,1,0,0,0],reference_id='ref',controls=4,clock=clock,sleep=clock.sleep)
    assert s.calls==1 and s.runtime.ledger.physics_index==2
    assert s.stopped and s.interval_records[0]['external_cycle_wall_ms']==pytest.approx(18.)


def test_half_interval_exception_is_not_swallowed_or_retried():
    from workflows.runtime_episode_v57 import run_intervals
    clock=Clock();s=Session(clock,failure_at=2)
    with pytest.raises(RuntimeError,match='known_half_interval_failure'):
        run_intervals(s,lambda _:None,[5.5,1,0,0,0],reference_id='ref',controls=4,clock=clock,sleep=clock.sleep)
    assert s.calls==2 and s.runtime.ledger.physics_index==3 and s.stopped


def test_long_scheduler_delay_stops_instead_of_bursting_catchup_commands():
    from workflows.runtime_episode_v57 import run_intervals
    clock=Clock();s=Session(clock)
    def oversleep(seconds):clock.now+=seconds+.02
    with pytest.raises(ValueError,match='schedule_overrun'):
        run_intervals(s,lambda _:None,[5.5,1,0,0,0],reference_id='ref',controls=4,clock=clock,sleep=oversleep)
    assert s.calls==1 and s.runtime.ledger.physics_index==2


def test_zero_mpc_activations_cannot_pass_controller_integration_gate():
    from workflows.runtime_episode_v57 import run_intervals
    clock=Clock();s=Session(clock);s.runtime.stats['mpc_activations']=0
    with pytest.raises(ValueError,match='no_mpc_activation'):
        run_intervals(s,lambda _:None,[5.5,1,0,0,0],reference_id='ref',controls=4,clock=clock,sleep=clock.sleep)
    assert s.calls==4 and s.runtime.ledger.physics_index==8
