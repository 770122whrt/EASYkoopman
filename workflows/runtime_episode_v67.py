"""Separate one bounded startup from steady timing; explicit effects mode.

Effects mode advances identical physics intervals without claiming wall-clock
realtime. The arbiter uses acknowledged simulated time, while the actual worker
and control computations retain their original wall-clock rejection limits.
"""
import time
import numpy as np


def configure_environment(cfg, configuration, seed):
    from workflows.runtime_episode_v59 import configure_environment as original
    original(cfg, configuration, seed)
    cfg.decimation = 4
    cfg.control_rate_hz_v67 = 30
    cfg.sim.render_interval = 4


def bind_runtime(session, assets, configuration, reference, *, reference_id, worker=None):
    from workflows.runtime_episode_v59 import check_runtime_context
    from koopman.inexact_tracking_v66 import InexactTrackingFeedback
    from koopman.rate30_v67 import ExecutionLedger, RuntimeCoordinator, FEEDBACK_CONFIG
    from workflows.runtime_audit_v67 import RecordingArbiter
    if worker is not None and worker.state != 'ready':
        raise ValueError('runtime_worker_not_ready')
    domain = assets.domains[configuration]
    context = assets.context(configuration)
    reset = session.reset_observation()
    context_audit = check_runtime_context(session.reset_record['snapshot'], configuration, context)
    policy = InexactTrackingFeedback(domain, context, config=FEEDBACK_CONFIG)
    seed = policy.prepare_startup(reset.state, reference)
    if seed['status'] != 'prepared':
        raise ValueError('runtime_startup:'+str(seed['reason']))
    ledger = ExecutionLedger(domain, context, reset, reference=reference, reference_id=reference_id,
        startup_command=seed['command'], feedback_config=FEEDBACK_CONFIG, steady=policy.steady)
    coordinator = RuntimeCoordinator(ledger, policy, worker)
    coordinator.arbiter = RecordingArbiter(ledger, config=coordinator.arbiter.config, clock=coordinator.clock)
    policy.physics_index = lambda: ledger.physics_index
    session.bind(coordinator)
    return dict(context_audit=context_audit, startup=seed, model_id=domain.model_id,
        support_id=domain.identity, execution_id=ledger._execution_id,
        control_rate_hz=30, physics_rate_hz=120, forecast_rate_hz=60,
        hold_physics_steps=4, feedback_slew=FEEDBACK_CONFIG.slew)


class BoundaryWorker:
    """Wait outside physics/control, release a reply at the next boundary only.

    Keep the worker's real elapsed_ms and failures unchanged. The committed
    eight-interval prefix still prevents this reply from acting prematurely.
    """
    def __init__(self, worker):
        self.worker = worker
        self._submitted = False
        self._event = None
        self.wait_seconds = 0.

    @property
    def generation(self): return self.worker.generation

    @property
    def state(self): return self.worker.state

    def submit(self, request_id, request):
        if self._submitted or self._event is not None:
            raise ValueError('boundary_worker_pending')
        receipt = self.worker.submit(request_id, request)
        self._submitted = receipt.get('status') == 'accepted'
        return receipt

    def poll(self):
        event, self._event = self._event, None
        return event

    def finish_boundary(self):
        if not self._submitted: return
        start = time.perf_counter()
        while self._event is None:
            self._event = self.worker.poll()
            if self._event is not None: break
            if time.perf_counter()-start > .12:
                raise TimeoutError('boundary_worker_missing_timeout')
            time.sleep(.0005)
        self.wait_seconds += time.perf_counter()-start
        self._submitted = False

    def close(self, **kwargs): return self.worker.close(**kwargs)


def bind_effect_clock(session):
    """Only admission ages use acknowledged physics time; safety stays live."""
    from workflows.runtime_audit_v67 import RecordingArbiter
    runtime = session.runtime
    if runtime.ledger.physics_index != 0 or runtime.stats['dispatches']:
        raise ValueError('effect_clock_requires_fresh_reset')
    runtime.arbiter = RecordingArbiter(runtime.ledger,
        config=runtime.arbiter.config, clock=lambda: runtime.ledger.physics_index/120)


def run_intervals(session, env_step, reference, *, reference_id, controls,
                  mode='startup_then_realtime', require_mpc=True,
                  clock=time.perf_counter, sleep=time.sleep):
    if type(controls) is not int or not 2 <= controls <= 128:
        raise ValueError('runtime_controls')
    if mode not in ('startup_then_realtime', 'simulation_effect'):
        raise ValueError('runtime_mode')
    if type(require_mpc) is not bool: raise ValueError('runtime_require_mpc')
    period = 1/30
    origin = None
    started = clock()
    elapsed_rows = []
    lateness_rows = []
    misses = 0
    try:
        for i in range(controls):
            start = clock()
            due = start if i == 0 or mode == 'simulation_effect' else origin+(i-1)*period
            late = start-due
            if not np.isfinite(late) or late < 0 or late >= period:
                raise ValueError('runtime_schedule_overrun')
            row = session.run_interval(env_step, reference, reference_id=reference_id)
            end = clock(); elapsed = end-start
            row.update(external_cycle_wall_ms=1000*elapsed,
                       scheduled_start_lateness_ms=1000*late,
                       timing_phase='startup' if i == 0 else 'steady', timing_mode=mode)
            elapsed_rows.append(1000*elapsed); lateness_rows.append(1000*late)
            if not np.isfinite(elapsed) or elapsed < 0:
                raise ValueError('runtime_clock')
            if row['status'] != 'completed_interval' or session.runtime.ledger.physics_index != 4*(i+1):
                raise ValueError('runtime_incomplete_receipts')
            if i == 0:
                if elapsed > .1: raise ValueError('runtime_startup_deadline')
                origin = end  # Exactly once; state/history are never reset.
            else:
                miss = end > due+period
                misses += int(miss)
                row['wall_deadline_missed'] = bool(miss)
                if mode == 'startup_then_realtime' and miss:
                    raise ValueError('runtime_steady_deadline')
                if elapsed > 1.: raise ValueError('runtime_diagnostic_cycle_limit')
            if mode == 'simulation_effect':
                worker = getattr(session.runtime, 'worker', None)
                if worker is not None:
                    if not isinstance(worker, BoundaryWorker):
                        raise ValueError('simulation_requires_boundary_worker')
                    worker.finish_boundary()
            elif i:
                remaining = origin+i*period-clock()
                if remaining > 0: sleep(remaining)
        if require_mpc and session.runtime.stats['mpc_activations'] < 1:
            raise ValueError('runtime_no_mpc_activation')
        return dict(completed_controls=controls, startup_ms=elapsed_rows[0],
                    steady_max_ms=max(elapsed_rows[1:]), maximum_cycle_ms=max(elapsed_rows),
                    steady_p50_ms=float(np.median(elapsed_rows[1:])),
                    steady_p95_ms=float(np.percentile(elapsed_rows[1:], 95)),
                    steady_deadline_misses=misses,
                    maximum_start_lateness_ms=max(lateness_rows),
                    seconds=clock()-started, simulated_seconds=controls/30,
                    timing_mode=mode, runtime_qualified=False,
                    gate='bounded_effects_pilot' if mode == 'simulation_effect'
                    else 'bounded_startup_and_steady_interface_only')
    except BaseException as exc:
        session.runtime._stop('episode:'+str(exc))
        raise
