"""Data-driven disturbance protocols with reproducible excitation generation.

The JSON records preserve each historical protocol exactly. Algorithm selection
is explicit because v86 predates the shared v87/v88 waveform algorithm. None of
the versioned Python protocol implementations is needed by this module.
"""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np


_PROTOCOL_ROOT = Path(__file__).resolve().parents[1] / "experiments" / "phase9"
_VERSIONS = ("v86", "v87", "v88")


class DisturbanceProtocol:
    """A selected experiment record; callers receive independent dictionary copies.

    RIDGE is None for v88: that evaluation fits no model and must not silently
    inherit a training setting from another experiment.
    """

    COLLECTOR = "workflows.collect_disturbance_data"

    def __init__(self, version):
        if version not in _VERSIONS:
            raise ValueError("disturbance_protocol_version")
        self.VERSION = version
        self._record = json.loads(
            (_PROTOCOL_ROOT / version / "protocol.json").read_text(encoding="utf-8")
        )
        if self._record.get("schema") != f"disturbance-experiment-{version}":
            raise ValueError("disturbance_protocol_schema")
        self.RIDGE = self._record.get("ridge")

    def cases(self):
        return deepcopy(self._record["cases"])

    def protocol(self):
        return deepcopy(self._record)

    def excitation(self, case):
        if case not in self._record["cases"]:
            raise ValueError(f"{self.VERSION}_case")
        algorithm = _early_waveform if self.VERSION == "v86" else _diverse_waveform
        return algorithm(case)

    def validate_split(self, train, validation, test):
        for group, role in zip((train, validation, test), ("train", "validation", "test")):
            if group != [case for case in self._record["cases"] if case["role"] == role]:
                raise ValueError(f"{self.VERSION}_episode_split")


def get_protocol(version="v88"):
    """Load an explicitly supported experiment, defaulting to the current matrix."""
    return DisturbanceProtocol(version)


def _early_waveform(case):
    rng = np.random.default_rng(case["seed"])
    n = 96
    t = np.arange(n) / 96
    result = np.zeros((160, 4), np.float32)
    phase = rng.uniform(-np.pi, np.pi, (4, 3))
    if case["excitation"] == "prbs":
        h = np.array([[1, 1, 1, 1], [1, -1, 1, -1],
                      [1, 1, -1, -1], [1, -1, -1, 1]])
        pairs = rng.choice([-1, 1], (8, 4))
        pairs[:4] = h[rng.permutation(4)] * rng.choice([-1, 1], 4)
    for axis, amp in enumerate([2., 1., .5, .25]):
        if case["excitation"] == "prbs":
            v = np.repeat(np.column_stack([pairs[:, axis], -pairs[:, axis]]).reshape(-1), 6)
        elif case["excitation"] == "multisine":
            v = np.sin(2 * np.pi * t[:, None] * np.array([1 + axis, 3 + axis, 5 + axis])
                       + phase[axis]).mean(1)
        else:
            low, high = 1 + axis / 4, 4 + axis
            v = np.sin(2 * np.pi * t * (low + .5 * (high - low) * t) + phase[axis, 0])
        result[64:, axis] = amp * v
    return result


def _diverse_waveform(case):
    rng = np.random.default_rng(case["seed"])
    n = 256
    t = np.arange(n) / 30
    out = np.zeros((320, 4), np.float32)
    for axis, amp in enumerate([2., 1., .5, .25]):
        phase = rng.uniform(-np.pi, np.pi, 3)
        if case["excitation"] == "prbs":
            dwell = int(rng.choice([8, 12, 16, 24]))
            signs = rng.choice([-1., 1.], int(np.ceil(n / dwell)))
            v = np.repeat(signs, dwell)[:n]
        elif case["excitation"] == "multisine":
            frequency = rng.uniform([.12, .4, .9], [.3, .8, 1.7])
            v = np.sin(2 * np.pi * t[:, None] * frequency + phase).sum(1) / 2
        elif case["excitation"] == "chirp":
            low = float(rng.uniform(.1, .3))
            high = float(rng.uniform(1.2, 2.4))
            if rng.random() < .5:
                low, high = high, low
            v = np.sin(2 * np.pi * (low * t + .5 * (high - low) * t * t / (n / 30)) + phase[0])
        else:
            duration = int(rng.choice([16, 24, 32]))
            block = np.r_[np.linspace(0, 1, 8), np.ones(duration), np.linspace(1, 0, 8), np.zeros(8)]
            wave = np.r_[block, -block]
            v = np.roll(np.resize(wave, n), int(rng.integers(0, len(wave))))
        v -= v.mean()
        v /= max(1., float(np.max(abs(v))))
        out[64:, axis] = amp * case["amplitude_scale"] * v
    return out
