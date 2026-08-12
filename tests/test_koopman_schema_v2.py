"""Contract tests for the pure-Python Koopman transition schema v2."""

from __future__ import annotations

from copy import deepcopy
import importlib
import sys

import pytest

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS, qualification_record
from koopman.schema_v2 import (
    KOOPMAN_TRANSITION_SCHEMA_V2,
    build_local_transition_v2,
    validate_transition_v2,
)


PUBLIC_CONFIGURATIONS = (
    "base",
    "long_body",
    "heavy_moderate",
    "asymmetric",
    "uuv6",
    "uuv6_angled",
    "uuv4",
    "uuv4_angled",
)


def _oracle_context(thruster_count: int) -> dict:
    values = {
        "fluid_velocity_world_3": [0.1, -0.2, 0.05],
        "water_density_kg_m3": 1028.0,
        "dynamic_viscosity_pa_s": 0.00108,
        "drag_multiplier": 1.0,
        "thruster_efficiency_n": [1.0] * thruster_count,
    }
    return {
        "available": True,
        "method": "runtime_cache",
        "method_version": "1",
        "source_kind": "simulator_ground_truth",
        "source_signals": [
            "fluid_velocity_world_3",
            "water_density_kg_m3",
            "dynamic_viscosity_pa_s",
            "drag_multiplier",
            "thruster_efficiency_n",
        ],
        "values": values,
        "units": {
            "fluid_velocity_world_3": "m/s",
            "water_density_kg_m3": "kg/m^3",
            "dynamic_viscosity_pa_s": "Pa*s",
            "drag_multiplier": "dimensionless",
            "thruster_efficiency_n": "dimensionless",
        },
        "frames": {
            "fluid_velocity_world_3": "world",
            "water_density_kg_m3": "scalar",
            "dynamic_viscosity_pa_s": "scalar",
            "drag_multiplier": "scalar",
            "thruster_efficiency_n": "per_thruster",
        },
        "value_provenance": {
            key: "same_step_runtime_cache" for key in values
        },
    }


def _unavailable_estimated_context() -> dict:
    return {
        "available": False,
        "method": "",
        "method_version": "",
        "source_kind": "unavailable",
        "source_signals": [],
        "values": {},
        "units": {},
        "frames": {},
        "value_provenance": {},
    }


def valid_transition(configuration: str = "base", **overrides) -> dict:
    topology = qualification_record(configuration)
    thruster_count = topology["thruster_count"]
    pwm = [0.1 * ((index % 3) - 1) for index in range(thruster_count)]
    pwm.extend([0.0] * (8 - thruster_count))
    virtual_control = [0.2, -0.1, 0.0 if configuration.startswith("uuv4") else 0.3, -0.4]
    payload = {
        "schema_version": "easyuuv-koopman-transition-v2",
        "state_11": [0.0, 0.1, 0.2, 0.0, 0.0, 0.0, 1.0, 0.01, 0.02, 0.03, 0.04],
        "reference_5": [1.5, 1.0, 0.0, 0.0, 0.0],
        "raw_action_4": [0.2, -0.1, 0.75, -0.4],
        "virtual_control_4": virtual_control,
        "motor_pwm_padded_8": pwm,
        "thruster_mask_8": [1] * thruster_count + [0] * (8 - thruster_count),
        "applied_wrench_6": [0.5, -0.25, 1.5, 0.1, -0.2, 0.05],
        "platform_context": {
            "configuration": configuration,
            "thruster_count": thruster_count,
            "control_channels": list(topology["control_channels"]),
            "control_mask": list(topology["control_mask"]),
            "allocation_mode": topology["allocation_mode"],
            "declared_control_rank": topology["declared_control_rank"],
            "mass_kg": 22.701,
            "inertia_diagonal_kg_m2": [0.37, 0.97, 1.19],
            "com_to_cob_offset_m": [0.0, 0.0, 0.01],
            "volume_m3": 0.023,
            "drag_multiplier": 1.0,
            "thruster_dynamics_time_constant_s": 0.05,
        },
        "environment_context_oracle": _oracle_context(thruster_count),
        "environment_context_estimated": _unavailable_estimated_context(),
        "next_state_11": [0.01, 0.11, 0.21, 0.0, 0.0, 0.0, 1.0, 0.02, 0.03, 0.04, 0.05],
        "episode_provenance": {
            "configuration": configuration,
            "scenario": "phase7-contract",
            "episode_id": f"contract-{configuration}-001",
            "step_index": 0,
            "seed": 7,
            "simulation_time_s": 0.0,
            "control_dt_s": 0.02,
            "task_id": "EasyUUV-Direct-v1",
            "controller_mode": "legacy/Ssurface",
            "source_commit": "a" * 40,
            "evidence_level": "local_contract",
        },
    }
    payload.update(overrides)
    return payload


def assert_reason(payload: dict, reason: str) -> None:
    with pytest.raises(ValueError, match=rf"^{reason}(?::|$)"):
        validate_transition_v2(payload)


@pytest.mark.parametrize("configuration", PUBLIC_CONFIGURATIONS)
def test_exact_schema_v2_transition_is_valid(configuration: str):
    assert tuple(SUPPORTED_EMBODIMENTS) == PUBLIC_CONFIGURATIONS
    payload = valid_transition(configuration)
    before = deepcopy(payload)

    validate_transition_v2(payload)

    assert payload == before
    assert payload["schema_version"] == KOOPMAN_TRANSITION_SCHEMA_V2


def test_builder_returns_fresh_local_only_transition():
    source = valid_transition()

    built = build_local_transition_v2(**source)
    built["state_11"][0] = 99.0

    assert source["state_11"][0] == 0.0
    assert built["episode_provenance"]["evidence_level"] == "local_contract"


@pytest.mark.parametrize("bad_version", [2, "2", "v2", "easyuuv-koopman-transition-v2.1"])
def test_transition_rejects_ambiguous_or_future_version(bad_version):
    payload = valid_transition()
    payload["schema_version"] = bad_version
    assert_reason(payload, "schema_version_mismatch")


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_transition_rejects_missing_and_extra_top_level_fields(change: str):
    payload = valid_transition()
    if change == "missing":
        del payload["reference_5"]
    else:
        payload["pwm_8d"] = [0.0] * 8
    assert_reason(payload, "field_set_mismatch")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("state_11", [0.0] * 10, "shape_invalid"),
        ("reference_5", [0.0] * 4, "shape_invalid"),
        ("raw_action_4", [0.0] * 3, "shape_invalid"),
        ("virtual_control_4", [0.0] * 5, "shape_invalid"),
        ("motor_pwm_padded_8", [0.0] * 7, "shape_invalid"),
        ("thruster_mask_8", [1] * 7, "shape_invalid"),
        ("applied_wrench_6", [0.0] * 5, "shape_invalid"),
        ("next_state_11", [0.0] * 12, "shape_invalid"),
        ("state_11", [0.0] * 10 + [float("nan")], "nonfinite_value"),
        ("applied_wrench_6", [0.0] * 5 + [float("inf")], "nonfinite_value"),
        ("raw_action_4", [0.0, 0.0, 0.0, 1.01], "control_out_of_bounds"),
        ("virtual_control_4", [-1.01, 0.0, 0.0, 0.0], "control_out_of_bounds"),
        ("motor_pwm_padded_8", [0.0] * 7 + [1.01], "pwm_out_of_bounds"),
        ("thruster_mask_8", [True] + [1] * 7, "type_invalid"),
        ("thruster_mask_8", [1, 1, 2, 1, 1, 1, 1, 1], "mask_mismatch"),
    ],
)
def test_transition_rejects_vector_shape_type_finite_and_range_mutations(
    field: str, value, reason: str
):
    payload = valid_transition()
    payload[field] = value
    assert_reason(payload, reason)


def test_transition_rejects_unknown_or_internal_configuration():
    for configuration in ("unknown", "heavy_duty"):
        payload = valid_transition()
        payload["platform_context"]["configuration"] = configuration
        payload["episode_provenance"]["configuration"] = configuration
        assert_reason(payload, "configuration_unknown")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("thruster_count", 6),
        ("control_channels", ["roll", "pitch", "depth", "yaw"]),
        ("control_mask", [1, 1, 0, 1]),
        ("allocation_mode", "pinv"),
        ("declared_control_rank", 3),
    ],
)
def test_platform_topology_must_match_canonical_catalog(field: str, value):
    payload = valid_transition("base")
    payload["platform_context"][field] = value
    assert_reason(payload, "topology_mismatch")


def test_mask_padding_and_underactuated_yaw_are_explicit():
    payload = valid_transition("uuv6")
    payload["motor_pwm_padded_8"][7] = 0.25
    assert_reason(payload, "padding_nonzero")

    payload = valid_transition("uuv6")
    payload["thruster_mask_8"] = [1] * 8
    assert_reason(payload, "mask_mismatch")

    payload = valid_transition("uuv4")
    assert payload["raw_action_4"][2] != 0.0
    payload["virtual_control_4"][2] = payload["raw_action_4"][2]
    assert_reason(payload, "underactuated_yaw_nonzero")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("mass_kg", 0.0, "context_value_invalid"),
        ("inertia_diagonal_kg_m2", [0.37, 0.97], "shape_invalid"),
        ("com_to_cob_offset_m", [0.0, float("nan"), 0.01], "nonfinite_value"),
        ("volume_m3", -0.01, "context_value_invalid"),
        ("drag_multiplier", 0.0, "context_value_invalid"),
        ("thruster_dynamics_time_constant_s", True, "type_invalid"),
    ],
)
def test_platform_context_rejects_invalid_dynamics(field: str, value, reason: str):
    payload = valid_transition()
    payload["platform_context"][field] = value
    assert_reason(payload, reason)


def test_nested_objects_use_exact_field_sets():
    for object_name in (
        "platform_context",
        "environment_context_oracle",
        "environment_context_estimated",
        "episode_provenance",
    ):
        payload = valid_transition()
        payload[object_name]["unexpected"] = "drift"
        assert_reason(payload, "field_set_mismatch")


def test_oracle_requires_units_frames_and_value_provenance():
    for namespace in ("units", "frames", "value_provenance"):
        payload = valid_transition()
        del payload["environment_context_oracle"][namespace]["fluid_velocity_world_3"]
        assert_reason(payload, "context_provenance_invalid")

    payload = valid_transition()
    payload["environment_context_oracle"]["frames"]["fluid_velocity_world_3"] = "body"
    assert_reason(payload, "context_provenance_invalid")


def test_estimated_unavailable_is_valid_and_must_be_empty():
    validate_transition_v2(valid_transition())

    payload = valid_transition()
    payload["environment_context_estimated"]["values"] = {"current_speed": 0.1}
    assert_reason(payload, "context_unavailable_invalid")


def test_available_estimate_requires_deployable_method_version_and_signals():
    payload = valid_transition()
    payload["environment_context_estimated"] = {
        "available": True,
        "method": "observer",
        "method_version": "1",
        "source_kind": "deployable_observation",
        "source_signals": ["imu", "depth"],
        "values": {"current_speed_m_s": 0.1},
        "units": {"current_speed_m_s": "m/s"},
        "frames": {"current_speed_m_s": "body"},
        "value_provenance": {"current_speed_m_s": "observer_output"},
    }
    validate_transition_v2(payload)

    for field, value in (
        ("method", ""),
        ("method_version", ""),
        ("source_signals", []),
    ):
        mutated = deepcopy(payload)
        mutated["environment_context_estimated"][field] = value
        assert_reason(mutated, "context_provenance_invalid")


def test_oracle_cannot_alias_or_masquerade_as_estimated_context():
    payload = valid_transition()
    payload["environment_context_estimated"] = payload["environment_context_oracle"]
    assert_reason(payload, "oracle_as_estimate")

    payload = valid_transition()
    payload["environment_context_estimated"] = deepcopy(
        payload["environment_context_oracle"]
    )
    payload["environment_context_estimated"]["source_kind"] = "deployable_observation"
    assert_reason(payload, "oracle_as_estimate")

    payload = valid_transition()
    payload["environment_context_estimated"] = deepcopy(
        payload["environment_context_oracle"]
    )
    assert_reason(payload, "oracle_as_estimate")


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("configuration", "uuv6", "topology_mismatch"),
        ("step_index", True, "type_invalid"),
        ("seed", False, "type_invalid"),
        ("simulation_time_s", float("nan"), "nonfinite_value"),
        ("control_dt_s", 0.0, "context_value_invalid"),
        ("source_commit", "ABC", "source_commit_invalid"),
        ("evidence_level", "server_pass", "evidence_level_invalid"),
        ("task_id", "", "type_invalid"),
    ],
)
def test_episode_provenance_is_unambiguous(field: str, value, reason: str):
    payload = valid_transition()
    payload["episode_provenance"][field] = value
    assert_reason(payload, reason)


def test_local_builder_rejects_server_evidence_self_assertion():
    payload = valid_transition()
    payload["episode_provenance"]["evidence_level"] = "server_isaac_smoke"

    with pytest.raises(ValueError, match=r"^local_evidence_required(?::|$)"):
        build_local_transition_v2(**payload)


def test_import_contract_does_not_load_runtime_frameworks(monkeypatch):
    for module_name in (
        "koopman.schema_v2",
        "easyuuv_nc.embodiments",
        "easyuuv_nc",
    ):
        sys.modules.pop(module_name, None)
    before = set(sys.modules)

    imported = importlib.import_module("koopman.schema_v2")
    loaded = set(sys.modules) - before

    assert imported.KOOPMAN_TRANSITION_SCHEMA_V2 == "easyuuv-koopman-transition-v2"
    assert not any(
        name == blocked or name.startswith(f"{blocked}.")
        for name in loaded
        for blocked in ("torch", "gymnasium", "omni", "easyuuv_nc.env")
    )
