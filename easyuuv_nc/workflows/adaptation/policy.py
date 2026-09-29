# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""policy forward / L2 / RNG 状态 / 向量相关 / 张量转 list。

（由 adapt.py 拆分而来，函数体逐字节保真。）
"""

from __future__ import annotations

from typing import List

import numpy as np
import torch


def _policy_forward_eval(policy, normalized_obs):
    """Fast loop forward: detached, no grad."""
    with torch.no_grad():
        return policy.act_inference(normalized_obs)


def _policy_forward_train(policy, normalized_obs):
    """Slow loop forward: must keep computation graph alive for backward().

    rsl_rl 的 ``ActorCritic.actor`` 是普通 ``nn.Sequential``，最后一层是
    ``nn.Linear(hidden, num_actions)``，输出 shape 直接就是 (B, num_actions)，
    **不是** ``(mean, log_std)`` 的拼接（log_std 单独存在 ``policy.std``/
    ``policy.log_std`` 里）。之前按 2*action_dim 切片会把 (B,4) 误切成 (B,2)，
    导致下游 ``mse_tgt`` shape 不匹配，慢环 19 次全部 except 静默失败。
    """
    if hasattr(policy, "act_inference"):
        # act_inference 不包 no_grad，梯度可正常回传；与 policy.actor(obs) 等价。
        return policy.act_inference(normalized_obs)
    if hasattr(policy, "actor"):
        return policy.actor(normalized_obs)
    if hasattr(policy, "update_distribution"):
        policy.update_distribution(normalized_obs)
        return policy.distribution.loc
    raise RuntimeError("Cannot find a differentiable forward path on the policy.")


def _policy_param_l2(policy, anchor: dict[str, torch.Tensor]) -> float:
    """L2 distance from a frozen parameter snapshot."""
    total = torch.zeros((), device=next(policy.parameters()).device)
    with torch.no_grad():
        for name, param in policy.named_parameters():
            ref = anchor.get(name)
            if ref is None:
                continue
            total = total + ((param.detach() - ref.to(param.device)) ** 2).sum()
    return float(torch.sqrt(total).detach().cpu().item())


def _capture_torch_rng_state() -> tuple[torch.Tensor, list[torch.Tensor] | None]:
    cpu_state = torch.random.get_rng_state()
    cuda_state = torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None
    return cpu_state, cuda_state


def _restore_torch_rng_state(state: tuple[torch.Tensor, list[torch.Tensor] | None]) -> None:
    cpu_state, cuda_state = state
    torch.random.set_rng_state(cpu_state)
    if cuda_state is not None and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(cuda_state)


def _safe_vector_corr(a: List[float], b: List[float]) -> float:
    """Small-vector Pearson correlation with stable NaN behavior."""
    if len(a) != len(b) or len(a) < 2:
        return float("nan")
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if not np.all(np.isfinite(arr_a)) or not np.all(np.isfinite(arr_b)):
        return float("nan")
    if float(np.std(arr_a)) <= 1.0e-12 or float(np.std(arr_b)) <= 1.0e-12:
        return float("nan")
    return float(np.corrcoef(arr_a, arr_b)[0, 1])


def _tensor_1d_list(value: torch.Tensor) -> List[float]:
    """Return env-0 tensor values as a flat Python list for CSV diagnostics."""
    row = value[0] if value.ndim > 1 else value
    return [float(x) for x in row.detach().cpu().reshape(-1).tolist()]

