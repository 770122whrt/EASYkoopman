from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable


STATE_DIM = 11
REFERENCE_DIM = 5
ACTION_DIM = 4
PWM_DIM = 8

REQUIRED_FIELDS = (
    "t",
    "state",
    "reference",
    "action_4d",
    "pwm_8d",
    "next_state",
    "trajectory_type",
    "controller_mode",
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

    sample["t"] = float(sample["t"])
    if not math.isfinite(sample["t"]):
        raise ValueError("t must be a finite number")

    for field_name in ("trajectory_type", "controller_mode"):
        if not isinstance(sample[field_name], str) or not sample[field_name].strip():
            raise ValueError(f"{field_name} must be a non-empty string")

    expected_lengths = {
        "state": STATE_DIM,
        "reference": REFERENCE_DIM,
        "action_4d": ACTION_DIM,
        "pwm_8d": PWM_DIM,
        "next_state": STATE_DIM,
    }
    for field_name, expected_length in expected_lengths.items():
        values = _flat_float_list(sample[field_name], field_name)
        if len(values) != expected_length:
            raise ValueError(f"{field_name} must contain exactly {expected_length} values")
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{field_name} values must be finite numbers")
        sample[field_name] = values

    if not all(-1.0 <= value <= 1.0 for value in sample["pwm_8d"]):
        raise ValueError("pwm_8d values must stay within [-1, 1]")


def validate_koopman_sequence(samples: Iterable[dict[str, Any]]) -> None:
    previous_t: float | None = None
    count = 0
    for index, sample in enumerate(samples):
        validate_koopman_sample(sample)
        current_t = sample["t"]
        if previous_t is not None and current_t <= previous_t:
            raise ValueError(
                f"Koopman timestamps must be strictly increasing at sample {index}: {current_t} <= {previous_t}"
            )
        previous_t = current_t
        count += 1
    if count == 0:
        raise ValueError("Koopman log must contain at least one sample")


def summarize_koopman_samples(samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    sample_list = list(samples)
    validate_koopman_sequence(sample_list)
    first = sample_list[0]
    last = sample_list[-1]
    return {
        "count": len(sample_list),
        "state_dim": len(first["state"]),
        "reference_dim": len(first["reference"]),
        "action_dim": len(first["action_4d"]),
        "pwm_dim": len(first["pwm_8d"]),
        "t_start": first["t"],
        "t_end": last["t"],
        "trajectory_types": sorted({sample["trajectory_type"] for sample in sample_list}),
        "controller_modes": sorted({sample["controller_mode"] for sample in sample_list}),
    }


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
    validate_koopman_sequence(samples)
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
