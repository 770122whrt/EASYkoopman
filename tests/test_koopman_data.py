from pathlib import Path

import pytest

from koopman_data import (
    KoopmanDataLogger,
    build_koopman_sample,
    load_koopman_samples,
    reconstruct_training_tuples,
)


def test_koopman_sample_round_trips_to_training_tuple(tmp_path: Path):
    log_path = tmp_path / "sample.jsonl"
    sample = build_koopman_sample(
        t=0.25,
        state=[1.5, 1.0, 0.0, 0.0, 0.0],
        reference=[0.0, 1.0, 0.0, 0.0, 0.0],
        action_4d=[0.1, -0.2, 0.3, -0.4],
        pwm_8d=[-0.1, 0.1, -0.2, 0.2, 0.3, -0.3, -0.3, 0.3],
        next_state=[1.49, 0.99, 0.01, 0.0, 0.0],
        trajectory_type="step",
        controller_mode="legacy/Ssurface",
    )

    with KoopmanDataLogger(log_path) as logger:
        logger.write(sample)

    loaded = load_koopman_samples(log_path)
    assert loaded == [sample]
    assert reconstruct_training_tuples(loaded) == [
        (
            sample["state"],
            sample["pwm_8d"],
            sample["reference"],
            sample["next_state"],
        )
    ]


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("action_4d", [0.0, 0.0, 0.0], "action_4d"),
        ("pwm_8d", [0.0] * 7, "pwm_8d"),
    ],
)
def test_koopman_sample_rejects_bad_control_lengths(field, value, match):
    kwargs = {
        "t": 0.0,
        "state": [0.0],
        "reference": [0.0],
        "action_4d": [0.0] * 4,
        "pwm_8d": [0.0] * 8,
        "next_state": [0.0],
        "trajectory_type": "step",
        "controller_mode": "legacy/Ssurface",
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=match):
        build_koopman_sample(**kwargs)
