"""
Thruster dynamics and model for EasyUUV

Author: Ethan Fahnestock
"""
# based on https://github.com/uuvsimulator/uuv_simulator/blob/master/uuv_gazebo_plugins/uuv_gazebo_plugins/src/Dynamics.cc

from isaaclab_compat import quat_from_euler_xyz
from dataclasses import dataclass
from abc import ABC, abstractmethod
import numpy as np 
import torch

def get_thruster_com_and_orientations(device):
  """
  todo: this entire function should be handled by the USD/URDF model and Configuration files, with named actuators
  This function retrieves the thruster extrinsics for a single vehicle
  """
  def create_tf_rpy(x,y,z,rr,rp,ry):
    print(rr,rp,ry)
    shift = torch.Tensor([x, y, z])
    r = quat_from_euler_xyz(torch.Tensor([rr]), torch.Tensor([rp]), torch.Tensor([ry]))[0]
    print(rr, rp, ry, r[0], r[1], r[2], r[3])
    return shift, r

  def create_tf_quat(x,y,z,w,vx,vy,vz):
    shift = torch.Tensor([x, y, z])
    r = torch.Tensor([w, vx, vy, vz])
    return shift, r
  
  def create_tf_rpyquat(x, y, z, roll, pitch, yaw):
    # 欧拉角转换为四元数（简化版）
    roll = torch.as_tensor(roll)
    pitch = torch.as_tensor(pitch)
    yaw = torch.as_tensor(yaw)
    cy = torch.cos(yaw * 0.5)
    sy = torch.sin(yaw * 0.5)
    cp = torch.cos(pitch * 0.5)
    sp = torch.sin(pitch * 0.5)
    cr = torch.cos(roll * 0.5)
    sr = torch.sin(roll * 0.5)

    w = cr * cp * cy + sr * sp * sy
    vx = sr * cp * cy - cr * sp * sy
    vy = cr * sp * cy + sr * cp * sy
    vz = cr * cp * sy - sr * sp * cy

    return create_tf_quat(x, y, z, w, vx, vy, vz)

  # TODO: think about the format of this, get rid of helper functions
  # AUV尺寸（单位：米）
  length = 0.56  # x轴方向
  width = 0.43   # y轴方向
  height = 0.24  # z轴方向


  # 实际使用版本
  thruster_info = {
      # 前四个用于深度的推进器
      "front_left_vertical": create_tf_rpyquat( # 左前，x,y均为正
          x = width * 0.3,
          y = length * 0.375,
          z = 0.03,
          roll = 0,
          pitch = -1.5708,
          yaw = 0
      ),
      "front_right_vertical": create_tf_rpyquat( # 右前，x为正，y为负
          x = width * 0.3,
          y = -length * 0.375,
          z = 0.03,
          roll = 0,
          pitch = -1.5708,
          yaw = 0
      ),
      "rear_left_vertical": create_tf_rpyquat( # 左后，x为负，y为正
          x = -width * 0.3,
          y = length * 0.375,
          z = 0.03,
          roll = 0,
          pitch = -1.5708,
          yaw = 0
      ),
      "rear_right_vertical": create_tf_rpyquat( # 右后，x,y均为负
          x = -width * 0.3,
          y = -length * 0.375,
          z = 0.03,
          roll = 0,
          pitch = -1.5708,
          yaw = 0
      ),
      "front_left_horizontal": create_tf_rpyquat(# 左前，x,y均为正
          x = width * 0.2,
          y = length * 0.2,
          z = -0.02,
          roll = 0,
          pitch = 0,
          yaw = -0.785398 # -45deg
      ),
      "front_right_horizontal": create_tf_rpyquat(# 右前，x为正，y为负
          x = width * 0.2,
          y = -length * 0.2,
          z = -0.02,
          roll = 0,
          pitch = 0,
          yaw = 0.785398 # 45deg
      ),
      "rear_left_horizontal": create_tf_rpyquat(# 左后，x为负，y为正
          x = -width * 0.2,
          y = length * 0.2,
          z = -0.02,
          roll = 0,
          pitch = 0,
          yaw = -2.356194 # -135deg
      ),
      "rear_right_horizontal": create_tf_rpyquat(# 右后，x为正，y为正
          x = -width * 0.2,
          y = -length * 0.2,
          z = -0.02,
          roll = 0,
          pitch = 0,
          yaw = 2.356194 # 135deg
      )
  }
  # vector pointing from com->thruster location (thruster, 3)
  # THRUSTER ORDERING IS 

  # new THRUSTER ORDERING IS 
  # 0 - front_left_vertical
  # 1 - front_right_vertical
  # 2 - rear_left_vertical
  # 3 - rear_right_vertical
  # 4 - front_left_horizontal
  # 5 - front_right_horizontal
  # 6 - rear_left_horizontal
  # 7 - rear_right_horizontal

  # 根据情况替代上面一行
  thruster_com_offsets = torch.tensor([
    [thruster_info["front_left_vertical"][0][0], thruster_info["front_left_vertical"][0][1], thruster_info["front_left_vertical"][0][2]],
    [thruster_info["front_right_vertical"][0][0], thruster_info["front_right_vertical"][0][1], thruster_info["front_right_vertical"][0][2]],
    [thruster_info["rear_left_vertical"][0][0], thruster_info["rear_left_vertical"][0][1], thruster_info["rear_left_vertical"][0][2]],
    [thruster_info["rear_right_vertical"][0][0], thruster_info["rear_right_vertical"][0][1], thruster_info["rear_right_vertical"][0][2]],
    [thruster_info["front_left_horizontal"][0][0], thruster_info["front_left_horizontal"][0][1], thruster_info["front_left_horizontal"][0][2]],
    [thruster_info["front_right_horizontal"][0][0], thruster_info["front_right_horizontal"][0][1], thruster_info["front_right_horizontal"][0][2]],
    [thruster_info["rear_left_horizontal"][0][0], thruster_info["rear_left_horizontal"][0][1], thruster_info["rear_left_horizontal"][0][2]],
    [thruster_info["rear_right_horizontal"][0][0], thruster_info["rear_right_horizontal"][0][1], thruster_info["rear_right_horizontal"][0][2]]
  ])

  # quaternions to go from COM frame to thruster frame (thruster, 4)

  # 替代上面一行
  thruster_quats = torch.tensor([
    [thruster_info["front_left_vertical"][1][0], thruster_info["front_left_vertical"][1][1], thruster_info["front_left_vertical"][1][2], thruster_info["front_left_vertical"][1][3]],
    [thruster_info["front_right_vertical"][1][0], thruster_info["front_right_vertical"][1][1], thruster_info["front_right_vertical"][1][2], thruster_info["front_right_vertical"][1][3]],
    [thruster_info["rear_left_vertical"][1][0], thruster_info["rear_left_vertical"][1][1], thruster_info["rear_left_vertical"][1][2], thruster_info["rear_left_vertical"][1][3]],
    [thruster_info["rear_right_vertical"][1][0], thruster_info["rear_right_vertical"][1][1], thruster_info["rear_right_vertical"][1][2], thruster_info["rear_right_vertical"][1][3]],
    [thruster_info["front_left_horizontal"][1][0], thruster_info["front_left_horizontal"][1][1], thruster_info["front_left_horizontal"][1][2], thruster_info["front_left_horizontal"][1][3]],
    [thruster_info["front_right_horizontal"][1][0], thruster_info["front_right_horizontal"][1][1], thruster_info["front_right_horizontal"][1][2], thruster_info["front_right_horizontal"][1][3]],
    [thruster_info["rear_left_horizontal"][1][0], thruster_info["rear_left_horizontal"][1][1], thruster_info["rear_left_horizontal"][1][2], thruster_info["rear_left_horizontal"][1][3]],
    [thruster_info["rear_right_horizontal"][1][0], thruster_info["rear_right_horizontal"][1][1], thruster_info["rear_right_horizontal"][1][2], thruster_info["rear_right_horizontal"][1][3]]
  ])

  return thruster_com_offsets, thruster_quats


class Dynamics(ABC):

  def __init__(self, numEnvs:int, num_thrusters_per_env:int, device:torch.device) -> None: 
    if numEnvs <= 0:
      raise ValueError("numEnvs must be strictly positive.")
    if num_thrusters_per_env <= 0:
      raise ValueError("num_thrusters_per_env must be strictly positive.")
    self.numEnvs = numEnvs
    self.num_thrusters_per_env = num_thrusters_per_env
    self.device = torch.device(device)
    self.reset_all()

  def _normalize_env_ids(self, env_ids) -> torch.Tensor:
    raw = torch.as_tensor(env_ids, device=self.device)
    if raw.numel() == 0:
      return torch.empty(0, dtype=torch.long, device=self.device)
    if raw.dtype == torch.bool:
      if raw.shape != (self.numEnvs,):
        raise ValueError(
          f"Boolean environment mask must have shape ({self.numEnvs},), got {tuple(raw.shape)}."
        )
      normalized = torch.nonzero(raw, as_tuple=False).reshape(-1)
    else:
      if raw.dtype.is_floating_point or raw.dtype.is_complex:
        raise ValueError("Environment ids must be integer indices or a boolean mask.")
      normalized = raw.to(dtype=torch.long).reshape(-1)
    if torch.any(normalized < 0) or torch.any(normalized >= self.numEnvs):
      raise IndexError(f"Environment ids must be in [0, {self.numEnvs}).")
    return normalized

  # env_ids may be integer indices or a boolean mask of length numEnvs.
  def reset(self, env_ids):
    env_ids_t = self._normalize_env_ids(env_ids)
    if env_ids_t.numel() == 0:
      return
    self.state[env_ids_t, :] = 0.0
    self.prevTime[env_ids_t] = 0.0

  def reset_all(self):
    self.state = torch.zeros((self.numEnvs, self.num_thrusters_per_env), dtype=torch.float32, device=self.device, requires_grad=False)
    self.prevTime = torch.zeros((self.numEnvs), dtype=torch.float32, device=self.device, requires_grad=False)

  @abstractmethod
  def update(self, cmd:torch.Tensor, t:torch.Tensor) -> torch.Tensor:
    pass

class DynamicsFirstOrder(Dynamics):

  def __init__(self, numEnvs:int, num_thrusters_per_env:int, tau:float, device:torch.device):
    super().__init__(numEnvs=numEnvs, num_thrusters_per_env=num_thrusters_per_env, device=device)
    self.tau = torch.full((self.numEnvs,), float(tau), dtype=torch.float32, device=self.device)
    self._validate_time_constants(self.tau)

  @staticmethod
  def _validate_time_constants(tau:torch.Tensor) -> None:
    if not torch.all(torch.isfinite(tau)) or not torch.all(tau > 0.0):
      raise ValueError("Thruster time constants must be finite and strictly positive.")

  def set_time_constants(self, env_ids, tau_values) -> None:
    env_ids_t = self._normalize_env_ids(env_ids)
    if env_ids_t.numel() == 0:
      return

    tau_tensor = torch.as_tensor(tau_values, device=self.device, dtype=torch.float32).reshape(-1)
    if tau_tensor.numel() == 1:
      tau_tensor = tau_tensor.repeat(env_ids_t.numel())
    elif tau_tensor.numel() != env_ids_t.numel():
      raise ValueError(
        f"Expected {env_ids_t.numel()} time constants for the selected environments, got {tau_tensor.numel()}."
      )
    self._validate_time_constants(tau_tensor)
    self.tau[env_ids_t] = tau_tensor

  # cmd: torch.tensor of shape (numEnvs, num_thrusters_per_env) 
  # t: torch.tensor of shape (numEnvs) with the current times 
  # given force commands, update the state of system and report current thrusts 
  def update(self, cmd:torch.Tensor, t:torch.Tensor) -> torch.Tensor:
    expected_cmd_shape = (self.numEnvs, self.num_thrusters_per_env)
    if not isinstance(cmd, torch.Tensor) or tuple(cmd.shape) != expected_cmd_shape:
      actual_shape = tuple(cmd.shape) if isinstance(cmd, torch.Tensor) else None
      raise ValueError(f"cmd must have shape {expected_cmd_shape}, got {actual_shape}.")
    if cmd.device != self.state.device:
      raise ValueError(f"cmd must use device {self.state.device}, got {cmd.device}.")
    if cmd.dtype != self.state.dtype:
      raise ValueError(f"cmd must use dtype {self.state.dtype}, got {cmd.dtype}.")
    if not torch.all(torch.isfinite(cmd)):
      raise ValueError("cmd must contain only finite values.")

    expected_time_shape = (self.numEnvs,)
    if not isinstance(t, torch.Tensor) or tuple(t.shape) != expected_time_shape:
      actual_shape = tuple(t.shape) if isinstance(t, torch.Tensor) else None
      raise ValueError(f"t must have shape {expected_time_shape}, got {actual_shape}.")
    if t.device != self.prevTime.device:
      raise ValueError(f"t must use device {self.prevTime.device}, got {t.device}.")
    if t.dtype != self.prevTime.dtype:
      raise ValueError(f"t must use dtype {self.prevTime.dtype}, got {t.dtype}.")
    if not torch.all(torch.isfinite(t)):
      raise ValueError("t must contain only finite values.")

    if torch.any(t < self.prevTime):
      raise ValueError("t must be monotonic for every environment.")

    dt = t - self.prevTime
    alpha = torch.exp(-dt / self.tau)
    next_state = self.state * alpha.unsqueeze(-1) + (1.0 - alpha).unsqueeze(-1) * cmd
    if not torch.all(torch.isfinite(next_state)):
      raise RuntimeError("First-order thruster update produced non-finite actuator state.")

    self.state.copy_(next_state)
    self.prevTime.copy_(t)
    return self.state

# based on https://github.com/uuvsimulator/uuv_simulator/blob/master/uuv_gazebo_plugins/uuv_gazebo_plugins/src/ThrusterConversionFcn.cc
@dataclass
class ConversionFunction(ABC):

  @abstractmethod
  def convert(self, cmd:np.ndarray) -> float:
    pass

class ConversionFunctionBasic(ConversionFunction):

  # rotorConstant: the rotor constant  
  rotorConstant: float

  def __init__(self, rotorConstant:float):
    super().__init__()
    self.rotorConstant = rotorConstant

  # cmd: np.ndarray of shape (numEnvs, num_thrusters_per_env)
  # converts velocity commands to thrust 
  def convert(self, cmd:torch.tensor) -> float:
    return self.rotorConstant * torch.abs(cmd) * cmd 
  
