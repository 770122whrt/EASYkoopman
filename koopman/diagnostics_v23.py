"""Additive local forensic tools; never a model-selection entry point."""

from pathlib import Path
import re

import numpy as np

from koopman.metrics_v21 import OFFICIAL_ROLLOUT_POLICY_V21, rollout_episode_v21
from koopman.so3_v21 import apply_increment_target_v21


class SourceOnlyReader:
    """Check exact predeclared bindings before delegating any dataset access."""

    def __init__(self, backend, bindings):
        self.backend = backend
        self.allowed = {item.episode_id: item for item in bindings}
        if any(item.configuration == 'base' or item.role not in {'fit', 'validation'}
               for item in bindings):
            raise ValueError('source_access_denied')
        self.opened = []

    def open_episode(self, binding):
        if (binding.configuration == 'base' or binding.role not in {'fit', 'validation'}
                or self.allowed.get(binding.episode_id) != binding):
            raise ValueError('source_access_denied')
        if hasattr(self.backend, 'dataset_root'):
            root = Path(self.backend.dataset_root).resolve()
            for relative in (binding.transition_path, binding.manifest_path):
                path = root / relative
                if (not path.resolve().is_relative_to(root)
                        or path.resolve() != path.absolute()):
                    raise ValueError('source_access_denied:redirected_path')
        result = self.backend.open_episode(binding)
        self.opened.append(binding)
        return result


def reserve_output(root, run_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}', run_id):
        raise ValueError('diagnostic_run_id_invalid')
    root = Path(root).resolve()
    target = root / run_id
    if not target.resolve().is_relative_to(root):
        raise ValueError('diagnostic_output_escape')
    target.mkdir(parents=True, exist_ok=False)
    return target


class _RecordingModel:
    def __init__(self, model):
        self.model = model
        self.last = None

    def predict_increment(self, state, memory, control, *, platform_score=None):
        self.last = {'state_11': np.array(state, copy=True),
                     'memory_4': np.array(memory, copy=True),
                     'control_4': np.array(control, copy=True)}
        try:
            result = self.model.predict_increment(state, memory, control,
                                                  platform_score=platform_score)
        except Exception as exc:
            self.last['exception'] = f'{type(exc).__name__}: {exc}'
            raise
        self.last['increment_10'] = np.array(result, copy=True)
        return result


def json_safe(value):
    """Keep nonfinite diagnostics explicit without emitting invalid JSON."""
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def diagnose_window(model, episode, *, start, steps, platform_score=None):
    """Use the production rollout once; inspect its last call after it returns."""
    recorder = _RecordingModel(model)
    trace = rollout_episode_v21(recorder, episode, start=start, steps=steps,
                               policy=OFFICIAL_ROLLOUT_POLICY_V21,
                               platform_score=platform_score)
    last = recorder.last
    if last is not None and 'increment_10' in last:
        try:
            # Pure post-hoc reconstruction, never fed back into the rollout.
            last['proposed_state_11'] = apply_increment_target_v21(
                last['state_11'], last['increment_10'])
        except Exception as exc:
            last['reconstruction_exception'] = f'{type(exc).__name__}: {exc}'
    attempted = trace.attempted_transition_count
    return json_safe({
        'episode_id': episode.episode_id, 'configuration': episode.configuration,
        'start': start, 'steps': steps, 'status': trace.status,
        'reason_code': trace.reason_code,
        'attempted_transition_count': attempted,
        'completed_transition_count': trace.completed_transition_count,
        'failure_transition_index': start + attempted - 1 if trace.status == 'failed' else None,
        'last_prediction': last,
    })
