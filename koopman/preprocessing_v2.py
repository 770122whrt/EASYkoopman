"""Non-mutating quaternion sign preprocessing for Phase 8 model fitting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from koopman.evidence_v2 import canonical_sha256


QUATERNION_PREPROCESSOR_VERSION_V2 = "phase8-quaternion-sign-preprocessor-v1"
STATE_DIM_V2 = 11
QUATERNION_SLICE_V2 = slice(1, 5)


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if detail is None else f"{reason}:{detail}")


def _readonly_matrix(value: Any, *, name: str) -> np.ndarray:
    array = np.array(value, dtype=np.float64, copy=True)
    if array.ndim != 2 or array.shape[1] != STATE_DIM_V2 or array.shape[0] == 0:
        _fail("preprocessing_shape_invalid", name)
    if not np.isfinite(array).all():
        _fail("preprocessing_nonfinite", name)
    quaternion_norms = np.linalg.norm(array[:, QUATERNION_SLICE_V2], axis=1)
    if np.any(quaternion_norms <= 0.0):
        _fail("preprocessing_quaternion_invalid", name)
    array.setflags(write=False)
    return array


def _first_quaternion_sign(quaternion: np.ndarray) -> float:
    for value in quaternion:
        if value > 0.0:
            return 1.0
        if value < 0.0:
            return -1.0
    _fail("preprocessing_quaternion_invalid", "first_quaternion")


@dataclass(frozen=True)
class QuaternionPreprocessedEpisodeV2:
    episode_id: str
    states: np.ndarray
    targets: np.ndarray
    source_sha256: str
    sign_flip_count: int
    version: str = QUATERNION_PREPROCESSOR_VERSION_V2
    preprocessor_sha256: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.episode_id, str) or not self.episode_id:
            _fail("preprocessing_episode_id_invalid")
        if self.version != QUATERNION_PREPROCESSOR_VERSION_V2:
            _fail("preprocessing_version_unsupported")
        states = _readonly_matrix(self.states, name="states")
        targets = _readonly_matrix(self.targets, name="targets")
        if states.shape != targets.shape:
            _fail("preprocessing_shape_invalid", "row_count")
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "targets", targets)
        payload = {
            "episode_id": self.episode_id,
            "source_sha256": self.source_sha256,
            "sign_flip_count": int(self.sign_flip_count),
            "states": states.tolist(),
            "targets": targets.tolist(),
            "version": self.version,
        }
        expected = canonical_sha256(payload)
        if self.preprocessor_sha256 and self.preprocessor_sha256 != expected:
            _fail("preprocessing_hash_mismatch")
        object.__setattr__(self, "preprocessor_sha256", expected)


def preprocess_quaternion_episode_v2(
    states: Any,
    targets: Any,
    *,
    episode_id: str,
) -> QuaternionPreprocessedEpisodeV2:
    """Align equivalent quaternion signs without changing source arrays.

    The first state uses a deterministic first-nonzero-positive convention. Later
    states align with their predecessor. Each transition target aligns with the
    next aligned state when present, and with the current state for the final row.
    """

    raw_states = np.array(states, dtype=np.float64, copy=True)
    raw_targets = np.array(targets, dtype=np.float64, copy=True)
    if (
        raw_states.ndim != 2
        or raw_targets.ndim != 2
        or raw_states.shape[1:] != (STATE_DIM_V2,)
        or raw_targets.shape[1:] != (STATE_DIM_V2,)
        or raw_states.shape[0] == 0
        or raw_states.shape != raw_targets.shape
    ):
        _fail("preprocessing_shape_invalid")
    if not np.isfinite(raw_states).all() or not np.isfinite(raw_targets).all():
        _fail("preprocessing_nonfinite")
    for name, array in (("states", raw_states), ("targets", raw_targets)):
        if np.any(np.linalg.norm(array[:, QUATERNION_SLICE_V2], axis=1) <= 0.0):
            _fail("preprocessing_quaternion_invalid", name)

    source_sha256 = canonical_sha256(
        {
            "episode_id": episode_id,
            "states": raw_states.tolist(),
            "targets": raw_targets.tolist(),
        }
    )
    aligned_states = raw_states.copy()
    aligned_targets = raw_targets.copy()
    flips = 0
    if _first_quaternion_sign(aligned_states[0, QUATERNION_SLICE_V2]) < 0.0:
        aligned_states[0, QUATERNION_SLICE_V2] *= -1.0
        flips += 1
    for index in range(1, aligned_states.shape[0]):
        previous = aligned_states[index - 1, QUATERNION_SLICE_V2]
        current = aligned_states[index, QUATERNION_SLICE_V2]
        if float(np.dot(previous, current)) < 0.0:
            aligned_states[index, QUATERNION_SLICE_V2] *= -1.0
            flips += 1
    for index in range(aligned_targets.shape[0]):
        reference_index = min(index + 1, aligned_states.shape[0] - 1)
        reference = aligned_states[reference_index, QUATERNION_SLICE_V2]
        target = aligned_targets[index, QUATERNION_SLICE_V2]
        if float(np.dot(reference, target)) < 0.0:
            aligned_targets[index, QUATERNION_SLICE_V2] *= -1.0
            flips += 1
    return QuaternionPreprocessedEpisodeV2(
        episode_id=episode_id,
        states=aligned_states,
        targets=aligned_targets,
        source_sha256=source_sha256,
        sign_flip_count=flips,
    )
