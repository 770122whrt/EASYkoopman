"""Isaac-free contract tests for the EasyUUV 2.0 embodiment catalog."""

from __future__ import annotations

from pathlib import Path

import pytest

from easyuuv_nc.embodiments import (
    CONTROL_CHANNELS,
    EMBODIMENT_CONFIGS,
    INTERNAL_EMBODIMENTS,
    SUPPORTED_EMBODIMENTS,
    qualification_record,
)
from easyuuv_nc.thrust_allocation import declared_control_rank


PROJECT_ROOT = Path(__file__).resolve().parents[1]


EXPECTED_PUBLIC_CONFIGURATIONS = (
    ("base", 8, (1, 1, 1, 1), 4),
    ("long_body", 8, (1, 1, 1, 1), 4),
    ("heavy_moderate", 8, (1, 1, 1, 1), 4),
    ("asymmetric", 8, (1, 1, 1, 1), 4),
    ("uuv6", 6, (1, 1, 1, 1), 4),
    ("uuv6_angled", 6, (1, 1, 1, 1), 4),
    ("uuv4", 4, (1, 1, 0, 1), 3),
    ("uuv4_angled", 4, (1, 1, 0, 1), 3),
)


def test_public_configuration_matrix_is_exact():
    assert CONTROL_CHANNELS == ("roll", "pitch", "yaw", "depth")
    assert SUPPORTED_EMBODIMENTS == tuple(row[0] for row in EXPECTED_PUBLIC_CONFIGURATIONS)
    assert INTERNAL_EMBODIMENTS == ("heavy_duty",)
    assert set(EMBODIMENT_CONFIGS) == set(SUPPORTED_EMBODIMENTS) | set(INTERNAL_EMBODIMENTS)

    records = [qualification_record(name) for name in SUPPORTED_EMBODIMENTS]
    assert "heavy_duty" not in {record["configuration"] for record in records}

    assert [
        (
            record["configuration"],
            record["thruster_count"],
            record["control_mask"],
            record["declared_control_rank"],
        )
        for record in records
    ] == list(EXPECTED_PUBLIC_CONFIGURATIONS)


@pytest.mark.parametrize("name, _count, _mask, expected_rank", EXPECTED_PUBLIC_CONFIGURATIONS)
def test_declared_control_rank_matches_public_qualification_matrix(
    name: str, _count: int, _mask: tuple[int, int, int, int], expected_rank: int
):
    assert declared_control_rank(EMBODIMENT_CONFIGS[name]) == expected_rank


def test_unknown_configuration_is_rejected_with_its_name():
    with pytest.raises(KeyError, match="unsupported_vehicle"):
        qualification_record("unsupported_vehicle")


@pytest.mark.parametrize(
    "relative_path",
    (
        "easyuuv_nc/env/easyuuv_env.py",
        "easyuuv_nc/workflows/train.py",
        "easyuuv_nc/workflows/adapt.py",
    ),
)
def test_runtime_consumers_use_the_canonical_catalog(relative_path: str):
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    if relative_path.endswith("easyuuv_env.py"):
        assert "EMBODIMENT_CONFIGS" in source
    else:
        assert "choices=SUPPORTED_EMBODIMENTS" in source

    assert 'choices=["base", "long_body"' not in source
