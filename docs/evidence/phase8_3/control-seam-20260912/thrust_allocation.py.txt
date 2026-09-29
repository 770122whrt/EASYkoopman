"""Pure Torch thrust-allocation helpers shared by runtime and qualification."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional

import torch


CONTROL_CHANNEL_NAMES = ("roll", "pitch", "yaw", "depth")
_CHANNEL_TO_WRENCH_ROW = {"roll": 3, "pitch": 4, "yaw": 5, "depth": 2}
_CONTROL_CHANNEL_TO_DOF = {"roll": "roll", "pitch": "pitch", "yaw": "yaw", "depth": "heave"}

# The received eight-motor PID mixing matrix, with rows ordered by motor and
# columns ordered [roll, pitch, yaw, depth].
LEGACY_CONTROL_TO_MOTOR = torch.tensor(
    [
        [-1.0, -1.0, 0.0, 1.0],
        [1.0, -1.0, 0.0, 1.0],
        [-1.0, 1.0, 0.0, 1.0],
        [1.0, 1.0, 0.0, 1.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ],
    dtype=torch.float32,
)


def quat_apply(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    """Rotate ``vec`` by a ``(w, x, y, z)`` quaternion."""
    quat = torch.as_tensor(quat, dtype=torch.float32)
    vec = torch.as_tensor(vec, dtype=torch.float32)
    w = quat[..., 0:1]
    xyz = quat[..., 1:4]
    t = 2.0 * torch.cross(xyz, vec, dim=-1)
    return vec + w * t + torch.cross(xyz, t, dim=-1)


def quat_from_rpy(roll: float, pitch: float, yaw: float) -> torch.Tensor:
    """Convert roll, pitch, yaw radians to a ``(w, x, y, z)`` quaternion."""
    cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    return torch.tensor(
        [
            cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
        ],
        dtype=torch.float32,
    )


@dataclass
class ThrusterLayout:
    """Geometry of one vehicle's thruster set."""

    positions: torch.Tensor
    orientations: torch.Tensor
    num_thrusters: int

    def __post_init__(self) -> None:
        self.positions = torch.as_tensor(self.positions, dtype=torch.float32)
        self.orientations = torch.as_tensor(self.orientations, dtype=torch.float32)
        if self.positions.shape != (self.num_thrusters, 3):
            raise ValueError(f"positions must be ({self.num_thrusters}, 3), got {tuple(self.positions.shape)}")
        if self.orientations.shape != (self.num_thrusters, 4):
            raise ValueError(f"orientations must be ({self.num_thrusters}, 4), got {tuple(self.orientations.shape)}")

    @classmethod
    def from_specs(cls, specs: Sequence[Sequence[float]]) -> "ThrusterLayout":
        """Build a layout from ``[x, y, z, roll, pitch, yaw]`` specification rows."""
        positions = []
        orientations = []
        for row in specs:
            x, y, z, roll, pitch, yaw = row
            positions.append([float(x), float(y), float(z)])
            orientations.append(quat_from_rpy(float(roll), float(pitch), float(yaw)))
        count = len(specs)
        return cls(
            positions=torch.tensor(positions, dtype=torch.float32),
            orientations=torch.stack(orientations, dim=0) if orientations else torch.zeros((0, 4)),
            num_thrusters=count,
        )


def build_wrench_matrix(layout: ThrusterLayout) -> torch.Tensor:
    """Build the 6xN matrix mapping thruster magnitudes to body wrench."""
    xhat = torch.tensor([1.0, 0.0, 0.0], dtype=torch.float32).expand(layout.num_thrusters, 3)
    force = quat_apply(layout.orientations, xhat)
    torque = torch.cross(layout.positions, force, dim=-1)
    matrix = torch.zeros((6, layout.num_thrusters), dtype=torch.float32)
    matrix[0:3, :] = force.transpose(0, 1)
    matrix[3:6, :] = torque.transpose(0, 1)
    return matrix


def control_channels_to_wrench(cmd: torch.Tensor) -> torch.Tensor:
    """Map ``[roll, pitch, yaw, depth]`` control to a six-axis body wrench."""
    cmd = torch.as_tensor(cmd, dtype=torch.float32)
    wrench = torch.zeros(cmd.shape[:-1] + (6,), dtype=torch.float32, device=cmd.device)
    for channel_index, name in enumerate(CONTROL_CHANNEL_NAMES):
        wrench[..., _CHANNEL_TO_WRENCH_ROW[name]] = cmd[..., channel_index]
    return wrench


def dof_weight_vector(controllable_dofs: Optional[Sequence[str]]) -> torch.Tensor:
    """Return the six-axis allocation weight vector for declared controllability."""
    axis_row = {"surge": 0, "sway": 1, "heave": 2, "roll": 3, "pitch": 4, "yaw": 5}
    if controllable_dofs is None:
        return torch.ones(6, dtype=torch.float32)
    weight = torch.zeros(6, dtype=torch.float32)
    for name in controllable_dofs:
        if name not in axis_row:
            raise ValueError(f"unknown DOF name {name!r}; expected one of {list(axis_row)}")
        weight[axis_row[name]] = 1.0
    return weight


def allocate(
    B: torch.Tensor,
    wrench_cmd: torch.Tensor,
    mode: str = "pinv",
    weight: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    """Allocate a desired six-axis wrench to thruster magnitudes."""
    B = torch.as_tensor(B, dtype=torch.float32)
    wrench_cmd = torch.as_tensor(wrench_cmd, dtype=torch.float32)
    if mode == "pinv":
        matrix = B
        target = wrench_cmd
    elif mode == "wls":
        weights = torch.ones(6, dtype=torch.float32) if weight is None else torch.as_tensor(weight, dtype=torch.float32)
        matrix = weights.unsqueeze(-1) * B
        target = wrench_cmd * weights
    else:
        raise ValueError(f"unknown allocate mode {mode!r}; expected 'pinv' or 'wls'")
    return torch.einsum("nk,...k->...n", torch.linalg.pinv(matrix), target)


def declared_control_rank(config: Mapping[str, Any]) -> int:
    """Return the rank of the configuration's declared four-channel control map."""
    allocation = config.get("thrust_allocation")
    if allocation is None:
        return int(torch.linalg.matrix_rank(LEGACY_CONTROL_TO_MOTOR).item())

    layout = ThrusterLayout.from_specs(allocation["specs"])
    active_channels = [
        index
        for index, name in enumerate(CONTROL_CHANNEL_NAMES)
        if _CONTROL_CHANNEL_TO_DOF[name] in set(allocation["controllable_dofs"])
    ]
    wrench_rows = [_CHANNEL_TO_WRENCH_ROW[CONTROL_CHANNEL_NAMES[index]] for index in active_channels]
    active_mapping = build_wrench_matrix(layout)[wrench_rows, :]
    return int(torch.linalg.matrix_rank(active_mapping).item())
