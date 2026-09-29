from pathlib import Path

import pytest

from koopman_data import KoopmanDataLogger, build_koopman_sample
from tests.test_koopman_data import valid_sample_kwargs
from workflows.validate_koopman_log import main


def test_validate_koopman_log_cli_reports_summary(tmp_path: Path, capsys):
    log_path = tmp_path / "koopman_step.jsonl"
    sample = build_koopman_sample(**valid_sample_kwargs())

    with KoopmanDataLogger(log_path) as logger:
        logger.write(sample)

    assert main([str(log_path)]) == 0

    output = capsys.readouterr().out
    assert "OK: 1 samples" in output
    assert "state_dim=11" in output
    assert "reference_dim=5" in output
    assert "action_dim=4" in output
    assert "pwm_dim=8" in output
    assert "trajectory_types=step" in output
    assert "controller_modes=legacy/Ssurface" in output


def test_validate_koopman_log_cli_rejects_bad_sequence(tmp_path: Path, capsys):
    log_path = tmp_path / "koopman_bad.jsonl"
    first = build_koopman_sample(**valid_sample_kwargs(t=2.0 / 60.0))
    second = build_koopman_sample(**valid_sample_kwargs(t=1.0 / 60.0))

    with KoopmanDataLogger(log_path) as logger:
        logger.write(first)
        logger.write(second)

    with pytest.raises(SystemExit) as exc_info:
        main([str(log_path)])

    assert exc_info.value.code == 1
    assert "strictly increasing" in capsys.readouterr().err
