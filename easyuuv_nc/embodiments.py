"""Canonical, Isaac-free EasyUUV embodiment configuration catalog."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CONTROL_CHANNELS = ("roll", "pitch", "yaw", "depth")
"""Qualification channel order shared by all public configurations."""

SUPPORTED_EMBODIMENTS = (
    "base",
    "long_body",
    "heavy_moderate",
    "asymmetric",
    "uuv6",
    "uuv6_angled",
    "uuv4",
    "uuv4_angled",
)
"""Public configuration names accepted by the train and adapt CLIs."""

INTERNAL_EMBODIMENTS = ("heavy_duty",)
"""Preset names intentionally excluded from public CLI selection."""

DECLARED_CONTROL_RANKS = {
    "base": 4,
    "long_body": 4,
    "heavy_duty": 4,
    "heavy_moderate": 4,
    "asymmetric": 4,
    "uuv6": 4,
    "uuv6_angled": 4,
    "uuv4": 3,
    "uuv4_angled": 3,
}
"""Static topology contract, cross-checked against Torch allocation tests."""


EMBODIMENT_CONFIGS: dict[str, dict[str, Any]] = {
    "base": {
        "mass": 2.2701e01,
        "inertia_tensors": [0.37, 0.97, 1.19],
        "com_to_cob_offset": [0.0, 0.0, 0.01],
        "dyn_time_constant": 0.05,
        "drag_multiplier": 1.0,
    },
    "long_body": {
        "mass": 2.2701e01,
        "inertia_tensors": [0.1, 2.5, 2.5],
        "com_to_cob_offset": [0.0, 0.0, 0.01],
        "dyn_time_constant": 0.05,
        "drag_multiplier": 1.0,
        "thruster_com_offset_scale": 1.2,
    },
    "heavy_duty": {
        "mass": 2.2701e01 * 5,
        "inertia_tensors": [0.37 * 5, 0.97 * 5, 1.19 * 5],
        "com_to_cob_offset": [0.0, 0.0, 0.01],
        "dyn_time_constant": 0.2,
        "drag_multiplier": 5.0,
    },
    "heavy_moderate": {
        "mass": 2.2701e01 * 2,
        "inertia_tensors": [0.37 * 2, 0.97 * 2, 1.19 * 2],
        "com_to_cob_offset": [0.0, 0.0, 0.01],
        "dyn_time_constant": 0.1,
        "drag_multiplier": 2.0,
    },
    "asymmetric": {
        "mass": 2.2701e01,
        "inertia_tensors": [0.37, 0.97, 1.19],
        "com_to_cob_offset": [0.05, 0.05, 0.01],
        "dyn_time_constant": 0.05,
        "drag_multiplier": 1.0,
    },
    "uuv6": {
        "mass": 29.7,
        "inertia_tensors": [0.37 * 29.7 / 22.701, 0.97 * 29.7 / 22.701, 1.19 * 29.7 / 22.701],
        "com_to_cob_offset": [0.0, 0.0, 0.01],
        "dyn_time_constant": 0.05,
        "drag_multiplier": 1.0,
        "volume": 0.03,
        "thrust_allocation": {
            "mode": "pinv",
            "controllable_dofs": ["heave", "roll", "pitch", "yaw"],
            "specs": [
                [0.129, 0.21, 0.03, 0.0, -1.5708, 0.0],
                [0.129, -0.21, 0.03, 0.0, -1.5708, 0.0],
                [-0.129, 0.21, 0.03, 0.0, -1.5708, 0.0],
                [-0.129, -0.21, 0.03, 0.0, -1.5708, 0.0],
                [0.0, 0.16125, -0.02, 0.0, 0.0, 0.0],
                [0.0, -0.16125, -0.02, 0.0, 0.0, 0.0],
            ],
        },
    },
    "uuv4": {
        "mass": 21.78,
        "inertia_tensors": [0.37 * 21.78 / 22.701, 0.97 * 21.78 / 22.701, 1.19 * 21.78 / 22.701],
        "com_to_cob_offset": [0.0, 0.0, 0.01],
        "dyn_time_constant": 0.05,
        "drag_multiplier": 1.0,
        "volume": 0.022,
        "thrust_allocation": {
            "mode": "wls",
            "controllable_dofs": ["heave", "roll", "pitch"],
            "specs": [
                [0.129, 0.21, 0.03, 0.0, -1.5708, 0.0],
                [0.129, -0.21, 0.03, 0.0, -1.5708, 0.0],
                [-0.129, 0.21, 0.03, 0.0, -1.5708, 0.0],
                [-0.129, -0.21, 0.03, 0.0, -1.5708, 0.0],
            ],
        },
    },
    "uuv6_angled": {
        "mass": 31.68,
        "inertia_tensors": [0.37 * 31.68 / 22.701, 0.97 * 31.68 / 22.701, 1.19 * 31.68 / 22.701],
        "com_to_cob_offset": [0.0, 0.0, 0.01],
        "dyn_time_constant": 0.05,
        "drag_multiplier": 1.0,
        "volume": 0.032,
        "thrust_allocation": {
            "mode": "pinv",
            "controllable_dofs": ["heave", "roll", "pitch", "yaw"],
            "specs": [
                [0.129, 0.21, 0.03, 0.139626, -1.5708, 0.0],
                [0.129, -0.21, 0.03, -0.139626, -1.5708, 0.0],
                [-0.129, 0.21, 0.03, 0.139626, -1.5708, 0.0],
                [-0.129, -0.21, 0.03, -0.139626, -1.5708, 0.0],
                [0.0, 0.16125, -0.02, 0.0, 0.174533, 0.0],
                [0.0, -0.16125, -0.02, 0.0, 0.174533, 0.0],
            ],
        },
    },
    "uuv4_angled": {
        "mass": 23.76,
        "inertia_tensors": [0.37 * 23.76 / 22.701, 0.97 * 23.76 / 22.701, 1.19 * 23.76 / 22.701],
        "com_to_cob_offset": [0.0, 0.0, 0.01],
        "dyn_time_constant": 0.05,
        "drag_multiplier": 1.0,
        "volume": 0.024,
        "thrust_allocation": {
            "mode": "wls",
            "controllable_dofs": ["heave", "roll", "pitch"],
            "specs": [
                [0.129, 0.21, 0.03, 0.139626, -1.5708, 0.0],
                [0.129, -0.21, 0.03, -0.139626, -1.5708, 0.0],
                [-0.129, 0.21, 0.03, 0.139626, -1.5708, 0.0],
                [-0.129, -0.21, 0.03, -0.139626, -1.5708, 0.0],
            ],
        },
    },
}
"""All received configuration payloads, including the internal preset."""


def qualification_record(name: str) -> dict[str, Any]:
    """Return a fresh, immutable-by-reference qualification record for ``name``.

    The returned dictionary and its tuple values never expose mutable internals of
    :data:`EMBODIMENT_CONFIGS`.
    """
    if name not in EMBODIMENT_CONFIGS:
        raise KeyError(name)

    config: Mapping[str, Any] = EMBODIMENT_CONFIGS[name]
    allocation = config.get("thrust_allocation")
    if allocation is None:
        control_mask = (1, 1, 1, 1)
        thruster_count = 8
        allocation_mode = "legacy"
    else:
        controllable_dofs = set(allocation["controllable_dofs"])
        control_mask = tuple(
            int(dof in controllable_dofs)
            for dof in ("roll", "pitch", "yaw", "heave")
        )
        thruster_count = len(allocation["specs"])
        allocation_mode = str(allocation["mode"])

    return {
        "configuration": str(name),
        "public": name in SUPPORTED_EMBODIMENTS,
        "thruster_count": int(thruster_count),
        "allocation_mode": allocation_mode,
        "control_channels": tuple(CONTROL_CHANNELS),
        "control_mask": tuple(control_mask),
        "declared_control_rank": DECLARED_CONTROL_RANKS[name],
    }
