"""Single-episode issue/ack ledger; the trusted simulator adapter is external.

Constructing observations does not prove a reset or physical execution occurred.
This layer validates their sequencing and values, owns causal history, and never
advances it from predictions. Isaac observation/ack provenance remains a runtime
integration obligation. An uncertain dispatch terminates this ledger.
"""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
from threading import Lock
import time
import uuid

import numpy as np

from koopman.bounded_feedback_v46 import (BoundedFeedback, FeedbackConfig,
    PreparedSteadyMap, feedback_demand)
from koopman.bounded_mpc_v44 import SupportDomain, COMMAND_ATOL, owned
from koopman.command_prediction_v37 import validate_context
from koopman.command_state_v39 import CausalCommandState
from koopman.control_objective_v44 import checked_reference
from koopman.physical_terms_v26 import validate_states
from koopman.prepared_projected_v40 import _context_key


def _label(value):
    if not isinstance(value, str) or not value.strip():raise ValueError('execution_identity')
    return value


@dataclass(frozen=True)
class BoundaryObservation:
    episode_id: str
    reset_id: str
    physics_index: int
    state: np.ndarray

    def __post_init__(self):
        _label(self.episode_id); _label(self.reset_id)
        if type(self.physics_index) is not int or self.physics_index < 0:
            raise ValueError('observation_index')
        x = np.asarray(self.state, dtype=float)
        if x.shape != (11,):raise ValueError('observation_state')
        validate_states(x[None])
        object.__setattr__(self, 'state', owned(x))


@dataclass(frozen=True)
class ResetObservation(BoundaryObservation):
    rotor_speed: np.ndarray

    def __post_init__(self):
        super().__post_init__()
        speed = np.asarray(self.rotor_speed, dtype=float)
        if (self.physics_index != 0 or speed.ndim != 1 or not np.isfinite(speed).all()
                or speed.size == 0 or np.max(np.abs(speed)) > 1e-8
                or abs(self.state[0]-5.5) > 1e-6 or np.max(np.abs(self.state[5:])) > 1e-6
                or np.linalg.norm(self.state[2:5]) > 1e-6):
            raise ValueError('verified_zero_reset_observation_required')
        object.__setattr__(self, 'rotor_speed', owned(speed))


@dataclass(frozen=True)
class ExecutionCapture:
    execution_id: str
    episode_id: str
    reset_id: str
    physics_index: int
    history_digest: str
    worker_generation: int
    reference_id: str
    reference_revision: int
    configuration: str
    context_key: tuple
    model_id: str
    support_id: str
    created_perf_counter_s: float
    state: np.ndarray
    reference: np.ndarray
    previous: object
    origin: object


class ExecutionLedger:
    """One outstanding command, confirmed twice at 120Hz for a 60Hz hold.

    The local controller owns this object; optimizer workers receive copies of
    captures, never the live ledger. All mutations try a lock without waiting.
    No reset, retry-after-ambiguity, or trial-commit operation is provided.
    """
    def __init__(self, domain, context, reset, *, reference, reference_id,
                 startup_command, feedback_config=FeedbackConfig(), history_limit=256,
                 allow_diagnostic=False):
        if not isinstance(domain, SupportDomain) or (not domain._verified_fit and not allow_diagnostic):
            raise ValueError('execution_fit_provenance_required')
        validate_context(domain.configuration, context)
        if (not isinstance(reset, ResetObservation) or _context_key(context) != domain.context_key
                or not isinstance(feedback_config, FeedbackConfig)
                or type(history_limit) is not int or not 1 <= history_limit <= 512):
            raise ValueError('execution_setup')
        self._domain, self._context = domain, replace(context)
        self._config = feedback_config
        self._steady = PreparedSteadyMap(domain.configuration, self._context)
        if reset.rotor_speed.shape != (self._steady.allocator.wrench_matrix.shape[1],):
            raise ValueError('reset_rotor_count')
        if domain.check_states(reset.state[None]):raise ValueError('reset_out_of_support')
        self._reference = owned(checked_reference(reference)); self._reference_id = _label(reference_id)
        self._startup_target = owned(feedback_demand(reset.state, self._reference,
            domain.configuration, self._context, feedback_config)['target_wrench'])
        self._startup = self._checked_command(startup_command, None, target=self._startup_target)
        self._reset = reset
        self._initial_reference_id = self._reference_id; self._initial_reference = self._reference
        self._binding = (domain.configuration, domain.context_key, domain.model_id, domain.identity)
        self._execution_id = uuid.uuid4().hex
        self._live = CausalCommandState(domain.configuration, self._context,
            episode_id=reset.episode_id, zero_rotor_reset_verified=True)
        self._history = deque(maxlen=history_limit)
        self._digest = hashlib.sha256(json.dumps(dict(execution_id=self._execution_id,
            episode=reset.episode_id, reset=reset.reset_id, binding=self._binding), sort_keys=True).encode()).hexdigest()
        self._previous = None; self._capture = None; self._pending = None
        self._startup_consumed = False; self._stop_reason = None
        self._reference_revision = 0; self._worker_generation = 0
        self._lock = Lock()

    @contextmanager
    def _guard(self, *, running=True):
        if not self._lock.acquire(blocking=False):raise RuntimeError('execution_busy')
        try:
            if running and self._stop_reason is not None:raise ValueError('execution_stopped:'+self._stop_reason)
            yield
        finally:self._lock.release()

    @property
    def physics_index(self):
        with self._guard(running=False):return self._live.physics_index

    @property
    def startup_consumed(self):
        with self._guard(running=False):return self._startup_consumed

    @property
    def pending(self):
        with self._guard(running=False):return self._pending is not None

    @property
    def stopped(self):
        with self._guard(running=False):return self._stop_reason is not None

    @property
    def stop_reason(self):
        with self._guard(running=False):return self._stop_reason

    def _binding_check(self):
        d = self._domain
        if (self._binding != (d.configuration, d.context_key, d.model_id, d.identity)
                or _context_key(self._context) != d.context_key
                or self._steady.configuration != d.configuration or self._steady.context_key != d.context_key):
            raise ValueError('execution_binding_changed')

    def _checked_command(self, value, previous, *, target=None):
        u = np.asarray(value, dtype=float)
        if u.shape != (4,) or not np.isfinite(u).all() or np.any(np.abs(u) > .95):
            raise ValueError('execution_command_invalid')
        u = np.asarray(u, dtype=np.float32)
        lo, hi = self._domain.command_lower, self._domain.command_upper
        if previous is not None:
            lo = np.maximum(lo, previous-self._config.slew)
            hi = np.minimum(hi, previous+self._config.slew)
        record = self._steady.inspect(u, np.zeros(6) if target is None else target, lo, hi)
        if not record['command_constraints_accepted'] or (target is not None and not record['physical_residual_accepted']):
            raise ValueError('execution_command_constraints_or_startup_residual')
        return owned(u, np.float32)

    def capture(self, observation, reference, *, reference_id):
        with self._guard():
            self._binding_check()
            index = self._live.physics_index
            if self._pending is not None or index % 2:raise ValueError('execution_pending_or_half_boundary')
            if (not isinstance(observation, BoundaryObservation) or observation.physics_index != index
                    or observation.episode_id != self._reset.episode_id or observation.reset_id != self._reset.reset_id):
                raise ValueError('execution_observation_binding')
            if self._domain.check_states(observation.state[None]):raise ValueError('execution_state_out_of_support')
            ref = checked_reference(reference); _label(reference_id)
            if index == 0 and (reference_id != self._initial_reference_id
                    or not BoundedFeedback._same_pose_values(ref, self._initial_reference, 1e-12)
                    or not BoundedFeedback._same_pose_values(observation.state, self._reset.state, 1e-6)):
                raise ValueError('startup_reference_or_reset_changed')
            if reference_id == self._reference_id:
                if not BoundedFeedback._same_pose_values(ref, self._reference, 1e-12):
                    raise ValueError('reference_changed_without_new_identity')
            else:
                self._reference_id = reference_id; self._reference = owned(ref)
                self._reference_revision += 1
            origin = self._live.snapshot(configuration=self._domain.configuration,
                context=self._context, origin_control=index//2, episode_id=self._reset.episode_id)
            value = ExecutionCapture(self._execution_id, self._reset.episode_id, self._reset.reset_id,
                index, self._digest, self._worker_generation, reference_id, self._reference_revision,
                *self._binding, time.perf_counter(), owned(observation.state), owned(ref),
                None if self._previous is None else owned(self._previous, np.float32), origin)
            self._capture = value
            return value

    def reserve(self, capture, command, *, source, startup=False):
        with self._guard():
            self._binding_check()
            if self._pending is not None:raise ValueError('execution_pending')
            if (capture is not self._capture or capture is None
                    or capture.physics_index != self._live.physics_index
                    or capture.history_digest != self._digest or capture.worker_generation != self._worker_generation):
                raise ValueError('execution_capture_stale')
            if source not in ('fallback', 'mpc', 'committed_prefix') or type(startup) is not bool:
                raise ValueError('execution_command_source')
            is_first = self._live.physics_index == 0
            if startup != is_first or (startup and (self._startup_consumed or source != 'fallback')):
                raise ValueError('startup_permission_not_available')
            u = self._checked_command(command, self._previous, target=self._startup_target if startup else None)
            if startup and not np.allclose(u, self._startup, rtol=0, atol=COMMAND_ATOL):
                raise ValueError('startup_command_binding')
            token = uuid.uuid4().hex
            self._pending = dict(ticket=token, command=u, source=source, startup=startup,
                physics_index=self._live.physics_index, dispatched=False, acknowledged=0, actual=None,
                reference_id=capture.reference_id, history_digest=capture.history_digest)
            self._capture = None
            return token

    def dispatch(self, ticket):
        with self._guard():
            p = self._pending
            if p is None or ticket != p['ticket'] or p['dispatched']:
                self._stop_reason = 'dispatch_duplicate_or_unknown'
                raise ValueError(self._stop_reason)
            self._binding_check()
            p['dispatched'] = True
            return dict(ticket=ticket, execution_id=self._execution_id, episode_id=self._reset.episode_id,
                reset_id=self._reset.reset_id, physics_index=p['physics_index'], command=owned(p['command'], np.float32),
                startup_exception=p['startup'], source=p['source'], actual_execution_confirmed=False,
                runtime_qualification='adapter_and_closed_loop_still_required')

    def acknowledge(self, ticket, actual_command, *, physics_index, episode_id, reset_id):
        with self._guard():
            try:
                self._binding_check(); p = self._pending
                if (p is None or not p['dispatched'] or ticket != p['ticket']
                        or episode_id != self._reset.episode_id or reset_id != self._reset.reset_id
                        or type(physics_index) is not int or physics_index != self._live.physics_index
                        or physics_index != p['physics_index']+p['acknowledged']):
                    raise ValueError('acknowledgment_binding_or_sequence')
                actual = self._checked_command(actual_command, self._previous,
                    target=self._startup_target if p['startup'] else None)
                if not np.allclose(actual, p['command'], rtol=0, atol=COMMAND_ATOL):
                    raise ValueError('acknowledgment_command_mismatch')
                if p['acknowledged'] and not np.array_equal(actual, p['actual']):
                    raise ValueError('acknowledgment_two_substep_hold_mismatch')
                following_digest = hashlib.sha256(bytes.fromhex(self._digest)
                    + physics_index.to_bytes(8, 'little')+actual.tobytes()).hexdigest()
                # This is the sole live recurrence write. Everything above is validated first.
                self._live.record_issued(actual.copy(), physics_index=physics_index, episode_id=episode_id)
                self._digest = following_digest; p['acknowledged'] += 1
                if p['acknowledged'] == 1:
                    p['actual'] = actual
                    if p['startup']:self._startup_consumed = True
                else:
                    self._previous = actual
                    self._history.append((p['physics_index']//2, actual))
                    self._pending = None
                return dict(physics_index=self._live.physics_index, history_digest=self._digest,
                    interval_complete=self._pending is None, startup_consumed=self._startup_consumed)
            except Exception as exc:
                self._stop_reason = 'execution_ack_failed:'+str(exc)
                raise

    def acknowledged_commands(self, start_control, end_control):
        with self._guard(running=False):
            if (type(start_control) is not int or type(end_control) is not int
                    or start_control < 0 or end_control < start_control or end_control > self._live.physics_index//2):
                raise ValueError('execution_history_range')
            selected = [u for i,u in self._history if start_control <= i < end_control]
            if len(selected) != end_control-start_control:raise ValueError('execution_history_expired')
            return np.array(selected, dtype=np.float32).reshape(-1,4)

    def restart_worker_generation(self):
        with self._guard():
            self._worker_generation += 1
            self._capture = None
            return self._worker_generation

    def abort(self, reason):
        with self._guard(running=False):
            if self._stop_reason is None:self._stop_reason = _label(reason)
            self._capture = None
