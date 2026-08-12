"""Strict, pure-Python transition and episode contracts for Koopman schema v2.

The module deliberately imports the EasyUUV catalog lazily.  File validation and
cold imports therefore do not require Torch, Gymnasium, Isaac Sim, or Isaac Lab.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import math
import re
from typing import Any


KOOPMAN_TRANSITION_SCHEMA_V2 = "easyuuv-koopman-transition-v2"
LOCAL_EVIDENCE_LEVEL = "local_contract"
SERVER_EVIDENCE_LEVEL = "server_isaac_smoke"

STATE_DIM = 11
REFERENCE_DIM = 5
ACTION_DIM = 4
PWM_PADDED_DIM = 8
WRENCH_DIM = 6
CONTROL_BOUND = 1.0
BOUND_TOLERANCE = 1e-6

TRANSITION_FIELDS = frozenset(
    {
        "schema_version",
        "state_11",
        "reference_5",
        "raw_action_4",
        "virtual_control_4",
        "motor_pwm_padded_8",
        "thruster_mask_8",
        "applied_wrench_6",
        "platform_context",
        "environment_context_oracle",
        "environment_context_estimated",
        "next_state_11",
        "episode_provenance",
    }
)
PLATFORM_CONTEXT_FIELDS = frozenset(
    {
        "configuration",
        "thruster_count",
        "control_channels",
        "control_mask",
        "allocation_mode",
        "declared_control_rank",
        "mass_kg",
        "inertia_diagonal_kg_m2",
        "com_to_cob_offset_m",
        "volume_m3",
        "drag_multiplier",
        "thruster_dynamics_time_constant_s",
    }
)
ENVIRONMENT_CONTEXT_FIELDS = frozenset(
    {
        "available",
        "method",
        "method_version",
        "source_kind",
        "source_signals",
        "values",
        "units",
        "frames",
        "value_provenance",
    }
)
EPISODE_PROVENANCE_FIELDS = frozenset(
    {
        "configuration",
        "scenario",
        "episode_id",
        "step_index",
        "seed",
        "simulation_time_s",
        "control_dt_s",
        "task_id",
        "controller_mode",
        "source_commit",
        "evidence_level",
    }
)
ORACLE_VALUE_FIELDS = frozenset(
    {
        "fluid_velocity_world_3",
        "water_density_kg_m3",
        "dynamic_viscosity_pa_s",
        "drag_multiplier",
        "thruster_efficiency_n",
    }
)

_SOURCE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _fail(reason: str, detail: str | None = None) -> None:
    raise ValueError(reason if not detail else f"{reason}:{detail}")


def _require_exact_mapping(
    value: Any, expected_fields: frozenset[str], *, path: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("type_invalid", path)
    actual = set(value)
    if actual != expected_fields:
        missing = ",".join(sorted(expected_fields - actual)) or "none"
        extra = ",".join(sorted(actual - expected_fields)) or "none"
        _fail("field_set_mismatch", f"{path}:missing={missing};extra={extra}")
    return value


def _require_nonempty_string(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("type_invalid", path)
    return value


def _require_int(value: Any, *, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("type_invalid", path)
    return value


def _require_number(value: Any, *, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("type_invalid", path)
    numeric = float(value)
    if not math.isfinite(numeric):
        _fail("nonfinite_value", path)
    return numeric


def _require_vector(
    value: Any,
    width: int,
    *,
    path: str,
    bounds: tuple[float, float] | None = None,
    bounds_reason: str = "control_out_of_bounds",
) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("type_invalid", path)
    if len(value) != width:
        _fail("shape_invalid", f"{path}:expected={width};actual={len(value)}")
    result = [_require_number(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if bounds is not None:
        lower, upper = bounds
        for index, item in enumerate(result):
            if item < lower - BOUND_TOLERANCE or item > upper + BOUND_TOLERANCE:
                _fail(bounds_reason, f"{path}[{index}]={item}")
    return result


def _require_positive_number(value: Any, *, path: str) -> float:
    numeric = _require_number(value, path=path)
    if numeric <= 0.0:
        _fail("context_value_invalid", path)
    return numeric


def _catalog_record(configuration: Any) -> Mapping[str, Any]:
    if not isinstance(configuration, str) or not configuration:
        _fail("configuration_unknown", str(configuration))
    from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS, qualification_record

    if configuration not in SUPPORTED_EMBODIMENTS:
        _fail("configuration_unknown", configuration)
    return qualification_record(configuration)


def _validate_platform_context(value: Any) -> tuple[str, Mapping[str, Any]]:
    context = _require_exact_mapping(
        value, PLATFORM_CONTEXT_FIELDS, path="platform_context"
    )
    configuration = context["configuration"]
    topology = _catalog_record(configuration)

    expected_values = {
        "thruster_count": topology["thruster_count"],
        "control_channels": list(topology["control_channels"]),
        "control_mask": list(topology["control_mask"]),
        "allocation_mode": topology["allocation_mode"],
        "declared_control_rank": topology["declared_control_rank"],
    }
    for field, expected in expected_values.items():
        actual = context[field]
        if field in {"thruster_count", "declared_control_rank"}:
            _require_int(actual, path=f"platform_context.{field}")
        if field == "control_mask":
            if not isinstance(actual, list) or any(type(item) is not int for item in actual):
                _fail("type_invalid", f"platform_context.{field}")
        if actual != expected:
            _fail("topology_mismatch", f"platform_context.{field}")

    _require_positive_number(context["mass_kg"], path="platform_context.mass_kg")
    inertia = _require_vector(
        context["inertia_diagonal_kg_m2"],
        3,
        path="platform_context.inertia_diagonal_kg_m2",
    )
    if any(item <= 0.0 for item in inertia):
        _fail("context_value_invalid", "platform_context.inertia_diagonal_kg_m2")
    _require_vector(
        context["com_to_cob_offset_m"],
        3,
        path="platform_context.com_to_cob_offset_m",
    )
    _require_positive_number(context["volume_m3"], path="platform_context.volume_m3")
    _require_positive_number(
        context["drag_multiplier"], path="platform_context.drag_multiplier"
    )
    _require_positive_number(
        context["thruster_dynamics_time_constant_s"],
        path="platform_context.thruster_dynamics_time_constant_s",
    )
    return configuration, topology


def _validate_metadata_maps(
    context: Mapping[str, Any], *, path: str, expected_keys: set[str]
) -> None:
    for namespace in ("units", "frames", "value_provenance"):
        mapping = context[namespace]
        if not isinstance(mapping, Mapping) or set(mapping) != expected_keys:
            _fail("context_provenance_invalid", f"{path}.{namespace}")
        for key, value in mapping.items():
            _require_nonempty_string(value, path=f"{path}.{namespace}.{key}")


def _validate_finite_context_value(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _validate_finite_context_value(nested, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, nested in enumerate(value):
            _validate_finite_context_value(nested, path=f"{path}[{index}]")
        return
    _require_number(value, path=path)


def _validate_oracle_context(value: Any, *, thruster_count: int) -> Mapping[str, Any]:
    context = _require_exact_mapping(
        value, ENVIRONMENT_CONTEXT_FIELDS, path="environment_context_oracle"
    )
    if context["available"] is not True:
        _fail("context_unavailable_invalid", "environment_context_oracle.available")
    _require_nonempty_string(
        context["method"], path="environment_context_oracle.method"
    )
    _require_nonempty_string(
        context["method_version"],
        path="environment_context_oracle.method_version",
    )
    if context["source_kind"] != "simulator_ground_truth":
        _fail("context_provenance_invalid", "environment_context_oracle.source_kind")
    signals = context["source_signals"]
    if not isinstance(signals, list) or not signals or any(
        not isinstance(item, str) or not item for item in signals
    ):
        _fail("context_provenance_invalid", "environment_context_oracle.source_signals")
    values = context["values"]
    if not isinstance(values, Mapping) or set(values) != ORACLE_VALUE_FIELDS:
        _fail("field_set_mismatch", "environment_context_oracle.values")
    _require_vector(
        values["fluid_velocity_world_3"],
        3,
        path="environment_context_oracle.values.fluid_velocity_world_3",
    )
    _require_positive_number(
        values["water_density_kg_m3"],
        path="environment_context_oracle.values.water_density_kg_m3",
    )
    _require_positive_number(
        values["dynamic_viscosity_pa_s"],
        path="environment_context_oracle.values.dynamic_viscosity_pa_s",
    )
    _require_positive_number(
        values["drag_multiplier"],
        path="environment_context_oracle.values.drag_multiplier",
    )
    _require_vector(
        values["thruster_efficiency_n"],
        thruster_count,
        path="environment_context_oracle.values.thruster_efficiency_n",
    )
    _validate_metadata_maps(
        context,
        path="environment_context_oracle",
        expected_keys=set(values),
    )
    if context["units"]["fluid_velocity_world_3"] != "m/s":
        _fail("context_provenance_invalid", "environment_context_oracle.units.fluid_velocity_world_3")
    if context["frames"]["fluid_velocity_world_3"] != "world":
        _fail("context_provenance_invalid", "environment_context_oracle.frames.fluid_velocity_world_3")
    return context


def _validate_estimated_context(
    value: Any, *, oracle: Mapping[str, Any]
) -> None:
    if value is oracle:
        _fail("oracle_as_estimate", "object_alias")
    context = _require_exact_mapping(
        value, ENVIRONMENT_CONTEXT_FIELDS, path="environment_context_estimated"
    )
    if context["available"] is False:
        expected_empty = {
            "method": "",
            "method_version": "",
            "source_kind": "unavailable",
            "source_signals": [],
            "values": {},
            "units": {},
            "frames": {},
            "value_provenance": {},
        }
        for field, expected in expected_empty.items():
            if context[field] != expected:
                _fail("context_unavailable_invalid", f"environment_context_estimated.{field}")
        return
    if context["available"] is not True:
        _fail("type_invalid", "environment_context_estimated.available")

    copied_namespaces = ("values", "units", "frames", "value_provenance")
    if all(context[field] == oracle[field] for field in copied_namespaces):
        _fail("oracle_as_estimate", "copied_oracle_payload")
    if context["source_kind"] != "deployable_observation":
        _fail("oracle_as_estimate", "source_kind")
    for field in ("method", "method_version"):
        value = context[field]
        if not isinstance(value, str) or not value.strip():
            _fail(
                "context_provenance_invalid",
                f"environment_context_estimated.{field}",
            )
    signals = context["source_signals"]
    if not isinstance(signals, list) or not signals or any(
        not isinstance(item, str) or not item for item in signals
    ):
        _fail("context_provenance_invalid", "environment_context_estimated.source_signals")
    values = context["values"]
    if not isinstance(values, Mapping) or not values:
        _fail("context_provenance_invalid", "environment_context_estimated.values")
    for key, nested in values.items():
        if not isinstance(key, str) or not key:
            _fail("context_provenance_invalid", "environment_context_estimated.values")
        _validate_finite_context_value(
            nested, path=f"environment_context_estimated.values.{key}"
        )
    _validate_metadata_maps(
        context,
        path="environment_context_estimated",
        expected_keys=set(values),
    )


def _validate_episode_provenance(
    value: Any, *, configuration: str
) -> Mapping[str, Any]:
    provenance = _require_exact_mapping(
        value, EPISODE_PROVENANCE_FIELDS, path="episode_provenance"
    )
    if provenance["configuration"] != configuration:
        _fail("topology_mismatch", "episode_provenance.configuration")
    for field in (
        "configuration",
        "scenario",
        "episode_id",
        "task_id",
        "controller_mode",
    ):
        _require_nonempty_string(provenance[field], path=f"episode_provenance.{field}")
    step_index = _require_int(
        provenance["step_index"], path="episode_provenance.step_index"
    )
    if step_index < 0:
        _fail("context_value_invalid", "episode_provenance.step_index")
    _require_int(provenance["seed"], path="episode_provenance.seed")
    simulation_time = _require_number(
        provenance["simulation_time_s"],
        path="episode_provenance.simulation_time_s",
    )
    if simulation_time < 0.0:
        _fail("context_value_invalid", "episode_provenance.simulation_time_s")
    _require_positive_number(
        provenance["control_dt_s"], path="episode_provenance.control_dt_s"
    )
    source_commit = provenance["source_commit"]
    if not isinstance(source_commit, str) or not _SOURCE_COMMIT_PATTERN.fullmatch(
        source_commit
    ):
        _fail("source_commit_invalid")
    if provenance["evidence_level"] not in {
        LOCAL_EVIDENCE_LEVEL,
        SERVER_EVIDENCE_LEVEL,
    }:
        _fail("evidence_level_invalid")
    return provenance


def validate_transition_v2(transition: Any) -> None:
    """Validate one schema-v2 transition without mutating caller-owned data."""
    payload = _require_exact_mapping(
        transition, TRANSITION_FIELDS, path="transition"
    )
    if payload["schema_version"] != KOOPMAN_TRANSITION_SCHEMA_V2:
        _fail("schema_version_mismatch")

    _require_vector(payload["state_11"], STATE_DIM, path="state_11")
    _require_vector(payload["reference_5"], REFERENCE_DIM, path="reference_5")
    _require_vector(
        payload["raw_action_4"],
        ACTION_DIM,
        path="raw_action_4",
        bounds=(-CONTROL_BOUND, CONTROL_BOUND),
    )
    virtual_control = _require_vector(
        payload["virtual_control_4"],
        ACTION_DIM,
        path="virtual_control_4",
        bounds=(-CONTROL_BOUND, CONTROL_BOUND),
    )
    pwm = _require_vector(
        payload["motor_pwm_padded_8"],
        PWM_PADDED_DIM,
        path="motor_pwm_padded_8",
        bounds=(-CONTROL_BOUND, CONTROL_BOUND),
        bounds_reason="pwm_out_of_bounds",
    )
    mask = payload["thruster_mask_8"]
    if isinstance(mask, (str, bytes)) or not isinstance(mask, Sequence):
        _fail("type_invalid", "thruster_mask_8")
    if len(mask) != PWM_PADDED_DIM:
        _fail("shape_invalid", "thruster_mask_8")
    if any(type(item) is not int for item in mask):
        _fail("type_invalid", "thruster_mask_8")
    if any(item not in (0, 1) for item in mask):
        _fail("mask_mismatch", "thruster_mask_8")
    _require_vector(
        payload["applied_wrench_6"], WRENCH_DIM, path="applied_wrench_6"
    )
    _require_vector(payload["next_state_11"], STATE_DIM, path="next_state_11")

    configuration, topology = _validate_platform_context(payload["platform_context"])
    expected_mask = [1] * topology["thruster_count"] + [0] * (
        PWM_PADDED_DIM - topology["thruster_count"]
    )
    if list(mask) != expected_mask:
        _fail("mask_mismatch", configuration)
    for index, enabled in enumerate(mask):
        if enabled == 0 and pwm[index] != 0.0:
            _fail("padding_nonzero", f"motor_pwm_padded_8[{index}]")
    if configuration.startswith("uuv4") and virtual_control[2] != 0.0:
        _fail("underactuated_yaw_nonzero", configuration)

    oracle = _validate_oracle_context(
        payload["environment_context_oracle"],
        thruster_count=topology["thruster_count"],
    )
    _validate_estimated_context(
        payload["environment_context_estimated"], oracle=oracle
    )
    _validate_episode_provenance(
        payload["episode_provenance"], configuration=configuration
    )


def build_local_transition_v2(**fields: Any) -> dict[str, Any]:
    """Return a fresh validated transition that can claim only local evidence."""
    transition = deepcopy(fields)
    validate_transition_v2(transition)
    provenance = transition["episode_provenance"]
    if provenance["evidence_level"] != LOCAL_EVIDENCE_LEVEL:
        _fail("local_evidence_required")
    return transition
