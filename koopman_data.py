from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


REQUIRED_FIELDS = (
    "t",
    "state",
    "reference",
    "action_4d",
    "pwm_8d",
    "next_state",
)


def _flat_float_list(values: Any, field_name: str) -> list[float]:
    if hasattr(values, "detach"):
        values = values.detach().cpu().reshape(-1).tolist()
    elif hasattr(values, "tolist"):
        values = values.tolist()

    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError(f"{field_name} must be a sequence of numbers")

    flattened: list[float] = []
    for value in values:
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            flattened.extend(_flat_float_list(value, field_name))
        else:
            flattened.append(float(value))
    return flattened


def build_koopman_sample(
    *,
    t: float,
    state: Any,
    reference: Any,
    action_4d: Any,
    pwm_8d: Any,
    next_state: Any,
    trajectory_type: str,
    controller_mode: str,
) -> dict[str, Any]:
    sample = {
        "t": float(t),
        "state": _flat_float_list(state, "state"),
        "reference": _flat_float_list(reference, "reference"),
        "action_4d": _flat_float_list(action_4d, "action_4d"),
        "pwm_8d": _flat_float_list(pwm_8d, "pwm_8d"),
        "next_state": _flat_float_list(next_state, "next_state"),
        "trajectory_type": str(trajectory_type),
        "controller_mode": str(controller_mode),
    }
    validate_koopman_sample(sample)
    return sample


def validate_koopman_sample(sample: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in sample]
    if missing:
        raise ValueError(f"Missing Koopman sample fields: {missing}")
    if len(sample["action_4d"]) != 4:
        raise ValueError("action_4d must contain exactly 4 values")
    if len(sample["pwm_8d"]) != 8:
        raise ValueError("pwm_8d must contain exactly 8 values")
    if len(sample["state"]) == 0:
        raise ValueError("state must not be empty")
    if len(sample["state"]) != len(sample["next_state"]):
        raise ValueError("state and next_state must have the same length")
    if len(sample["reference"]) == 0:
        raise ValueError("reference must not be empty")


class KoopmanDataLogger:
    def __init__(self, path: str | Path, *, append: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        self._file = self.path.open(mode, encoding="utf-8")

    def write(self, sample: dict[str, Any]) -> None:
        validate_koopman_sample(sample)
        json.dump(sample, self._file, separators=(",", ":"))
        self._file.write("\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "KoopmanDataLogger":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def load_koopman_samples(path: str | Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line)
            validate_koopman_sample(sample)
            samples.append(sample)
    return samples


def reconstruct_training_tuples(
    samples: Iterable[dict[str, Any]],
) -> list[tuple[list[float], list[float], list[float], list[float]]]:
    tuples = []
    for sample in samples:
        validate_koopman_sample(sample)
        tuples.append(
            (
                sample["state"],
                sample["pwm_8d"],
                sample["reference"],
                sample["next_state"],
            )
        )
    return tuples
