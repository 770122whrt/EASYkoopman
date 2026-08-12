"""Contracts for explicit, read-only and non-promoting v1 Koopman access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from koopman.dataset_v2 import dataset_from_records_v2
from koopman.schema_v2 import validate_transition_v2
from koopman.v1_compatibility import (
    V1CompatibilityView,
    load_v1_compatibility,
    require_v2_training_eligibility,
)
from koopman_data import load_koopman_samples


FIXTURE = Path(__file__).parent / "fixtures" / "koopman_step_small.jsonl"
FIXTURE_SHA256 = "c1fcb16c9d3d7828a57f2790509b35a60f1f8d59bf60abf7fcdeb0ae1c51f955"
EXPECTED_UNAVAILABLE_FIELDS = frozenset(
    {
        "virtual_control_4",
        "thruster_mask_8",
        "applied_wrench_6",
        "platform_context",
        "environment_context_oracle",
        "environment_context_estimated",
        "configuration",
        "episode_provenance",
    }
)


def test_v1_view_is_never_v2_training_eligible() -> None:
    view = load_v1_compatibility(FIXTURE)

    assert isinstance(view, V1CompatibilityView)
    assert view.source_schema == "v1"
    assert view.eligible_for_v2_cross_configuration_training is False
    assert view.unavailable_fields == EXPECTED_UNAVAILABLE_FIELDS
    assert len(view.samples) == 4
    with pytest.raises(ValueError, match="v1_not_v2_training_eligible"):
        require_v2_training_eligibility(view)


def test_v1_view_copies_and_freezes_existing_loader_output(monkeypatch) -> None:
    import koopman.v1_compatibility as compatibility

    calls: list[Path] = []
    canonical_samples = load_koopman_samples(FIXTURE)

    def existing_loader(path: str | Path):
        calls.append(Path(path))
        return canonical_samples

    monkeypatch.setattr(compatibility, "load_koopman_samples", existing_loader)
    view = compatibility.load_v1_compatibility(FIXTURE)
    assert calls == [FIXTURE]
    assert [dict(sample) for sample in view.samples] == canonical_samples

    canonical_samples[0]["state"][0] = 999.0
    assert view.samples[0]["state"][0] == 1.5
    with pytest.raises(TypeError):
        view.samples[0]["state"] = ()
    with pytest.raises(TypeError):
        view.samples[0]["state"][0] = 999.0


def test_v1_adapter_has_no_promotion_or_inferred_runtime_facts() -> None:
    view = load_v1_compatibility(FIXTURE)
    forbidden = {
        "to_v2",
        "promote",
        "configuration",
        "virtual_control_4",
        "applied_wrench_6",
        "platform_context",
        "environment_context_oracle",
        "environment_context_estimated",
    }
    assert forbidden.isdisjoint(dir(view))
    first = view.samples[0]
    assert set(first) == {
        "t",
        "state",
        "reference",
        "action_4d",
        "pwm_8d",
        "next_state",
        "trajectory_type",
        "controller_mode",
    }
    assert "virtual_control_4" not in first
    assert "configuration" not in first
    assert "applied_wrench_6" not in first


def test_raw_v1_and_compatibility_samples_fail_strict_v2_paths() -> None:
    raw = load_koopman_samples(FIXTURE)[0]
    view = load_v1_compatibility(FIXTURE)

    with pytest.raises(ValueError, match="field_set_mismatch"):
        validate_transition_v2(raw)
    with pytest.raises(ValueError, match="field_set_mismatch"):
        validate_transition_v2(view.samples[0])
    with pytest.raises(ValueError, match="type_invalid|episode_too_short|field_set_mismatch"):
        dataset_from_records_v2(view.samples)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        (lambda row: row.pop("pwm_8d"), "Missing Koopman sample fields"),
        (lambda row: row.__setitem__("pwm_8d", [0.0] * 7), "pwm_8d"),
        (lambda row: row.__setitem__("t", float("nan")), "finite"),
    ),
)
def test_corrupt_v1_still_fails_through_existing_loader(
    tmp_path: Path, mutation, reason: str
) -> None:
    rows = load_koopman_samples(FIXTURE)
    mutation(rows[0])
    path = tmp_path / "corrupt-v1.jsonl"
    path.write_text(
        "".join(json.dumps(row, allow_nan=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=reason):
        load_v1_compatibility(path)


def test_canonical_v1_fixture_bytes_are_unchanged() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
