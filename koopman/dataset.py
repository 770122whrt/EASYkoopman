from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from koopman_data import PWM_DIM, REFERENCE_DIM, STATE_DIM, load_koopman_samples, validate_koopman_sequence


@dataclass(frozen=True)
class KoopmanDataset:
    X: np.ndarray
    U: np.ndarray
    R: np.ndarray
    Y: np.ndarray
    t: np.ndarray
    source_paths: tuple[str, ...]
    dt: float | None
    trajectory_types: tuple[str, ...]
    controller_modes: tuple[str, ...]

    def __post_init__(self) -> None:
        arrays = {
            "X": np.asarray(self.X, dtype=float),
            "U": np.asarray(self.U, dtype=float),
            "R": np.asarray(self.R, dtype=float),
            "Y": np.asarray(self.Y, dtype=float),
            "t": np.asarray(self.t, dtype=float),
        }
        object.__setattr__(self, "X", arrays["X"])
        object.__setattr__(self, "U", arrays["U"])
        object.__setattr__(self, "R", arrays["R"])
        object.__setattr__(self, "Y", arrays["Y"])
        object.__setattr__(self, "t", arrays["t"])

        expected = {
            "X": STATE_DIM,
            "U": PWM_DIM,
            "R": REFERENCE_DIM,
            "Y": STATE_DIM,
        }
        for name, width in expected.items():
            array = arrays[name]
            if array.ndim != 2 or array.shape[1] != width:
                raise ValueError(f"{name} must have shape (n, {width})")
        if arrays["t"].ndim != 1:
            raise ValueError("t must have shape (n,)")

        counts = {arrays[name].shape[0] for name in ("X", "U", "R", "Y")}
        counts.add(arrays["t"].shape[0])
        if len(counts) != 1:
            raise ValueError("X, U, R, Y and t must contain the same number of samples")
        if self.sample_count == 0:
            raise ValueError("KoopmanDataset must contain at least one sample")

    @property
    def sample_count(self) -> int:
        return int(self.X.shape[0])


def _path_list(paths: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    path_list = [Path(path) for path in paths]
    if not path_list:
        raise ValueError("load_dataset requires at least one JSONL path")
    return path_list


def _estimate_dt(times: np.ndarray) -> float | None:
    if times.size < 2:
        return None
    diffs = np.diff(times)
    positive = diffs[diffs > 0]
    if positive.size == 0:
        return None
    return float(np.median(positive))


def dataset_from_samples(
    samples: Iterable[dict],
    *,
    source_paths: Iterable[str] = (),
    validate_time: bool = True,
) -> KoopmanDataset:
    sample_list = list(samples)
    if validate_time:
        validate_koopman_sequence(sample_list)
    if not sample_list:
        raise ValueError("KoopmanDataset must contain at least one sample")

    X = np.asarray([sample["state"] for sample in sample_list], dtype=float)
    U = np.asarray([sample["pwm_8d"] for sample in sample_list], dtype=float)
    R = np.asarray([sample["reference"] for sample in sample_list], dtype=float)
    Y = np.asarray([sample["next_state"] for sample in sample_list], dtype=float)
    t = np.asarray([sample["t"] for sample in sample_list], dtype=float)

    return KoopmanDataset(
        X=X,
        U=U,
        R=R,
        Y=Y,
        t=t,
        source_paths=tuple(source_paths),
        dt=_estimate_dt(t),
        trajectory_types=tuple(sorted({sample["trajectory_type"] for sample in sample_list})),
        controller_modes=tuple(sorted({sample["controller_mode"] for sample in sample_list})),
    )


def load_dataset(paths: str | Path | Iterable[str | Path]) -> KoopmanDataset:
    path_list = _path_list(paths)
    all_samples: list[dict] = []
    dt_values: list[float] = []

    for path in path_list:
        samples = load_koopman_samples(path)
        if len(samples) > 1:
            file_dt = _estimate_dt(np.asarray([sample["t"] for sample in samples], dtype=float))
            if file_dt is not None:
                dt_values.append(file_dt)
        all_samples.extend(samples)

    dataset = dataset_from_samples(
        all_samples,
        source_paths=[str(path) for path in path_list],
        validate_time=len(path_list) == 1,
    )
    if dt_values:
        return KoopmanDataset(
            X=dataset.X,
            U=dataset.U,
            R=dataset.R,
            Y=dataset.Y,
            t=dataset.t,
            source_paths=dataset.source_paths,
            dt=float(np.median(dt_values)),
            trajectory_types=dataset.trajectory_types,
            controller_modes=dataset.controller_modes,
        )
    return dataset

