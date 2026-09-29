from pathlib import Path

import pytest

from koopman_data import (
    ACTION_DIM,
    KoopmanDataLogger,
    PWM_DIM,
    REFERENCE_DIM,
    STATE_DIM,
    build_koopman_sample,
    load_koopman_samples,
    reconstruct_training_tuples,
    summarize_koopman_samples,
    validate_koopman_sequence,
)


def valid_sample_kwargs(**overrides):
    kwargs = {
        "t": 1.0 / 60.0,
        "state": [1.5, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "reference": [0.0, 1.0, 0.0, 0.0, 0.0],
        "action_4d": [0.0, -0.0, 0.0, -0.75],
        "pwm_8d": [-0.2334, -0.2334, -0.2334, -0.2334, 0.0, -0.0, -0.0, 0.0],
        "next_state": [
            1.499337077140808,
            1.0,
            0.0,
            0.0,
            0.0,
            7.699680537598397e-08,
            0.0,
            -0.050149060785770416,
            0.0,
            5.321732032825821e-08,
            0.0,
        ],
        "trajectory_type": "step",
        "controller_mode": "legacy/Ssurface",
    }
    kwargs.update(overrides)
    return kwargs


def test_koopman_sample_round_trips_to_training_tuple(tmp_path: Path):
    log_path = tmp_path / "sample.jsonl"
    sample = build_koopman_sample(**valid_sample_kwargs())

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
        ("state", [0.0] * (STATE_DIM - 1), "state"),
        ("next_state", [0.0] * (STATE_DIM - 1), "next_state"),
        ("reference", [0.0] * (REFERENCE_DIM - 1), "reference"),
        ("action_4d", [0.0] * (ACTION_DIM - 1), "action_4d"),
        ("pwm_8d", [0.0] * (PWM_DIM - 1), "pwm_8d"),
        ("pwm_8d", [0.0] * (PWM_DIM - 1) + [1.5], "pwm_8d values"),
    ],
)
def test_koopman_sample_rejects_bad_dimensions_and_pwm_bounds(field, value, match):
    kwargs = valid_sample_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError, match=match):
        build_koopman_sample(**kwargs)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("action_4d", [0.0, 0.0, 0.0], "action_4d"),
        ("pwm_8d", [0.0] * 7, "pwm_8d"),
    ],
)
def test_koopman_sample_rejects_bad_control_lengths(field, value, match):
    kwargs = valid_sample_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError, match=match):
        build_koopman_sample(**kwargs)


def test_koopman_sequence_summary_accepts_current_phase1_schema():
    first = build_koopman_sample(**valid_sample_kwargs(t=1.0 / 60.0))
    second = build_koopman_sample(
        **valid_sample_kwargs(t=2.0 / 60.0, state=first["next_state"], next_state=[1.4979861974716187] + first["next_state"][1:])
    )

    validate_koopman_sequence([first, second])
    summary = summarize_koopman_samples([first, second])

    assert summary == {
        "count": 2,
        "state_dim": STATE_DIM,
        "reference_dim": REFERENCE_DIM,
        "action_dim": ACTION_DIM,
        "pwm_dim": PWM_DIM,
        "t_start": pytest.approx(1.0 / 60.0),
        "t_end": pytest.approx(2.0 / 60.0),
        "trajectory_types": ["step"],
        "controller_modes": ["legacy/Ssurface"],
    }


def test_koopman_sequence_rejects_non_increasing_timestamps():
    first = build_koopman_sample(**valid_sample_kwargs(t=2.0 / 60.0))
    second = build_koopman_sample(**valid_sample_kwargs(t=1.0 / 60.0))

    with pytest.raises(ValueError, match="strictly increasing"):
        validate_koopman_sequence([first, second])
