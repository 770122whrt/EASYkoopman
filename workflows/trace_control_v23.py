"""Prepare one bounded trace request; --execute is for a separately authorized Isaac host."""
import argparse
from pathlib import Path
import json

from koopman.diagnostics_v23 import reserve_output


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--run-id', required=True)
    result.add_argument('--configuration', choices=('base', 'uuv6', 'uuv4'), default='base')
    result.add_argument('--seed', type=int, choices=(8201, 8202), default=8201)
    result.add_argument('--excitation', choices=('zero', 'constant', 'step', 'prbs'), default='constant')
    result.add_argument('--condition', choices=('cold', 'warm'), default='cold')
    result.add_argument('--trace', choices=('on', 'off'), default='on')
    result.add_argument('--reset-mode', choices=('legacy', 'episode_local_v1'), default='legacy')
    result.add_argument('--inertia-sync', choices=('legacy', 'declared_v1'), default='legacy')
    result.add_argument('--backend-readback', choices=('on', 'off'), default='off')
    result.add_argument('--initialization', choices=('legacy', 'authored_static_v1'), default='legacy')
    result.add_argument('--execute', action='store_true')
    return result


def request(args):
    return {'schema': 'phase8.3-single-case-request-v1', 'run_id': args.run_id,
            'configuration': args.configuration, 'seed': args.seed,
            'excitation': args.excitation, 'condition': args.condition,
            'trace': args.trace, 'control_history_reset_mode': args.reset_mode,
            'inertia_sync_mode': args.inertia_sync,
            'backend_readback': args.backend_readback,
            'physics_initialization_mode': args.initialization,
            'observed_intervals': 32, 'preparation_intervals': 32 if args.condition == 'warm' else 0,
            'physics_dt_s': 1 / 120, 'decimation': 2, 'control_dt_s': 1 / 60,
            'amplitude': .1, 'prbs_hold_intervals': 4,
            'evidence_level': 'exploratory_isaac_trace_only',
            'output_relative': f'tmp/phase8_3/{args.run_id}',
            'requires': ['explicit_server_start_authorization', 'clean_tested_source_bundle',
                         'loaded_runtime_binding', 'trace_on_off_gate_before_matrix']}


def actions(spec):
    import numpy as np
    result = np.zeros((32, 4), dtype=np.float32)
    if spec['excitation'] == 'constant':
        result[:] = .1
    elif spec['excitation'] == 'step':
        result[8:] = .1
    elif spec['excitation'] == 'prbs':
        rng = np.random.default_rng(spec['seed'])
        result[:] = np.repeat(rng.choice([-.1, .1], size=(8, 4)), 4, axis=0)
    if spec['configuration'] == 'uuv4':
        result[:, 2] = 0
    return result


def execute(spec):
    # Reuse only the clean-source helper; never call the old formal collector.
    from workflows.collect_koopman_v21_identification import _repository_commit
    source_commit = _repository_commit()
    from isaaclab_app import AppLauncher
    app = AppLauncher({'headless': True}).app
    env = None
    output = None
    trace = None
    report = {'request': spec, 'source_commit': source_commit, 'boundary_states': [],
              'status': 'started', 'frames': 'state: world z, wxyz, body v/omega; wrench: body; speed: internal rad/s convention'}
    try:
        import hashlib
        import inspect
        import numpy as np
        import gymnasium as gym
        import isaaclab
        import torch
        from easyuuv_nc import register_gym_tasks
        from easyuuv_nc.env.easyuuv_env import EasyUUVEnvCfg, EasyUUVEnv
        from isaaclab_compat import DirectRLEnv
        from workflows.control_trace_v23 import ControlTraceSession, _copy, _states, backend_readback
        from workflows.control_seam_v23 import mechanical_readback
        from workflows.qualify_easyuuv_v2 import detect_runtime_provenance
        register_gym_tasks()
        cfg = EasyUUVEnvCfg()
        cfg.scene.num_envs = 1
        cfg.eval_mode = True
        cfg.cap_episode_length = False
        cfg.reference_mode = 'step'
        cfg.disturbance_cfg.mode = 'none'
        cfg.noise_cfg.enable_noise = False
        cfg.domain_randomization.use_custom_randomization = False
        cfg.control_history_reset_mode = spec['control_history_reset_mode']
        cfg.inertia_sync_mode = spec['inertia_sync_mode']
        cfg.physics_initialization_mode = spec['physics_initialization_mode']
        cfg.initial_embodiment_type = spec['configuration']
        # Seed construction as well as reset; matched initial state still requires measurement.
        cfg.seed = spec['seed']
        env = gym.make('EasyUUV-Direct-v1', cfg=cfg)
        runtime = env.unwrapped
        if spec['backend_readback'] == 'on':
            report['backend_before_configuration'] = backend_readback(runtime)
        report['initial_mechanics'] = _copy(getattr(runtime, '_initial_mechanics_v23', None))
        if spec['configuration'] != 'base' and spec['physics_initialization_mode'] == 'legacy':
            runtime.apply_embodiment_config(spec['configuration'])
        if (runtime.sim.cfg.dt != spec['physics_dt_s'] or runtime.cfg.decimation != 2
                or float(runtime.step_dt) != spec['control_dt_s']):
            raise RuntimeError('trace_runtime_timing_mismatch')
        root = Path(__file__).resolve().parents[1]
        if not (root / 'tmp/phase8_3').resolve().is_relative_to(root / 'tmp'):
            raise ValueError('diagnostic_output_escape')
        output = reserve_output(root / 'tmp/phase8_3', spec['run_id'])
        report['runtime_provenance'] = detect_runtime_provenance(isaaclab.__file__)
        report['loaded_sources'] = {cls.__name__: {'path': inspect.getfile(cls),
             'sha256': hashlib.sha256(Path(inspect.getfile(cls)).read_bytes()).hexdigest()}
             for cls in (EasyUUVEnv, DirectRLEnv)}
        report['effective_cfg'] = {key: _copy(getattr(cfg, key)) for key in
            ('decimation', 'control_history_reset_mode', 'inertia_sync_mode',
             'physics_initialization_mode', 'initial_embodiment_type', 'cascade_control', 'control_method',
             's_ratio', 'self_adapt', 'attitude_error_mode', 'd_use_ang_vel', 'd_filter_tau',
             'depth_integral_gain', 'reference_mode', 'starting_depth')}
        report['topology'] = {name: _copy(getattr(runtime, name)) for name in
            ('_control_mask_4', 'thruster_com_offsets', 'thruster_quats', 'action_lim', 'PID_args')}
        report['mechanical_after_configuration'] = mechanical_readback(runtime)
        trace = ControlTraceSession(runtime, enabled=spec['trace'] == 'on',
            max_substeps=2 * (spec['observed_intervals'] + spec['preparation_intervals']),
            backend_readback_enabled=spec['backend_readback'] == 'on')
        actuator_estimate = np.zeros(runtime._num_thrusters)
        report['actuator_estimator_contract'] = {
            'initialization': 'known_zero_reset', 'truth_feedback': False,
            'input': 'ordered_clipped_pwm', 'tau_s': float(runtime.cfg.dyn_time_constant)}
        with trace:
            env.reset(seed=spec['seed'])
            report['initial_boundary'] = trace._snapshot()
            def step(action, stage, index):
                nonlocal actuator_estimate
                previous_rows = len(trace.substeps)
                result = env.step(torch.as_tensor(action, device=runtime.device).reshape(1, 4))
                if bool(torch.any(result[2])) or bool(torch.any(result[3])):
                    raise RuntimeError('trace_unexpected_auto_reset')
                state = _states(runtime)
                if not np.isfinite(state).all():
                    raise RuntimeError('trace_nonfinite_state')
                if abs(state[0][0]) > 100 or np.any(np.abs(state[0][5:]) > 100):
                    raise RuntimeError('trace_state_bound')
                snapshot = runtime.get_koopman_telemetry_snapshot()
                for field in ('virtual_control_4', 'motor_pwm_n', 'applied_wrench_6'):
                    if not bool(torch.isfinite(snapshot[field]).all()):
                        raise RuntimeError('trace_nonfinite_command')
                if bool(torch.any(snapshot['motor_pwm_n'].abs() > 1)):
                    raise RuntimeError('trace_pwm_bound')
                if spec['trace'] == 'on':
                    rows = trace.substeps[previous_rows:]
                    if len(rows) != 2:
                        raise RuntimeError('trace_call_count_mismatch')
                    for row in rows:
                        row.update(stage=stage, stage_interval=index)
                        before = row['before']['telemetry']['step_token'][0]
                        after = row['command']['telemetry']['step_token'][0]
                        if after != before + 1 or 'actuator_update' not in row:
                            raise RuntimeError('trace_token_or_actuator_capture_mismatch')
                    from workflows.validate_control_trace_v23 import validate_interval
                    validate_interval(rows, configuration=spec['configuration'])
                    from workflows.actuator_trace_v23 import annotate_estimates
                    actuator_estimate = annotate_estimates(
                        rows, actuator_estimate, tau=float(runtime.cfg.dyn_time_constant))
                report['boundary_states'].append({'stage': stage, 'interval': index, 'state_11': state,
                                                  'telemetry': _copy(snapshot)})
            if spec['condition'] == 'warm':
                dirty = actions({**spec, 'excitation': 'constant'})
                for i, action in enumerate(dirty):
                    step(action, 'dirty_preparation', i)
                env.reset(seed=spec['seed'])
                actuator_estimate = np.zeros(runtime._num_thrusters)
            report['observed_start_boundary'] = trace._snapshot()
            report['mechanical_after_observed_reset'] = mechanical_readback(runtime)
            for i, action in enumerate(actions(spec)):
                step(action, 'observed', i)
        report['status'] = 'completed_exploratory_trace'
    except Exception as exc:
        report['status'] = 'failed_exploratory_trace'
        report['exception'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if output is not None:
            from koopman.diagnostics_v23 import json_safe
            if trace is not None:
                report['substeps'] = trace.substeps
                report['events'] = trace.events
            (output / 'trace.json').write_text(json.dumps(json_safe(report), ensure_ascii=False,
                                            indent=2, allow_nan=False) + '\n', encoding='utf-8')
        try:
            if env is not None:
                env.close()
        finally:
            app.close()


def main():
    args = parser().parse_args()
    spec = request(args)
    if args.execute:
        execute(spec)
    else:
        print(json.dumps(spec, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
