"""STDW-style on-policy fine-tuning workflow for EasyUUV (v3 plan).

Replaces ``workflows/play_stdw_adapt.py`` (the legacy teacher-student
distillation pipeline) with a true STDW-style gradual domain adaptation loop:

- A ``EasyUUVStdwWrapper`` drives a linear ``com_to_cob_offset`` drift on
  selectable axes between ``drift_start_step`` and ``drift_end_step`` and
  performs a 5s rolling RMS low-pass on a compound tracking error signal.
- A ``StdwReplayBuffer`` collects (s, a, a_pseudo, r, s', error, mask, V, tag,
  step) tuples and exposes a ``sample_pair`` API for STDW source/target batch
  matching.
- The loaded ``actor_critic`` is fine-tuned in-place (no teacher/student
  duplication) with the STDW loss
  ``(1-rho) * L_src + rho * L_tgt + lambda_reg * ||theta - theta_pre||^2``.
- ``rho`` is synchronised with the drift fraction.
- A Lyapunov ``V_t = 0.5*e^T P e`` "physical sieve" mask filters the per-sample
  loss so that only energy-decreasing samples produce gradients.

The workflow remains compatible with ``custom_workflows/run_with_isaac_env.sh``
and ``experiment_runner.py``.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import shutil
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gymnasium as gym
import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
import torch


# ---------------------------------------------------------------------------
# 路径引导：让 ``import easyuuv_nc`` 可解析（父目录入 sys.path）。
# 干净包名重构：不再需要 legacy ``_bootstrap_local_lab_tasks_package()`` hack，
# 因为 easyuuv_nc 用普通模块 entry_point ``easyuuv_nc.env:EasyUUVEnv``，
# ``import easyuuv_nc`` 即触发 gym.register。
# ---------------------------------------------------------------------------

WORKFLOW_DIR = Path(__file__).resolve().parent          # .../easyuuv_nc/workflows
EASYUUV_NC_DIR = WORKFLOW_DIR.parent                    # .../easyuuv_nc
REPO_ROOT = EASYUUV_NC_DIR                              # 兼容旧变量名（指向 easyuuv_nc 包根）
PARENT_OF_NC = EASYUUV_NC_DIR.parent                    # .../easyuuv_stdw (or sibling after move)
if str(PARENT_OF_NC) not in sys.path:
    sys.path.insert(0, str(PARENT_OF_NC))
if str(EASYUUV_NC_DIR) not in sys.path:
    sys.path.insert(0, str(EASYUUV_NC_DIR))

from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS  # noqa: E402

from easyuuv_nc.stdw_integration.metrics import (  # noqa: E402
    DEFAULT_DEPTH_LOWER_LIMIT,
    DEFAULT_DEPTH_REFERENCE_FRAME,
    DEFAULT_DEPTH_SURFACE_Z,
    DEFAULT_DEPTH_TRANSITION_WIDTH,
    DEFAULT_DEPTH_UPPER_LIMIT,
)

# ---------------------------------------------------------------------------
# 拆分重构：全部独立 helper 迁至 ``easyuuv_nc.workflows.adaptation`` 包。
# 该包 omni-free，可在 AppLauncher 之前 import（``_bool_arg`` 等被 argparse 使用）。
# adapt.py 现退化为薄入口：仅保留 argparse/AppLauncher 编排 + main()。
# ---------------------------------------------------------------------------
from easyuuv_nc.workflows.adaptation import (  # noqa: E402,F401
    PHASE56_RUNTIME_FEATURE_SETS,
    PHASE56_RUNTIME_HARD_THRESHOLDS,
    PHASE56_RUNTIME_SOFT_THRESHOLDS,
    _analytic_s_surface_action,
    _apply_action_bridge_residual_write,
    _apply_analytic_action_shim,
    _apply_deployed_action_bridge_residual,
    _apply_deployed_reduced_action_anchor,
    _apply_runtime_zeta4_update,
    _apply_task_a_depth_failsafe_shim,
    _apply_zeta4_surrogate,
    _bool_arg,
    _bounded_multiplier_to_delta,
    _build_pseudo_action_target,
    _capture_torch_rng_state,
    _direction_gate_correction_direction,
    _effective_zeta4_multipliers,
    _enforce_zeta_depth_floor_,
    _get_desired_pose,
    _get_true_pose,
    _parse_axes,
    _parse_channel_indices,
    _parse_p_diag,
    _parse_zeta_grad_mask,
    _phase4a_anchor_contract,
    _phase4a_empty_anchor_contract,
    _phase56_curvature_relative_defaults,
    _phase56_curvature_relative_row,
    _phase56_curvature_relative_summary,
    _phase56_flow_cfg,
    _phase56_prepare_live_bundle,
    _phase56_runtime_execution_directives,
    _phase56_runtime_feature_vector,
    _phase56_runtime_live_contract,
    _phase56_runtime_monitor_defaults,
    _phase56_runtime_state_step,
    _phase56_standardize,
    _phase8_fm_midpoint_state_anchor,
    _policy_forward_eval,
    _policy_forward_train,
    _policy_param_l2,
    _quat_conjugate,
    _quat_mul,
    _read_initial_cob_xy,
    _read_jacobian_inv_diag,
    _read_low_level_correction,
    _reset_wrapper_env,
    _resolve_drift_router,
    _restore_torch_rng_state,
    _runtime_control_snapshot,
    _runtime_reference_context,
    _safe_vector_corr,
    _save_stdw_checkpoint,
    _set_initial_disturbance,
    _tensor_1d_list,
    _tracking_error_direction,
    _zeta4_multipliers,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


parser = argparse.ArgumentParser(description="STDW online adaptation for EasyUUV (v3).")
parser.add_argument("--cpu", action="store_true", default=False)
parser.add_argument("--disable_fabric", action="store_true", default=False)
parser.add_argument("--num_envs", type=int, default=1)
parser.add_argument("--task", type=str, default="EasyUUV-Direct-v1")
parser.add_argument("--seed", type=int, default=None)
parser.add_argument("--total_steps", type=int, default=1400)
parser.add_argument(
    "--deterministic_reference",
    type=_bool_arg,
    default=False,
    help="Decouple the desired/reference trajectory from the global RNG so STDW "
    "on/off share an identical reference under the same seed (for fair overlay).",
)
parser.add_argument(
    "--ground_plane_mode",
    type=str,
    choices=["grid", "local_cuboid"],
    default="grid",
    help="Scene ground source. grid preserves the historic Isaac remote USD; "
    "local_cuboid provides an explicit offline z=0 fallback.",
)

# STDW gates
parser.add_argument("--use_stdw", type=_bool_arg, default=True)
parser.add_argument("--enable_filter", type=_bool_arg, default=True)
parser.add_argument("--use_quantile_filter", type=_bool_arg, default=True)
parser.add_argument("--discard_ratio", type=float, default=0.1)
parser.add_argument("--enable_pseudo_action", type=_bool_arg, default=True)
parser.add_argument("--pseudo_gain", type=float, default=1.0)
# 改良 2：伪标签饱和门控与自适应衰减
# - pseudo_gate_limit：clip(pseudo_gain * J^-1 Δu, -a_limit, +a_limit)，
#   防止 PID 积分饱和反哺出过激动作（默认 0.5，范围 [0,1]）。
# - pseudo_decay：pseudo_gain(ρ) = pseudo_gain_0 * (1 - pseudo_decay * ρ)，
#   随 drift_frac 增大让策略自己接管控制（建议 0.7）。
parser.add_argument("--pseudo_gate_limit", type=float, default=0.5)
parser.add_argument("--pseudo_decay", type=float, default=0.7)
# Fix A (DIAG_stdw_pseudo_label_mechanism_20260707): switch _pid_value_add_buf from
# the action-copy formula to an error-driven one. Default False keeps disk-byte
# identity to the pre-Fix-A pipeline.
parser.add_argument("--pseudo_error_driven", type=_bool_arg, default=False)
parser.add_argument("--pseudo_error_gain", type=float, default=3.0)
parser.add_argument(
    "--pseudo_action_target_mode",
    type=str,
    default="legacy_delta",
    choices=["legacy_delta", "analytic_blend", "analytic_residual", "analytic_residual_error_gate"],
    help="How to build B_tgt['pseudo_actions']. legacy_delta keeps the historic "
         "action + correction path. analytic_blend replaces the target with a "
         "convex blend toward an analytic S-surface action derived from the same observation. "
         "analytic_residual adds a clipped residual toward that analytic action. "
         "analytic_residual_error_gate applies that residual only when the runtime error signal exceeds a threshold.",
)
parser.add_argument(
    "--pseudo_action_analytic_mix",
    type=float,
    default=0.5,
    help="Blend factor for --pseudo_action_target_mode=analytic_blend. 0 keeps the "
         "current policy action, 1 uses the analytic action target on the first four channels.",
)
parser.add_argument(
    "--pseudo_action_residual_scale",
    type=float,
    default=0.5,
    help="Scale factor for --pseudo_action_target_mode=analytic_residual. The pseudo "
         "target becomes action + scale * clipped(analytic - action) on channels 0:4.",
)
parser.add_argument(
    "--pseudo_action_residual_clip",
    type=float,
    default=0.15,
    help="Absolute clip applied to (analytic - action) before residual scaling under "
         "--pseudo_action_target_mode=analytic_residual. <=0 disables the clip.",
)
parser.add_argument(
    "--pseudo_action_residual_channels",
    type=str,
    default="0,1,2,3",
    help="Comma-separated control-channel indices affected by analytic_residual. "
         "Default 0,1,2,3 updates all four pose/depth channels; e.g. 1,3 means pitch+depth only.",
)
parser.add_argument(
    "--pseudo_action_residual_sign_aware",
    type=_bool_arg,
    default=False,
    help="If True, residual-style pseudo targets only modify channels where analytic and "
         "policy actions already lie in the same sign half-space (product >= 0).",
)
parser.add_argument(
    "--pseudo_action_error_gate_metric",
    type=str,
    default="filtered_error",
    choices=["filtered_error", "raw_error"],
    help="Runtime STDW error signal used by analytic_residual_error_gate.",
)
parser.add_argument(
    "--pseudo_action_error_gate_threshold",
    type=float,
    default=0.35,
    help="analytic_residual_error_gate only injects the residual when the selected "
         "runtime error signal is >= this threshold.",
)
parser.add_argument(
    "--pseudo_action_lyapunov_gate",
    type=str,
    default="off",
    choices=["off", "require_pass", "require_fail"],
    help="Line-1 certified guidance gate for residual-style pseudo targets. off keeps "
         "the legacy behavior. require_pass injects the residual only on steps whose "
         "Lyapunov certificate currently passes (stdw_lyap_pass>=0.5, i.e. V is on the "
         "certified descent set). require_fail injects only on steps whose certificate "
         "fails (stdw_lyap_pass<0.5), i.e. corrective guidance where V is not descending. "
         "Non-finite / missing certificate defaults to no injection.",
)
parser.add_argument(
    "--pseudo_action_descent_align",
    type=str,
    default="off",
    choices=["off", "gate", "project"],
    help="Line-2 descent-aligned direction rule for residual-style pseudo targets. "
         "off keeps the legacy behavior. gate injects the (per-channel) residual only "
         "when the residual is aligned with the certified descent direction -grad(V) "
         "(i.e. per-channel residual*(-P*e) > margin). project keeps only the component "
         "of the residual along -grad(V) before injecting. -grad(V) = -P*e is analytic "
         "under the diagonal pose_quadratic V; e is read from the runtime tracking "
         "error. Non-finite / missing error defaults to no injection. Orthogonal to "
         "--pseudo_action_lyapunov_gate and --pseudo_trust_trigger.",
)
parser.add_argument(
    "--pseudo_action_descent_margin",
    type=float,
    default=0.0,
    help="Line-2 alignment margin. gate injects channel c only if "
         "residual[c]*(-P[c]*e[c]) > margin. project keeps the -grad(V) component only "
         "when the total alignment dot exceeds margin. 0 = accept any strictly "
         "descent-aligned residual.",
)
parser.add_argument(
    "--pseudo_trust_trigger",
    type=str,
    default="off",
    choices=["off", "gate"],
    help="Line-3 trust-as-trigger role for the analytic pseudo signal. off keeps the "
         "legacy trigger behavior. gate additionally requires the analytic S-surface "
         "action and the current policy action to be directionally consistent "
         "(cosine similarity over the first four channels >= "
         "--pseudo_trust_align_threshold) before the slow loop is allowed to fire on "
         "this step. This changes ONLY whether the slow loop triggers, never the pseudo "
         "target value. Orthogonal to the residual-value gates above.",
)
parser.add_argument(
    "--pseudo_trust_align_threshold",
    type=float,
    default=0.0,
    help="Line-3 minimum cosine similarity between the analytic S-surface action and "
         "the policy action (first four channels) required to trigger the slow loop "
         "under --pseudo_trust_trigger=gate. 0 = require only non-negative alignment.",
)
# 控制策略：默认启用 A-S-Surface 让 easyuuv_env 写出真实的 PID_value_add 到
# _pid_value_add_buf。若仍 self_adapt=False，delta_u≡0，pseudo-action 链路无效。
parser.add_argument(
    "--control_profile",
    type=str,
    default="A-S-Surface",
    choices=["A-S-Surface", "S-Surface", "PID", "direct_pwm"],
)
parser.add_argument(
    "--analytic_action_mode",
    type=str,
    default="off",
    choices=["off", "analytic", "residual_from_start"],
    help="Opt-in analytic S-surface action shim. off=policy action. analytic=replace "
         "control channels with quaternion-error/depth-error action and zero gain "
         "channels. residual_from_start=analytic + scale*(policy-frozen_ref), so "
         "the initial fast loop is exactly analytic while STDW/E-SUOT can learn a residual.",
)
parser.add_argument("--analytic_residual_scale", type=float, default=1.0)
parser.add_argument("--analytic_depth_target", type=float, default=1.5)
parser.add_argument("--analytic_depth_action_lim", type=float, default=1.0)
parser.add_argument("--analytic_roll_pitch_action_lim", type=float, default=0.6)
parser.add_argument("--analytic_yaw_action_lim", type=float, default=0.3)
parser.add_argument(
    "--analytic_gain_mode",
    type=str,
    default="zero",
    choices=["zero", "residual_from_start", "policy"],
    help="For 8D parametric policies, choose how action[:,4:8] is filled under "
         "--analytic_action_mode. zero gives exact gain-ratio identity when PE is "
         "disabled or identity_init bypasses the tuner.",
)
parser.add_argument("--enable_lyapunov_mask", type=_bool_arg, default=True)
parser.add_argument("--lyapunov_eps", type=float, default=0.0)
parser.add_argument("--lyapunov_p_diag", type=str, default="1.0,1.0,1.0,1.0")
parser.add_argument(
    "--lyapunov_gate_mode",
    type=str,
    default="sample_mask",
    choices=["sample_mask", "strict_sample_mask", "guarded_drift"],
)
parser.add_argument("--lyapunov_abs_margin", type=float, default=0.0)
parser.add_argument("--lyapunov_rel_margin", type=float, default=0.0)
parser.add_argument("--lyapunov_window_steps", type=int, default=60)
parser.add_argument("--lyapunov_min_pass_rate", type=float, default=0.0)
parser.add_argument(
    "--lyapunov_v_mode",
    type=str,
    default="pose_quadratic",
    choices=["pose_quadratic", "so3_consistent", "energy_with_rate", "control_lyapunov"],
    help="M1: Lyapunov V definition. pose_quadratic=legacy 0.5*e^T P e; "
         "so3_consistent=SO(3) quat_error_magnitude (reward-aligned); "
         "energy_with_rate=adds 0.5*edot^T Q edot kinetic term; "
         "control_lyapunov=CLF exponential decay gate dV<=-alpha*V.",
)
parser.add_argument("--lyapunov_q_diag", type=str, default="0.0,0.0,0.0,0.0",
                    help="M1: rate weights Q (roll,pitch,yaw,depth) for energy_with_rate/control_lyapunov.")
parser.add_argument("--lyapunov_decay_alpha", type=float, default=0.0,
                    help="M1: CLF exponential decay rate for control_lyapunov gate (dV<=-alpha*V).")
parser.add_argument(
    "--lyapunov_depth_barrier_mode",
    type=str,
    default="off",
    choices=["off", "boundary", "delete"],
    help="Depth term treatment in V. off=legacy full depth energy. "
         "boundary=zero the depth-channel error inside the safe core "
         "|depth_err|<half and smoothstep-restore across soft, matching "
         "easyuuv_env depth_deadband_mode=boundary. delete=zero the depth "
         "channel unconditionally (attitude-only V). NOTE: offline replay "
         "shows depth is ~3%% of Lyapunov energy, so depth removal alone is "
         "near-identity for pass rate; combine with --lyapunov_dv_criterion.",
)
parser.add_argument("--lyapunov_depth_barrier_half", type=float, default=0.3,
                    help="Safe-core half-width for barrier-consistent V depth term "
                         "(V1 safe core [-1.3,-0.7] center width when des_depth=starting_depth).")
parser.add_argument("--lyapunov_depth_barrier_soft", type=float, default=0.2,
                    help="Smoothstep restore band width for barrier-consistent V depth term.")
parser.add_argument(
    "--lyapunov_dv_criterion",
    type=str,
    default="strict",
    choices=["strict", "practical_band", "level_set", "relative"],
    help="Lyapunov pass criterion. strict=legacy monotone dV<eps (spuriously "
         "fails tight tracking of an oscillating reference). practical_band="
         "UUB pass iff dV<eps_rel*|V_prev| OR V<v_floor (recommended; offline "
         "recovers tight-tracking pass 0.44->0.94). level_set=pass iff V<v_floor "
         "OR dV<0. relative=pass iff dV<eps_rel*|V_prev|.",
)
parser.add_argument("--lyapunov_dv_eps_rel", type=float, default=0.05,
                    help="Relative dV tolerance band (fraction of |V_prev|) for "
                         "practical_band / relative dV criteria.")
parser.add_argument("--lyapunov_v_floor", type=float, default=0.05,
                    help="Low-energy ultimate-bound floor: V below this counts as "
                         "practically stable for practical_band / level_set criteria.")
# M2: directional hard-constraint guard (builds on M1's dV-sign mask).
# Default 'off' keeps the legacy soft-weighting-only behaviour (零行为变更).
# When active, the slow-loop update is *rejected* (not just down-weighted) if the
# batch lacks Lyapunov-descent evidence or its target pull points anti-descent.
parser.add_argument(
    "--stdw_dir_guard",
    type=str,
    default="off",
    choices=["off", "pass_rate", "descent_align", "both"],
    help="M2: directional hard constraint on slow-loop updates (补 §1.1 缺方向性). "
         "off=legacy soft mask weighting only. pass_rate=reject if descent "
         "fraction < --stdw_dir_guard_min_pass_rate. descent_align=reject if the "
         "target loss net-pull points against the Lyapunov descent direction. "
         "both=require both.",
)
parser.add_argument("--stdw_dir_guard_min_pass_rate", type=float, default=0.5,
                    help="M2: minimum batch Lyapunov-descent fraction (mask=1 share) "
                         "required to accept an update under pass_rate/both.")
parser.add_argument("--stdw_dir_guard_align_margin", type=float, default=0.0,
                    help="M2: minimum descent-alignment score in [-1,1] required under "
                         "descent_align/both. 0 = reject only net anti-descent batches.")
parser.add_argument(
    "--lyapunov_guard_action",
    type=str,
    default="skip_slow_loop",
    choices=["skip_slow_loop", "freeze_drift", "zero_drift"],
)
parser.add_argument("--lyapunov_guard_confirm_steps", type=int, default=30)
parser.add_argument("--lyapunov_guard_recover_steps", type=int, default=30)
parser.add_argument("--g_C_lr", type=float, default=5e-5)
parser.add_argument("--lambda_reg", type=float, default=1e-3)
# Regularization mode: parameter-space L2 (legacy) vs behavior KL on source
# observations (preferred). behavior_kl 用 frozen ref policy 的输出做 anchor，
# 在输出空间约束策略漂移，比在 5K 个权重参数上加 L2 更鲁棒。
parser.add_argument(
    "--reg_mode", type=str, default="behavior_kl", choices=["l2", "behavior_kl"]
)
parser.add_argument(
    "--stdw_update_acceptance",
    type=str,
    default="off",
    choices=["off", "batch_trust"],
)
parser.add_argument("--stdw_max_behavior_mse", type=float, default=1.0e-4)
parser.add_argument("--stdw_max_action_delta_mse", type=float, default=1.0e-3)
parser.add_argument("--stdw_max_target_mse_increase", type=float, default=1.0e-4)
parser.add_argument("--stdw_min_effective_batch_frac", type=float, default=0.2)
parser.add_argument("--target_drift", type=float, default=0.05)
parser.add_argument("--drift_start_step", type=int, default=200)
parser.add_argument("--drift_end_step", type=int, default=1200)
parser.add_argument("--drift_axes", type=str, default="0")
parser.add_argument(
    "--auto_drift_router",
    type=_bool_arg,
    default=False,
    help="Optional deployment probe: route COB drift based on initial com_to_cob xy. Default False keeps legacy behavior.",
)
parser.add_argument(
    "--drift_router_mode",
    type=str,
    default="off",
    choices=["off", "offset_correct"],
    help="off keeps --target_drift/--drift_axes; offset_correct applies a corrective drift for large xy offsets.",
)
parser.add_argument(
    "--drift_router_xy_threshold",
    type=float,
    default=0.04,
    help="Absolute xy offset threshold (m) used by --drift_router_mode offset_correct.",
)
parser.add_argument(
    "--depth_reference_frame",
    type=str,
    default=DEFAULT_DEPTH_REFERENCE_FRAME,
    choices=["raw_world_z", "surface_relative_depth"],
    help="V1 depth-barrier input contract. surface_relative_depth uses depth_v1 = z_world - depth_surface_z.",
)
parser.add_argument(
    "--depth_surface_z",
    type=float,
    default=DEFAULT_DEPTH_SURFACE_Z,
    help="Water-surface world-z used when --depth_reference_frame=surface_relative_depth.",
)
parser.add_argument(
    "--depth_upper_limit",
    type=float,
    default=DEFAULT_DEPTH_UPPER_LIMIT,
    help="Upper hard V1 depth bound in meters, negative underwater. Default -0.5.",
)
parser.add_argument(
    "--depth_lower_limit",
    type=float,
    default=DEFAULT_DEPTH_LOWER_LIMIT,
    help="Lower hard V1 depth bound in meters, negative underwater. Default -1.5.",
)
parser.add_argument(
    "--depth_transition_width",
    type=float,
    default=DEFAULT_DEPTH_TRANSITION_WIDTH,
    help="Soft transition-band width inside each V1 hard depth bound. Default 0.2 m.",
)
parser.add_argument("--ramp_shape", type=str, default="linear", choices=["linear", "cosine"],
                    help="Shape of the drift / disturbance ramp between drift_start_step and "
                         "drift_end_step. 'cosine' produces a smoother S-curve with zero slope "
                         "at both endpoints, useful for sine/oscillatory scenarios that suffer "
                         "from large transient errors during a steep linear ramp.")
parser.add_argument("--filter_window_seconds", type=float, default=5.0)
parser.add_argument("--slow_loop_interval", type=int, default=60)
parser.add_argument("--batch_size", type=int, default=256)
parser.add_argument("--buffer_capacity", type=int, default=50000)
parser.add_argument("--resume_buffer", type=str, default=None)
parser.add_argument(
    "--stdw_target_domain_mode",
    type=str,
    default="target_then_intermediate",
    choices=[
        "target_then_intermediate",
        "target_intermediate_mix",
        "intermediate_only",
        "mixed_all",
        "domain_balanced_mix",
    ],
    help=(
        "Target-side replay sampling mode. Default keeps legacy tag2->tag1 fallback. "
        "B-2' FM midpoint buffer enrichment is consumed only when this is set to "
        "target_intermediate_mix or intermediate_only. Phase-8 zeta-only online "
        "uses mixed_all/domain_balanced_mix to avoid recent-window manifold specialization."
    ),
)
parser.add_argument(
    "--stdw_target_intermediate_frac",
    type=float,
    default=0.5,
    help="Fraction of target-side samples drawn from tag1 when stdw_target_domain_mode=target_intermediate_mix.",
)
parser.add_argument(
    "--slow_loop_dry_run",
    type=_bool_arg,
    default=False,
    help="Diagnostic mode: sample slow-loop batches and compute losses, but never run backward/optimizer.step().",
)
parser.add_argument(
    "--log_policy_diagnostics",
    type=_bool_arg,
    default=False,
    help="Write policy parameter drift and fast-loop action-vs-reference diagnostics to stdw_output.csv.",
)
parser.add_argument(
    "--preserve_rng_around_slow_loop",
    type=_bool_arg,
    default=False,
    help="Diagnostic mode: restore torch RNG state after slow-loop sampling/update to avoid perturbing env noise/reset streams.",
)
parser.add_argument(
    "--stdw_update_target",
    type=str,
    default="policy",
    choices=["policy", "zeta4"],
    help=(
        "Phase-8 separation switch. policy keeps legacy slow-loop policy-weight updates. "
        "zeta4 freezes the policy and optimizes only four S-surface zeta1 multipliers "
        "through the state-space target loss."
    ),
)
parser.add_argument(
    "--stdw_zeta_lr",
    type=float,
    default=None,
    help="Learning rate for --stdw_update_target=zeta4. Defaults to --g_C_lr.",
)
parser.add_argument(
    "--stdw_zeta_bound",
    type=float,
    default=0.3,
    help="Symmetric tanh bound for zeta4 multipliers: multiplier = 1 +/- bound.",
)
parser.add_argument(
    "--stdw_zeta_reg",
    type=float,
    default=1.0e-3,
    help="L2 regularization on the bounded zeta4 multiplier offset.",
)
parser.add_argument(
    "--stdw_inv_proxy",
    type=str,
    default=None,
    help="Phase-8 path to the inverse dynamics proxy f(s_t, s_next)->a_t.",
)
parser.add_argument(
    "--stdw_zeta_grad_mask",
    type=str,
    default=None,
    help="Phase-8 zeta-only diagnostic: optional 4-value comma mask applied to "
         "zeta gradients before optimizer.step. Example '0,0,1,0' updates yaw only. "
         "Default None keeps all four axes trainable.",
)
parser.add_argument(
    "--stdw_direction_gate",
    type=_bool_arg,
    default=False,
    help="Phase-8 deployable tracking-envelope directional gate. Only update zeta if "
         "the proposed delta_zeta reduces the physical error.",
)
parser.add_argument(
    "--stdw_direction_gate_source",
    type=str,
    default="pseudo_actions",
    choices=["pseudo_actions", "target_anchor", "tracking_error"],
    help="Reference used by --stdw_direction_gate. pseudo_actions keeps the legacy "
         "diagnostic path; target_anchor uses the actual active action-space "
         "anchor; tracking_error uses live roll/pitch/yaw/depth tracking error.",
)
parser.add_argument(
    "--stdw_direction_gate_min_dot",
    type=float,
    default=0.0,
    help="Minimum mean dot(d_action, correction_direction) required by "
         "--stdw_direction_gate.",
)
parser.add_argument(
    "--stdw_depth_guard",
    type=_bool_arg,
    default=False,
    help="Depth-authority guard for zeta4. Near the depth barrier, reject any "
         "update that further decreases the depth zeta multiplier.",
)
parser.add_argument(
    "--stdw_depth_guard_upper_trigger",
    type=float,
    default=-0.7,
    help="Upper-side V1 depth trigger used by --stdw_depth_guard.",
)
parser.add_argument(
    "--stdw_depth_guard_lower_trigger",
    type=float,
    default=-1.3,
    help="Lower-side V1 depth trigger used by --stdw_depth_guard.",
)
parser.add_argument(
    "--stdw_depth_guard_eps",
    type=float,
    default=1.0e-4,
    help="Minimum actual decrease in the depth zeta multiplier required before "
         "--stdw_depth_guard rejects an update. This avoids float-noise false positives.",
)
parser.add_argument(
    "--stdw_zeta_depth_min_multiplier",
    type=float,
    default=0.0,
    help="Optional hard lower bound on the depth zeta multiplier when "
         "--stdw_update_target=zeta4. <= 0 disables the floor.",
)
parser.add_argument(
    "--stdw_zeta_write_scale",
    type=float,
    default=1.0,
    help="Opt-in gain on the legacy multiplicative zeta4 write path. 1.0 keeps "
         "the current behavior; >1.0 strengthens zeta4->action write without "
         "changing the target construction.",
)
parser.add_argument(
    "--stdw_runtime_attitude_zeta_path",
    type=str,
    default="legacy_pid",
    choices=["legacy_pid", "geo_so3"],
    help="Where accepted zeta4 attitude updates are deployed at runtime. "
         "legacy_pid keeps the old roll/pitch/yaw PID_args[:,:,0] path. "
         "geo_so3 redirects the first three zeta channels into the active SO(3) "
         "geo_zeta1 attitude surface. Default keeps current behavior.",
)
parser.add_argument(
    "--stdw_action_bridge_residual_scale",
    type=float,
    default=0.0,
    help="Opt-in direct residual write for l_tgt_space=action_bridge. Adds "
         "residual_scale*(multiplier-1)*(a_bridge-policy) on the first 4 control "
         "channels. 0 disables the path so it stays orthogonal to legacy runs.",
)
parser.add_argument(
    "--stdw_action_bridge_residual_clip",
    type=float,
    default=0.0,
    help="Optional absolute clip applied to (a_bridge-policy) before the direct "
         "residual write. <=0 disables clipping.",
)
parser.add_argument(
    "--stdw_action_bridge_upstream_mode",
    type=str,
    default="raw_abs",
    choices=["raw_abs", "delta_id", "policy_on_zbridge"],
    help="How to construct the action-space bridge from inv_proxy. raw_abs keeps "
         "a_bridge = inv_proxy(s_t, z_bridge). delta_id subtracts the self-pair "
     "bias inv_proxy(s_t, s_t) and re-centers the bridge around the current "
     "policy action. policy_on_zbridge uses the frozen reference policy delta "
     "a(z_bridge)-a(s_t) as the upstream bridge increment.",
)
parser.add_argument(
    "--stdw_action_bridge_equiv_audit",
    type=_bool_arg,
    default=False,
    help="Diagnostic-only logging for action_bridge upstream equivalence. Records "
         "how close Delta-ID and Policy-on-zbridge deltas are without changing "
         "the deployed behavior.",
)
parser.add_argument(
    "--stdw_target_mse_axis_audit",
    type=_bool_arg,
    default=False,
    help="Diagnostic-only per-axis trust audit. During batch_trust evaluation, "
         "recompute target_mse_after with roll-only, pitch-only, and yaw-only "
         "zeta updates to identify which attitude channel degrades the target.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_enable",
    type=_bool_arg,
    default=False,
    help="Opt-in direct deployed action-anchor residual. Reuses the latest accepted "
         "action_bridge delta and injects it into the fast loop without passing "
         "through zeta multipliers. Default False keeps current behavior.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_scale",
    type=float,
    default=0.0,
    help="Scale applied to the latest accepted reduced action-anchor residual in "
         "the fast loop. 0 disables the path.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_clip",
    type=float,
    default=0.0,
    help="Optional absolute clip on the cached reduced action-anchor residual "
         "before it is deployed. <=0 disables clipping.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_channels",
    type=str,
    default="attitude",
    choices=["attitude", "first4"],
    help="Channels affected by the reduced deployed action-anchor residual. "
         "attitude writes only roll/pitch/yaw; first4 also includes depth.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_geo_residual_scale",
    type=float,
    default=0.0,
    help="Optional runtime override for env.geo_residual_scale when reduced action "
         "anchor is enabled. This opens the SO(3) residual coupling path without "
         "changing default Task C behavior.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_sswp_sign_enable",
    type=_bool_arg,
    default=False,
    help="Use a slow EMA of deployable low-level compensation as the sign oracle "
         "for reduced action-anchor attitude channels. Magnitude stays from the "
         "raw action_bridge residual; sign comes from -SSWP EMA.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_dual_source_gate",
    type=_bool_arg,
    default=False,
    help="Keep a reduced action-anchor attitude channel only when its raw sign "
         "agrees with the SSWP sign oracle. Default False keeps current behavior.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_sswp_beta",
    type=float,
    default=0.999,
    help="EMA coefficient used to build the deployable SSWP sign oracle from "
         "runtime_pid_value for reduced action-anchor direction correction.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_consensus_gate",
    type=_bool_arg,
    default=False,
    help="Strong consensus oracle: only keep an attitude channel when SSWP sign "
         "and tracking-error sign agree; deployed sign follows the consensus.",
)
parser.add_argument(
    "--stdw_reduced_action_anchor_consensus_preferred_sign",
    type=_bool_arg,
    default=False,
    help="Consensus-preferred oracle: if SSWP and tracking-error signs agree, use "
         "that consensus sign; otherwise fall back to tracking-error sign.",
)
parser.add_argument(
    "--task_a_depth_failsafe_mode",
    type=str,
    default="off",
    choices=["off", "analytic_depth_channel", "sswp_depth_channel"],
    help="Optional Task-A fast-loop depth failsafe. It is orthogonal to STDW and "
         "default-off so A/B comparisons remain explicit.",
)
parser.add_argument(
    "--task_a_depth_failsafe_lower_trigger",
    type=float,
    default=-1.3,
    help="Activate --task_a_depth_failsafe_mode when true depth falls below this V1 value.",
)
parser.add_argument(
    "--task_a_depth_failsafe_release_trigger",
    type=float,
    default=-1.15,
    help="Release the Task-A depth failsafe only after true depth recovers above this V1 value.",
)
parser.add_argument(
    "--task_a_depth_failsafe_target_v1",
    type=float,
    default=-1.0,
    help="Independent V1 depth target used by Task-A fast-loop failsafe. Keeps the overlay "
         "orthogonal to --analytic_depth_target.",
)
parser.add_argument(
    "--task_a_depth_failsafe_blend",
    type=float,
    default=1.0,
    help="Blend factor for Task-A depth failsafe channel replacement. 1.0 means full override.",
)
parser.add_argument(
    "--task_a_depth_failsafe_sswp_scale",
    type=float,
    default=1.0,
    help="Scale applied to the depth-channel SSWP EMA when "
         "--task_a_depth_failsafe_mode=sswp_depth_channel.",
)

# Triggered Adaptation Gating (TAG)
parser.add_argument("--enable_trigger_gate", type=_bool_arg, default=True,
                    help="TAG: 仅当低通滤波复合误差 >= trigger_threshold 时才激活慢环梯度更新")
parser.add_argument("--trigger_threshold", type=float, default=0.05,
                    help="TAG 阈值 (rad)；filt_err 低于此值时静默慢环自适应，防止稳态参数漂移")

# Disturbance / noise
parser.add_argument("--noise_std", type=float, default=0.02)
parser.add_argument("--noise_corr", type=float, default=0.8)
parser.add_argument("--ang_vel_extra_std", type=float, default=0.0,
                    help="A4: 仅作用于 obs 末 3 维 root_ang_vel_b 的额外 IMU 陀螺白噪声 (rad/s)；"
                         "默认 0.0 保持 byte-identical，仅用于 Table 3 噪声敏感度扫描")
parser.add_argument("--wave_mode", type=str, default="sine", choices=["none", "constant", "sine", "jonswap"])
parser.add_argument("--wave_base_vel", nargs=3, type=float, default=[0.06, 0.0, 0.02])
parser.add_argument("--wave_amplitude", nargs=3, type=float, default=[0.08, 0.03, 0.02])
parser.add_argument("--wave_frequency", nargs=3, type=float, default=[0.16, 0.22, 0.3])

# Scenario / embodiment / fault (gradual injection presets)
parser.add_argument(
    "--scenario",
    type=str,
    default=None,
    help="Scenario preset name from scenarios.SCENARIO_PRESETS. "
         "When set, --wave_*/--noise_* are ignored and the schedule "
         "ramps disturbance from baseline to target between drift_start_step "
         "and drift_end_step.",
)
parser.add_argument(
    "--embodiment",
    type=str,
    default="base",
    choices=SUPPORTED_EMBODIMENTS,
)
parser.add_argument(
    "--pid_multipliers",
    type=str,
    default=None,
    help="Optional JSON string applied via env.apply_pid_multipliers AFTER embodiment apply, "
         "BEFORE the first reset. Example: "
         "'{\"roll_zeta1\": 0.7, \"yaw_zeta3\": 1.2, \"depth_zeta1\": 0.8}'. "
         "Keys must match '<axis>_<param>' where axis ∈ {roll,pitch,yaw,depth} and "
         "param ∈ {zeta1,zeta2,zeta3}. Useful for re-tuning gains on heavy/asymmetric "
         "embodiments without re-training (option 6.2 in REPORT_scenarios_6k).",
)
parser.add_argument(
    "--ctrl_mismatch",
    type=str,
    default=None,
    help="M3: JSON spec for controller-mismatch injection beyond pid_gain (plug-and-play). "
         "Applied via env.apply_ctrl_mismatch AFTER pid_multipliers, BEFORE first reset. "
         "Schema: {\"mode\": \"actuator_scale\", \"thrust_scale\": 0.2} | "
         "{\"mode\": \"s_surface_struct\", \"s_ratio_scale\": 0.5, \"add_scale\": 0.0} | "
         "{\"mode\": \"allocation_skew\", \"alloc_scale\": [1,1,0.3,1]}. "
         "Default None = pid_gain (现状，零行为变更). Designed to break the ~67%% mismatch ceiling "
         "by retargeting the failure to thrust/structural level (see PLAN §4).",
)
parser.add_argument(
    "--boundary_effect",
    type=str,
    default=None,
    help="M4: near-boundary effects (plug-and-play). Either a preset mode string "
         "({off, residual_buoyancy, free_surface, ground_effect, nonlinear_restoring, full}) "
         "or a JSON object {\"mode\": \"free_surface\", \"z_surface\": 1.5, ...} whose extra keys "
         "override BoundaryEffectModels fields. Applied via env.apply_boundary_effect AFTER "
         "ctrl_mismatch, BEFORE first reset. Default None = off (零行为变更). Models the Sim2Real "
         "free-surface / ground-effect / residual-buoyancy gap (see PLAN §5, ref/近边界效应.md).",
)
# M5: domain-adaptation backend for the slow-loop target anchor (plug-and-play).
# Default 'opr' keeps the legacy physics-prior pseudo_action path (零行为变更).
# esuot_full / esuot_light replace B_tgt["pseudo_actions"] with an E-SUOT optimal
# -transport anchor computed purely from the state-action distribution -- it never
# reads com_to_cob, J_inv, or the micro-probe (no physical prior; see PLAN §6).
parser.add_argument(
    "--domain_adapt_backend",
    type=str,
    default="opr",
    choices=["opr", "esuot_full", "esuot_light", "none"],
    help="M5: slow-loop target anchor source. opr=legacy pseudo_actions (default, "
         "physics prior). esuot_full=neural E-SUOT (Algorithm 1, barycentric). "
         "esuot_light=Sinkhorn barycentric (no NN). none=disable target term. "
         "esuot_* are prior-free (no com_to_cob/J_inv/micro-probe).",
)
parser.add_argument("--esuot_eps", type=float, default=0.1,
                    help="M5: entropy regularisation ε for the E-SUOT entropic plan.")
parser.add_argument("--esuot_eta", type=float, default=1.0,
                    help="M5: discretisation step η; transport cost is 1/(2η)||·||².")
parser.add_argument("--esuot_lambda1", type=float, default=1.0,
                    help="M5: unbalanced target-side conjugate weight (Eq.18 λ1).")
parser.add_argument("--esuot_lambda2", type=float, default=1.0,
                    help="M5: unbalanced source-side transport weight (Eq.18 λ2).")
parser.add_argument("--esuot_divergence", type=str, default="kl",
                    choices=["kl", "chi2", "softplus", "identity"],
                    help="M5: f-divergence for the conjugate f* (KL = Table 3 best).")
parser.add_argument("--esuot_inner_iters", type=int, default=50,
                    help="M5 (esuot_full): epochs per w_φ / T_θ step in Algorithm 1.")
parser.add_argument("--esuot_num_steps", type=int, default=1,
                    help="M5 (esuot_full): number of intermediate domains T in Algorithm 1.")
parser.add_argument("--esuot_sinkhorn_iters", type=int, default=200,
                    help="M5 (esuot_light): Sinkhorn iterations for the barycentric plan.")

# B5: state-match L_tgt path. Default 'action' keeps the legacy pseudo_action /
# esuot action anchor path (零行为变更). state_* variants replace L_tgt with
# ||phi(f(s_tgt, pi(s_tgt))) - phi(z_bridge))||^2 in a proxy-defined phi space.
# Diagnostic path only: enforced online_allowed=false and analytic_action_mode=off
# at policy-setup time (see the boundary check below).
parser.add_argument(
    "--l_tgt_space",
    type=str,
    default="action",
    choices=["action", "state_raw", "state_latent", "state_whitened", "zero", "action_bridge"],
    help="B5: slow-loop L_tgt space. action=legacy action-anchor MSE. "
         "action_bridge=Phase-8 E: maps z_bridge to an action via inv_proxy. "
         "state_raw/state_latent/state_whitened=state-match in a proxy phi space; "
         "requires --state_match_proxy and forces the diagnostic hard-constraints "
         "(online_allowed=false, analytic_action_mode=off). "
         "zero=Live A/B (U4) null control arm: slow-loop mechanics run (RNG, "
         "acceptance, optimizer.step) but mse_tgt is a shape-preserving zero "
         "tensor so target-side gradient contribution is exactly 0; requires the "
         "same diagnostic hard-constraints as state_*; NO --state_match_proxy.",
)
parser.add_argument(
    "--state_match_proxy",
    type=str,
    default=None,
    help="B5: path to a proxy .pt bundle (kind=mlp|latent|ensemble). Required when "
         "--l_tgt_space is a state_* variant; ignored otherwise.",
)
parser.add_argument(
    "--state_match_z_source",
    type=str,
    default="esuot_light_moved_states",
    choices=["esuot_light_moved_states", "fm_midpoint", "buffer_next_state"],
    help="B5/Phase-8: source of the z_bridge state anchor. "
         "esuot_light_moved_states=state read-out of the same Sinkhorn plan. "
         "fm_midpoint=explicit opt-in FM early-midpoint anchor from a Phase56 "
         "runtime bundle; requires bundle feature_dim == state_match_proxy state_dim. "
         "buffer_next_state=diagnostic-only one-step observed next_state from the "
         "replay row; removes FM/Sinkhorn target generation and isolates the proxy "
         "state-transition path without changing the default mainline.",
)
parser.add_argument(
    "--stdw_fm_bridge_alpha",
    "--fm_bridge_alpha",
    dest="stdw_fm_bridge_alpha",
    type=float,
    default=None,
    help="Optional alpha for --state_match_z_source=fm_midpoint. If omitted, "
         "uses the Phase56 bundle target_alpha / --phase56_runtime_target_alpha.",
)
# B5 ii-a follow-up: opt-in phi-space L_tgt scale normalization. Default 'none'
# keeps the pre-normalize behavior byte-identical (used by pre-2026-07-15 A/B).
# 'std' divides mse_tgt by z_match.detach().std().pow(2) so state arm L_tgt
# lands on the same O(1) scale as the action arm, controlling for gradient
# magnitude in the wide256 pilot follow-up.
parser.add_argument(
    "--l_tgt_state_normalize",
    type=str,
    default="none",
    choices=["none", "std"],
    help="B5 ii-a: normalize phi-space mse_tgt by z_match.detach().std()^2 "
         "when 'std'; 'none' preserves legacy behavior. Applies only when "
         "--l_tgt_space is a state_* variant.",
)
parser.add_argument(
    "--fault_thrusters",
    type=str,
    default="4,5",
    help="Comma list of thruster indices to fault. Used only when scenario specifies fault_rate.",
)
parser.add_argument(
    "--fault_rate_per_second",
    type=float,
    default=None,
    help="Override scenario fault_rate. Falls back to scenario default if None.",
)
parser.add_argument(
    "--fault_start_offset_steps",
    type=int,
    default=0,
    help="Offset from drift_start_step where fault begins ramping.",
)

# Convergence
parser.add_argument("--stability_threshold", type=float, default=0.05,
                    help="Absolute compound-error threshold below which we count convergence streak. "
                         "Default 0.05 is tight; raise for high-disturbance scenarios.")
parser.add_argument("--stability_threshold_rel", type=float, default=0.0,
                    help="If > 0, also compute a relative threshold = rel * baseline_compound_error_mean "
                         "where baseline window is steps [0, drift_start_step). The effective threshold "
                         "used at runtime is max(stability_threshold, relative). Set to 0 to disable.")
parser.add_argument("--stability_window", type=int, default=10)
parser.add_argument("--final_mse_window", type=int, default=200)
parser.add_argument(
    "--log_runtime_control",
    type=_bool_arg,
    default=False,
    help="Write env runtime PID_value, raw/clipped motorValue, and saturation diagnostics to stdw_output.csv.",
)
parser.add_argument(
    "--phase4a_signal_probe",
    type=_bool_arg,
    default=False,
    help="Write Phase 4A nonclip signal-source contract diagnostics. This is log-only "
         "and never changes control output, pseudo targets, or policy updates.",
)
parser.add_argument(
    "--phase4a_sswp_beta",
    type=float,
    default=0.999,
    help="Phase 4A log-only SSWP EMA beta for low-level correction telemetry.",
)
parser.add_argument(
    "--phase4a_anchor_scale",
    type=float,
    default=1.0,
    help="Phase 4A log-only scale for candidate anchor residuals.",
)
parser.add_argument(
    "--phase4a_descent_residual_scale",
    type=float,
    default=0.5,
    help="Phase 4A log-only scale for analytic descent residual anchors.",
)
parser.add_argument(
    "--phase4a_descent_residual_clip",
    type=float,
    default=0.25,
    help="Phase 4A log-only per-channel clip for analytic descent residual anchors.",
)
parser.add_argument(
    "--phase56_runtime_binding",
    type=_bool_arg,
    default=False,
    help="Enable log-only live Phase 5/6 runtime monitors and fallback-state logging. "
         "This never changes control output or online updates.",
)
parser.add_argument(
    "--phase56_runtime_reference_csv",
    type=str,
    default=None,
    help="Reference runtime csv used to build the offline Phase 5/6 live-binding bundle.",
)
parser.add_argument(
    "--phase56_runtime_bundle_dir",
    type=str,
    default=None,
    help="Optional prebuilt Phase 5/6 runtime bundle directory. When set, live binding "
         "loads this artifact instead of rebuilding from --phase56_runtime_reference_csv.",
)
parser.add_argument(
    "--phase56_runtime_execution_hooks",
    type=_bool_arg,
    default=False,
    help="Enable opt-in Phase 5/6 execution skeleton hooks. This can block the slow loop "
         "and reuse existing freeze/fallback/reset hooks, but still does not enable online "
         "mainline adaptation.",
)
parser.add_argument(
    "--phase56_runtime_frozen_min_dwell_steps",
    type=int,
    default=2,
    help="Minimum dwell steps to remain in FROZEN before allowing recovery back to ADAPT_ACTIVE.",
)
parser.add_argument(
    "--phase56_runtime_frozen_recover_steps",
    type=int,
    default=3,
    help="Number of consecutive clear steps required to recover from FROZEN to ADAPT_ACTIVE.",
)
parser.add_argument(
    "--phase56_runtime_fallback_dwell_steps",
    type=int,
    default=2,
    help="Minimum dwell steps to remain in FALLBACK_ZERO_DRIFT before escalating to RESET_REQUIRED.",
)
parser.add_argument(
    "--phase56_runtime_reset_dwell_steps",
    type=int,
    default=2,
    help="Minimum dwell steps to remain in RESET_REQUIRED before the execution hook requests reset.",
)
parser.add_argument(
    "--phase56_runtime_feature_set",
    type=str,
    default="core6",
    choices=["core6", "core6_sswp", "core6_sswp_fault"],
    help="Deployable Phase 5/6 feature set for live log-only monitors.",
)
parser.add_argument(
    "--phase56_runtime_context_gate",
    type=str,
    default="sswp_fault_to_safe",
    choices=["observed_direct", "safe_core_direct", "sswp_fault_to_safe"],
    help="Offline split/gate used to build the Phase 5/6 live-binding bundle.",
)
parser.add_argument(
    "--phase56_runtime_fm_profile",
    type=str,
    default="m160_i16_s128",
    choices=["m120_i12_s128", "m160_i16_s128", "m220_i24_s160"],
    help="Flow Matching profile used by the live log-only Phase 5/6 bundle.",
)
parser.add_argument(
    "--phase56_runtime_target_alpha",
    type=float,
    default=0.25,
    help="Recommended early-midpoint alpha recorded with the live Phase 5/6 monitor stream.",
)
parser.add_argument(
    "--phase56_runtime_max_samples",
    type=int,
    default=128,
    help="Maximum source/target samples used to prepare the live Phase 5/6 bundle.",
)
parser.add_argument(
    "--phase56_runtime_device",
    type=str,
    default="cpu",
    help="Device for the log-only Phase 5/6 live-binding bundle (default: cpu).",
)
parser.add_argument(
    "--phase56_curvature_relative_logging",
    type=_bool_arg,
    default=False,
    help="Enable log-only raw-curvature relative-shift diagnostics. This never changes "
         "control output, phase56_runtime_state, or fallback transitions.",
)
parser.add_argument(
    "--phase56_curvature_baseline_source",
    type=str,
    default="healthy_quantile_bank",
    help="Baseline provenance label for raw-curvature relative-shift logging.",
)
parser.add_argument(
    "--phase56_curvature_baseline_window_label",
    type=str,
    default="design_reference_observed_direct_v1",
    help="Baseline window/bank label for raw-curvature relative-shift logging.",
)
parser.add_argument(
    "--phase56_curvature_baseline_p95",
    type=float,
    default=0.015466931322589517,
    help="Healthy curvature p95 baseline for raw-curvature relative-shift logging.",
)
parser.add_argument(
    "--phase56_curvature_baseline_p99",
    type=float,
    default=0.016753863366320728,
    help="Healthy curvature p99 baseline for raw-curvature relative-shift logging.",
)
parser.add_argument(
    "--phase56_curvature_window_size",
    type=int,
    default=16,
    help="Rolling window size for raw-curvature watch/stress counters.",
)

# Paths / config
parser.add_argument("--workflow_config", type=str, default=None)
parser.add_argument("--logs_root", type=str, default=None)
parser.add_argument("--results_root", type=str, default=None)
parser.add_argument("--artifacts_root", type=str, default=None)
parser.add_argument("--experiment_name", type=str, default="easyuuv_direct")
parser.add_argument("--run_name", type=str, default=None)
parser.add_argument("--load_run", type=str, default=None)
parser.add_argument("--checkpoint", type=str, default="model_500.pt")
parser.add_argument(
    "--save_stdw_ckpt",
    type=_bool_arg,
    default=False,
    help="Save intermediate adapted STDW checkpoints. Default False keeps legacy behavior.",
)
parser.add_argument(
    "--stdw_ckpt_interval",
    type=int,
    default=300,
    help="Save adapted checkpoint every N steps when --save_stdw_ckpt is enabled.",
)
parser.add_argument(
    "--stdw_ckpt_keep_last",
    type=int,
    default=0,
    help="If >0, keep only the latest N intermediate checkpoint pairs.",
)
parser.add_argument(
    "--export_deploy_jit",
    type=_bool_arg,
    default=True,
    help="Also export obs_normalizer+actor TorchScript for Isaac-independent deployment.",
)
parser.add_argument("--logger", type=str, default=None, choices={"wandb", "tensorboard", "neptune"})
parser.add_argument("--log_project_name", type=str, default=None)
parser.add_argument("--resume", type=_bool_arg, default=None)


from omni.isaac.lab.app import AppLauncher  # type: ignore

AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# 干净包名：``import easyuuv_nc`` 即触发 gym.register（entry_point=easyuuv_nc.env:EasyUUVEnv）。
import easyuuv_nc  # noqa: E402,F401

# ---------------------------------------------------------------------------
# Lab-side imports (after AppLauncher).
# ---------------------------------------------------------------------------

from omni.isaac.lab.utils.math import euler_xyz_from_quat  # noqa: E402
from omni.isaac.lab_tasks.utils import get_checkpoint_path, parse_env_cfg  # noqa: E402
from omni.isaac.lab_tasks.utils.wrappers.rsl_rl import (  # noqa: E402
    RslRlOnPolicyRunnerCfg,
    RslRlVecEnvWrapper,
)
from rsl_rl.runners import OnPolicyRunner  # noqa: E402

from easyuuv_nc.custom_workflows import cli_args  # noqa: E402  isort: skip
from easyuuv_nc.custom_workflows.workflow_config import apply_config_overrides, load_workflow_config  # noqa: E402
from easyuuv_nc.custom_workflows.workflow_paths import (  # noqa: E402
    WorkflowPaths,
    ensure_directory,
    resolve_checkpoint_identifiers,
    resolve_checkpoint_path,
)


from easyuuv_nc.utils.stdw_buffer import StdwReplayBuffer  # noqa: E402
# M5: E-SUOT domain-adaptation adapter (prior-free target anchor). Only used when
# --domain_adapt_backend is esuot_full / esuot_light.
from easyuuv_nc.esuot import AdapterConfig, DomainAdaptAdapter  # noqa: E402
from easyuuv_nc.esuot.light import LightOTConfig, LightOTTransport  # noqa: E402
from easyuuv_nc.easyuuv_stdw_wrapper import EasyUUVStdwWrapper  # noqa: E402
from easyuuv_nc import stdw_dir_guard  # noqa: E402  (M2 directional hard-constraint guard)
from easyuuv_nc.stdw_integration import (  # noqa: E402
    DEFAULT_DEPTH_LOWER_LIMIT,
    DEFAULT_DEPTH_REFERENCE_FRAME,
    DEFAULT_DEPTH_SURFACE_Z,
    DEFAULT_DEPTH_TRANSITION_WIDTH,
    DEFAULT_DEPTH_UPPER_LIMIT,
    DEPTH_BARRIER_CONTRACT_VERSION,
    STDWCSVLogger,
    angle_remap,
    calculate_actuator_saturation_stats,
    calculate_attitude_error_so3,
    calculate_attitude_tracking_mse,
    calculate_compound_error,
    calculate_control_effort,
    calculate_depth_barrier_penalty,
    convert_depth_to_v1,
    calculate_domain_bias,
    resolve_depth_barrier_limits,
)
from easyuuv_nc.stdw_integration.flow_matching import (  # noqa: E402
    FlowMatchingConfig,
    compute_path_curvature,
    integrate_flow_euler,
    train_conditional_flow_matching,
)
from easyuuv_nc.stdw_integration.phase56 import (  # noqa: E402
    build_phase56_split,
    extract_phase56_features_from_csv,
    load_phase56_runtime_bundle,
    prepare_phase56_runtime_bundle,
)
from easyuuv_nc.stdw_integration.plots import _plot_stdw_diagnostics  # noqa: E402


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    workflow_cfg = load_workflow_config(args_cli.workflow_config)
    train_cfg = workflow_cfg.get("train", {}) or {}
    path_cfg = workflow_cfg.get("paths", {}) or {}

    if args_cli.task == parser.get_default("task") and "task" in train_cfg:
        args_cli.task = train_cfg["task"]
    if args_cli.num_envs == parser.get_default("num_envs") and "num_envs" in train_cfg:
        args_cli.num_envs = train_cfg["num_envs"]
    if args_cli.seed is None and "seed" in train_cfg:
        args_cli.seed = train_cfg["seed"]

    paths = WorkflowPaths.from_overrides(
        logs_root=args_cli.logs_root or path_cfg.get("logs_root"),
        results_root=args_cli.results_root or path_cfg.get("results_root"),
        artifacts_root=args_cli.artifacts_root or path_cfg.get("artifacts_root"),
    )

    env_cfg = parse_env_cfg(
        args_cli.task,
        use_gpu=not args_cli.cpu,
        num_envs=args_cli.num_envs,
        use_fabric=not args_cli.disable_fabric,
    )
    if workflow_cfg.get("env"):
        apply_config_overrides(env_cfg, workflow_cfg["env"])
    env_cfg.domain_randomization.use_custom_randomization = False
    env_cfg.noise_cfg.enable_noise = True
    env_cfg.noise_cfg.std_dev = args_cli.noise_std
    env_cfg.noise_cfg.correlation_coeff = args_cli.noise_corr
    # A4: IMU 陀螺额外白噪声（默认 0.0 即 byte-identical）；仅当 obs_include_ang_vel 且 >0 时生效。
    if float(getattr(args_cli, "ang_vel_extra_std", 0.0)) > 0.0:
        env_cfg.noise_cfg.ang_vel_extra_std = float(args_cli.ang_vel_extra_std)
    # 把 seed 注入到环境与全局 RNG，使 (a) noise / (b) torch.randn / (c) np.random 都跨 seed 不同。
    if args_cli.seed is not None:
        try:
            env_cfg.seed = int(args_cli.seed)
        except Exception:
            pass
        import random as _py_random
        import numpy as _np
        import torch as _torch
        _py_random.seed(int(args_cli.seed))
        _np.random.seed(int(args_cli.seed))
        _torch.manual_seed(int(args_cli.seed))
        if _torch.cuda.is_available():
            _torch.cuda.manual_seed_all(int(args_cli.seed))
    # 公平 overlay 模式：把参考轨迹与全局 RNG 解耦（专用 generator 按 seed 复现），
    # 使 STDW on/off 在相同 seed 下得到逐步一致的 desired 轨迹。
    if args_cli.deterministic_reference:
        env_cfg.deterministic_reference = True
    if args_cli.ground_plane_mode != "grid":
        env_cfg.ground_plane_mode = args_cli.ground_plane_mode
    # Fix A landing: opt-in error-driven pseudo-label. Default False keeps
    # disk-byte identity to the pre-Fix-A action-copy formula.
    if bool(args_cli.pseudo_error_driven):
        env_cfg.pseudo_error_driven = True
        env_cfg.pseudo_error_gain = float(args_cli.pseudo_error_gain)
    # 仅当 yaml 未在 disturbance_cfg.mode 上明确写入时，才用 CLI 默认值覆盖；
    # 否则 yaml 的 jonswap_* / base_vel 等会被 CLI 默认值整段抹掉。
    yaml_disturbance = (workflow_cfg.get("env") or {}).get("disturbance_cfg") or {}
    if "mode" not in yaml_disturbance:
        env_cfg.disturbance_cfg.mode = args_cli.wave_mode
    if "base_vel" not in yaml_disturbance:
        env_cfg.disturbance_cfg.base_vel = list(args_cli.wave_base_vel)
    if "amplitude" not in yaml_disturbance:
        env_cfg.disturbance_cfg.amplitude = list(args_cli.wave_amplitude)
    if "frequency" not in yaml_disturbance:
        env_cfg.disturbance_cfg.frequency = list(args_cli.wave_frequency)
    print(f"[DISTURBANCE] mode={env_cfg.disturbance_cfg.mode} "
          f"base_vel={list(getattr(env_cfg.disturbance_cfg, 'base_vel', []))} "
          f"hs={getattr(env_cfg.disturbance_cfg, 'jonswap_hs', None)} "
          f"fp={getattr(env_cfg.disturbance_cfg, 'jonswap_fp', None)}")

    agent_cfg: RslRlOnPolicyRunnerCfg = cli_args.parse_rsl_rl_cfg(args_cli.task, args_cli, workflow_cfg.get("agent"))
    if args_cli.load_run:
        agent_cfg.load_run = args_cli.load_run
    if args_cli.checkpoint:
        agent_cfg.load_checkpoint = args_cli.checkpoint

    raw_env = gym.make(args_cli.task, cfg=env_cfg)

    # 启用控制策略：A-S-Surface 才会触发 self_adapt=True，让 easyuuv_env._pid_value_add_buf
    # 写入真实的低层修正量；否则 _read_low_level_correction 始终返回 0，pseudo-action 无效。
    try:
        raw_env.unwrapped.apply_control_profile(args_cli.control_profile)
    except Exception as exc:
        print(f"[WARN] apply_control_profile({args_cli.control_profile}) failed: {exc}")

    # Cross-embodiment: apply once after gym.make. Embodiment switching is not
    # gradual (PhysX mass / inertia rebuild). The disturbance schedule below
    # remains the only time-varying axis.
    if args_cli.embodiment != "base":
        try:
            raw_env.unwrapped.apply_embodiment_config(args_cli.embodiment)
        except Exception as exc:
            print(f"[WARN] apply_embodiment_config({args_cli.embodiment}) failed: {exc}")

    # 强制把 yaml 里的 disturbance 字段透到 env runtime cfg：parse_env_cfg / gym.make
    # 路径上 disturbance_cfg 这种 inner class 的注入并不可靠，且 apply_control_profile /
    # apply_embodiment_config 可能把 mode/base_vel 改回默认，因此放在它们之后做最终覆盖。
    if yaml_disturbance:
        try:
            shift_kwargs = {}
            for k in ("mode", "base_vel", "amplitude", "frequency",
                      "jonswap_hs", "jonswap_fp", "jonswap_gamma",
                      "jonswap_depth", "jonswap_direction", "jonswap_seed"):
                if k in yaml_disturbance:
                    shift_kwargs[k] = yaml_disturbance[k]
            if shift_kwargs:
                raw_env.unwrapped.apply_runtime_domain_shift(**shift_kwargs)
                print(f"[DISTURBANCE/runtime] applied: {shift_kwargs}")
        except Exception as exc:
            print(f"[WARN] apply_runtime_domain_shift(yaml) failed: {exc}")

    # Optional PID multipliers (option 6.2): apply after embodiment so the
    # rebuilt mass / inertia is the gain reference.
    if args_cli.pid_multipliers:
        try:
            zeta_updates = json.loads(args_cli.pid_multipliers)
            if not isinstance(zeta_updates, dict):
                raise ValueError("pid_multipliers must decode to a JSON object")
            raw_env.unwrapped.apply_pid_multipliers(zeta_updates)
            print(f"[INFO] applied pid_multipliers: {zeta_updates}")
        except Exception as exc:
            print(f"[WARN] apply_pid_multipliers({args_cli.pid_multipliers!r}) failed: {exc}")
    if bool(args_cli.stdw_reduced_action_anchor_enable) and abs(
        float(args_cli.stdw_reduced_action_anchor_geo_residual_scale)
    ) > 0.0:
        try:
            raw_env.unwrapped.cfg.geo_residual_scale = float(
                args_cli.stdw_reduced_action_anchor_geo_residual_scale
            )
            print(
                "[INFO] applied reduced action-anchor geo_residual_scale="
                f"{raw_env.unwrapped.cfg.geo_residual_scale}"
            )
        except Exception as exc:
            print(
                "[WARN] apply reduced action-anchor geo_residual_scale="
                f"{args_cli.stdw_reduced_action_anchor_geo_residual_scale} failed: {exc}"
            )

    # M3: optional controller-mismatch injection beyond pid_gain (plug-and-play).
    if args_cli.ctrl_mismatch:
        try:
            mismatch_spec = json.loads(args_cli.ctrl_mismatch)
            if not isinstance(mismatch_spec, dict):
                raise ValueError("ctrl_mismatch must decode to a JSON object")
            raw_env.unwrapped.apply_ctrl_mismatch(mismatch_spec)
            print(f"[INFO] applied ctrl_mismatch: {mismatch_spec}")
        except Exception as exc:
            print(f"[WARN] apply_ctrl_mismatch({args_cli.ctrl_mismatch!r}) failed: {exc}")

    # M4: optional near-boundary effects (plug-and-play). Accepts either a preset
    # mode string or a JSON object. Applied after mismatch, before first reset.
    if args_cli.boundary_effect:
        try:
            raw = args_cli.boundary_effect.strip()
            if raw.startswith("{"):
                boundary_spec = json.loads(raw)
                if not isinstance(boundary_spec, dict):
                    raise ValueError("boundary_effect JSON must decode to an object")
            else:
                boundary_spec = raw  # preset mode string
            raw_env.unwrapped.apply_boundary_effect(boundary_spec)
            print(f"[INFO] applied boundary_effect: {boundary_spec}")
        except Exception as exc:
            print(f"[WARN] apply_boundary_effect({args_cli.boundary_effect!r}) failed: {exc}")

    # Compose: EasyUUVStdwWrapper -> RslRlVecEnvWrapper.
    sim_dt = float(getattr(env_cfg.sim, "dt", 1.0 / 120.0))
    # One env.step advances decimation physics substeps, so the physical time per
    # logged row is sim_dt * decimation. sim_dt itself is reused for depth-barrier
    # physics / disturbance ramp timing and must NOT be mutated; time_axis_dt is a
    # dedicated logging-only step used solely for the CSV time_s axis.
    _decimation = int(getattr(env_cfg, "decimation", 1) or 1)
    time_axis_dt = sim_dt * _decimation
    depth_limits = resolve_depth_barrier_limits(
        upper_limit=float(args_cli.depth_upper_limit),
        lower_limit=float(args_cli.depth_lower_limit),
        transition_width=float(args_cli.depth_transition_width),
    )

    def _depth_to_v1(depth_or_z):
        return convert_depth_to_v1(
            depth_or_z,
            reference_frame=str(args_cli.depth_reference_frame),
            surface_z=float(args_cli.depth_surface_z),
        )

    def _depth_barrier_for_v1(depth_v1):
        return calculate_depth_barrier_penalty(
            depth_v1,
            dt=sim_dt,
            upper_limit=float(depth_limits["depth_upper_limit"]),
            upper_safe=float(depth_limits["depth_upper_safe"]),
            lower_safe=float(depth_limits["depth_lower_safe"]),
            lower_limit=float(depth_limits["depth_lower_limit"]),
        )

    print(
        "[DEPTH-CONTRACT] "
        f"frame={args_cli.depth_reference_frame} surface_z={float(args_cli.depth_surface_z):.3f} "
        f"hard=[{float(depth_limits['depth_lower_limit']):.3f}, {float(depth_limits['depth_upper_limit']):.3f}] "
        f"safe=[{float(depth_limits['depth_lower_safe']):.3f}, {float(depth_limits['depth_upper_safe']):.3f}] "
        f"width={float(depth_limits['depth_tube_width']):.3f}m",
        flush=True,
    )

    def _error_signal_callable(inner_env):
        try:
            des_quat = inner_env.unwrapped._goal[0]
            des_roll, des_pitch, des_yaw = euler_xyz_from_quat(des_quat.unsqueeze(0))
            root_quat = inner_env.unwrapped._robot.data.root_quat_w[0]
            true_roll, true_pitch, true_yaw = euler_xyz_from_quat(root_quat.unsqueeze(0))
            true_z = float(inner_env.unwrapped._robot.data.root_pos_w[0][2].item())
            des_depth = float(inner_env.unwrapped.cfg.starting_depth)
            return calculate_compound_error(
                float(angle_remap(des_roll)[0].item()),
                float(angle_remap(des_pitch)[0].item()),
                float(angle_remap(des_yaw)[0].item()),
                float(angle_remap(true_roll)[0].item()),
                float(angle_remap(true_pitch)[0].item()),
                float(angle_remap(true_yaw)[0].item()),
                des_depth,
                true_z,
            )
        except Exception:
            return 0.0

    effective_target_drift, effective_drift_axes, initial_cob_xy = _resolve_drift_router(raw_env, args_cli)

    stdw_wrapper = EasyUUVStdwWrapper(
        raw_env,
        drift_start_step=args_cli.drift_start_step,
        drift_end_step=args_cli.drift_end_step,
        target_drift=effective_target_drift,
        drift_axes=effective_drift_axes,
        enable_filter=args_cli.enable_filter,
        filter_window_seconds=args_cli.filter_window_seconds,
        sim_dt_seconds=sim_dt,
        ramp_shape=args_cli.ramp_shape,
        error_signal_callable=_error_signal_callable,
        enable_lyapunov_mask=args_cli.enable_lyapunov_mask,
        lyapunov_P_diag=_parse_p_diag(args_cli.lyapunov_p_diag),
        lyapunov_eps=args_cli.lyapunov_eps,
        lyapunov_gate_mode=args_cli.lyapunov_gate_mode,
        lyapunov_abs_margin=args_cli.lyapunov_abs_margin,
        lyapunov_rel_margin=args_cli.lyapunov_rel_margin,
        lyapunov_window_steps=args_cli.lyapunov_window_steps,
        lyapunov_min_pass_rate=args_cli.lyapunov_min_pass_rate,
        lyapunov_v_mode=args_cli.lyapunov_v_mode,
        lyapunov_Q_diag=_parse_p_diag(args_cli.lyapunov_q_diag),
        lyapunov_decay_alpha=args_cli.lyapunov_decay_alpha,
        lyapunov_depth_barrier_mode=args_cli.lyapunov_depth_barrier_mode,
        lyapunov_depth_barrier_half=args_cli.lyapunov_depth_barrier_half,
        lyapunov_depth_barrier_soft=args_cli.lyapunov_depth_barrier_soft,
        lyapunov_dv_criterion=args_cli.lyapunov_dv_criterion,
        lyapunov_dv_eps_rel=args_cli.lyapunov_dv_eps_rel,
        lyapunov_v_floor=args_cli.lyapunov_v_floor,
    )
    env = RslRlVecEnvWrapper(stdw_wrapper)

    log_root_path = paths.training_log_root(args_cli.experiment_name)
    print(f"[INFO] Loading checkpoint from directory: {log_root_path}", flush=True)
    import os
    if os.path.isfile(args_cli.checkpoint):
        resume_path = os.path.abspath(args_cli.checkpoint)
    else:
        resume_path = resolve_checkpoint_path(
            log_root_path,
            agent_cfg.load_run,
            agent_cfg.load_checkpoint,
            get_checkpoint_path,
        )
    print(f"[INFO] Loading model checkpoint from: {resume_path}", flush=True)
    resolved_load_run, resolved_checkpoint = resolve_checkpoint_identifiers(resume_path, agent_cfg.load_run)

    agent_cfg_dict = agent_cfg.to_dict()
    ppo_runner = OnPolicyRunner(env, agent_cfg_dict, log_dir=None, device=agent_cfg.device)
    # 仅加载策略权重；play 下游自建 optimizer（见下方 Adam），且分阶段训练的
    # checkpoint optimizer 仅含可训练子集，会与全参数 optimizer 的 param group 不匹配。
    ppo_runner.load(resume_path, load_optimizer=False)
    runtime_device = env.unwrapped.device

    # Direct fine-tune (no teacher/student copy).
    policy = ppo_runner.alg.actor_critic.to(runtime_device)
    policy.train()
    stdw_update_target = str(getattr(args_cli, "stdw_update_target", "policy"))
    stdw_zeta_delta = None
    stdw_zeta_last_multiplier = None
    stdw_runtime_action_bridge_delta = None
    stdw_runtime_reduced_action_anchor = None
    stdw_reduced_action_anchor_sswp_ema = None
    stdw_zeta_grad_mask = _parse_zeta_grad_mask(getattr(args_cli, "stdw_zeta_grad_mask", None))
    stdw_direction_gate_source = str(getattr(args_cli, "stdw_direction_gate_source", "pseudo_actions"))

    if bool(getattr(args_cli, "stdw_direction_gate", False)) or bool(getattr(args_cli, "stdw_depth_guard", False)):
        if str(getattr(args_cli, "stdw_update_acceptance", "off")) != "batch_trust":
            raise SystemExit(
                "--stdw_direction_gate/--stdw_depth_guard require "
                "--stdw_update_acceptance=batch_trust so rejected updates can be rolled back."
            )
    if float(getattr(args_cli, "stdw_zeta_depth_min_multiplier", 0.0)) > 0.0 and stdw_update_target != "zeta4":
        raise SystemExit(
            "--stdw_zeta_depth_min_multiplier is only valid with --stdw_update_target=zeta4."
        )
    if bool(getattr(args_cli, "stdw_direction_gate", False)) and stdw_direction_gate_source == "target_anchor":
        if str(getattr(args_cli, "l_tgt_space", "action")) not in {"action", "action_bridge"}:
            raise SystemExit(
                "--stdw_direction_gate_source=target_anchor requires "
                "--l_tgt_space in {action, action_bridge}."
            )
    if float(getattr(args_cli, "stdw_zeta_write_scale", 1.0)) <= 0.0:
        raise SystemExit("--stdw_zeta_write_scale must be > 0.")
    if str(getattr(args_cli, "stdw_runtime_attitude_zeta_path", "legacy_pid")) != "legacy_pid":
        if stdw_update_target != "zeta4":
            raise SystemExit("--stdw_runtime_attitude_zeta_path is only valid with --stdw_update_target=zeta4.")
    if abs(float(getattr(args_cli, "stdw_action_bridge_residual_scale", 0.0))) > 0.0:
        if stdw_update_target != "zeta4":
            raise SystemExit(
                "--stdw_action_bridge_residual_scale is only valid with --stdw_update_target=zeta4."
            )
        if str(getattr(args_cli, "l_tgt_space", "action")) != "action_bridge":
            raise SystemExit(
                "--stdw_action_bridge_residual_scale requires --l_tgt_space=action_bridge."
            )
    if bool(getattr(args_cli, "stdw_reduced_action_anchor_enable", False)) or abs(
        float(getattr(args_cli, "stdw_reduced_action_anchor_scale", 0.0))
    ) > 0.0:
        if stdw_update_target != "zeta4":
            raise SystemExit(
                "--stdw_reduced_action_anchor_* are only valid with --stdw_update_target=zeta4."
            )
        if str(getattr(args_cli, "l_tgt_space", "action")) != "action_bridge":
            raise SystemExit(
                "--stdw_reduced_action_anchor_* require --l_tgt_space=action_bridge."
            )
    if bool(getattr(args_cli, "stdw_reduced_action_anchor_consensus_gate", False)) and bool(
        getattr(args_cli, "stdw_reduced_action_anchor_consensus_preferred_sign", False)
    ):
        raise SystemExit(
            "--stdw_reduced_action_anchor_consensus_gate and "
            "--stdw_reduced_action_anchor_consensus_preferred_sign are mutually exclusive; "
            "run them as separate experiments."
        )
    if str(getattr(args_cli, "task_a_depth_failsafe_mode", "off")) != "off":
        if float(args_cli.task_a_depth_failsafe_release_trigger) <= float(args_cli.task_a_depth_failsafe_lower_trigger):
            raise SystemExit(
                "--task_a_depth_failsafe_release_trigger must be greater than "
                "--task_a_depth_failsafe_lower_trigger to form a valid hysteresis band."
            )

    if getattr(args_cli, "stdw_direction_gate", False):
        # Directional gate requires rejection sampling machinery to evaluate and potentially undo the step.
        args_cli.stdw_rejection_sampling = True
    if stdw_update_target == "zeta4":
        for parameter in policy.parameters():
            parameter.requires_grad_(False)
        stdw_zeta_delta = torch.nn.Parameter(torch.zeros(4, device=runtime_device))
        stdw_zeta_last_multiplier = torch.ones(4, device=runtime_device)
        zeta_lr = float(args_cli.stdw_zeta_lr) if args_cli.stdw_zeta_lr is not None else float(args_cli.g_C_lr)
        optimizer = torch.optim.Adam([stdw_zeta_delta], lr=zeta_lr)
        print(
            f"[INFO] Phase-8 zeta-only online adaptation active: lr={zeta_lr} "
            f"bound={args_cli.stdw_zeta_bound} reg={args_cli.stdw_zeta_reg}",
            flush=True,
        )
        if stdw_zeta_grad_mask is not None:
            print(
                f"[INFO] Phase-8 zeta gradient mask active: {stdw_zeta_grad_mask.detach().cpu().tolist()}",
                flush=True,
            )
    else:
        for parameter in policy.parameters():
            parameter.requires_grad_(True)
        optimizer = torch.optim.Adam(policy.parameters(), lr=args_cli.g_C_lr)

    theta_pre = {n: p.detach().clone() for n, p in policy.named_parameters()}

    # Frozen reference copy of the loaded checkpoint, used as the "source" anchor
    # for the slow loop. Without this, B_src["actions"] (recorded under the
    # fine-tuned policy) would coincide with policy(obs_src) and L_src ≡ 0.
    policy_ref = copy.deepcopy(policy).to(runtime_device)
    policy_ref.eval()
    for parameter in policy_ref.parameters():
        parameter.requires_grad_(False)

    obs_normalizer = ppo_runner.obs_normalizer.to(runtime_device)
    obs_normalizer.eval()
    for parameter in obs_normalizer.parameters():
        parameter.requires_grad_(False)

    # Sanity check: the training forward path must keep grad alive.
    try:
        dummy_obs = torch.zeros(1, env_cfg.num_observations, device=runtime_device)
        sample_out = _policy_forward_train(policy, dummy_obs)
        print(f"[INFO] _policy_forward_train requires_grad={sample_out.requires_grad}")
        if stdw_update_target == "policy":
            assert sample_out.requires_grad, "fatal: policy training forward path is detached"
    except AssertionError:
        raise
    except Exception as exc:
        print(f"[WARN] forward-path sanity check skipped: {exc}")

    buffer = StdwReplayBuffer(capacity=args_cli.buffer_capacity, device=runtime_device)
    if args_cli.resume_buffer:
        try:
            buffer.load(Path(args_cli.resume_buffer))
            print(f"[INFO] Resumed buffer from {args_cli.resume_buffer}; size={len(buffer)}")
        except Exception as exc:
            print(f"[WARN] Failed to load resume buffer: {exc}")

    # M5: build the E-SUOT domain-adaptation adapter when a non-OPR backend is
    # requested. Kept None for the default 'opr'/'none' paths so the legacy
    # pseudo_action anchor is used unchanged (零行为变更).
    domain_adapt_adapter = None
    if args_cli.domain_adapt_backend in ("esuot_full", "esuot_light"):
        domain_adapt_adapter = DomainAdaptAdapter(
            AdapterConfig(
                backend=args_cli.domain_adapt_backend,
                eps=float(args_cli.esuot_eps),
                eta=float(args_cli.esuot_eta),
                lambda1=float(args_cli.esuot_lambda1),
                lambda2=float(args_cli.esuot_lambda2),
                divergence=str(args_cli.esuot_divergence),
                inner_iters=int(args_cli.esuot_inner_iters),
                num_steps=int(args_cli.esuot_num_steps),
                sinkhorn_iters=int(args_cli.esuot_sinkhorn_iters),
                device=str(runtime_device),
                seed=args_cli.seed,
            )
        )
        print(
            f"[INFO] M5 domain-adapt backend = {args_cli.domain_adapt_backend} "
            f"(prior-free E-SUOT anchor; eps={args_cli.esuot_eps}, eta={args_cli.esuot_eta})",
            flush=True,
        )

    # B5: state-match kit. Only constructed when --l_tgt_space is a state_* variant.
    # Hard-constraints (documented in AGENTS.md, B5 route iv):
    #   * state_* requires a state z_bridge, which currently is only served by the
    #     esuot_light plan read-out (compute_state_anchor). Force
    #     --domain_adapt_backend=esuot_light so B_src/B_tgt flow through the same
    #     Sinkhorn plan.
    #   * state_* is a diagnostic path; --online_allowed must be false and
    #     --analytic_action_mode=off (fast-loop keeps the RL policy on the executed
    #     control so slow-loop gradients actually reach the executed policy).
    state_match_kit = None
    if args_cli.l_tgt_space != "action":
        # Shared diagnostic hard-constraints across state_* and zero: slow-loop
        # policy-weight gradients are not allowed online. Phase-8 zeta4 is the
        # single opt-in exception: it freezes the policy and updates only 4-D
        # controller gains.
        phase8_zeta_online = str(getattr(args_cli, "stdw_update_target", "policy")) == "zeta4"
        if bool(getattr(args_cli, "online_allowed", False)) and not phase8_zeta_online:
            raise SystemExit(f"--l_tgt_space={args_cli.l_tgt_space} requires online_allowed=false (B5 hard constraint)")
        if str(getattr(args_cli, "analytic_action_mode", "off")) != "off" and not phase8_zeta_online:
            raise SystemExit(
                f"--l_tgt_space={args_cli.l_tgt_space} requires --analytic_action_mode=off "
                "(B5 hard constraint: slow-loop gradients must reach the executed policy)"
            )
        if args_cli.l_tgt_space == "zero":
            # Live A/B (U4) null control: no proxy, no z_bridge, no phi space.
            # domain_adapt_backend / state_match_proxy constraints do NOT apply.
            # mse_tgt is a shape-preserving zero tensor computed inline at the
            # dispatch site below; slow-loop mechanics (RNG, acceptance,
            # optimizer.step) are preserved so the arm answers "does slow-loop
            # mechanics itself destabilize the policy independent of the target
            # anchor?" (P1 vs P3 arbitration per PLAN_LIVE_AB_20260716 §3.1).
            print(
                "[INFO] B5 Live A/B (U4) null arm: l_tgt_space=zero "
                "(mse_tgt=0, no proxy, slow-loop mechanics preserved)",
                flush=True,
            )
        elif args_cli.l_tgt_space == "action_bridge":
            print(
                "[INFO] Phase-8 Action Bridge: l_tgt_space=action_bridge "
                "(mse_tgt uses InverseDynamicsProxy to map z_bridge to a_bridge)",
                flush=True,
            )
        else:
            # state_* variant: requires proxy + esuot_light z_bridge read-out.
            if args_cli.state_match_proxy is None:
                raise SystemExit("--l_tgt_space=state_* requires --state_match_proxy")
            if args_cli.domain_adapt_backend != "esuot_light":
                raise SystemExit(
                    f"--l_tgt_space=state_* currently requires --domain_adapt_backend=esuot_light "
                    f"(got {args_cli.domain_adapt_backend!r}); the state z_bridge is a read-out of "
                    "the same Sinkhorn plan."
                )
            from workflows.tools.state_match_kit_v1 import load_state_match_kit
            state_match_kit = load_state_match_kit(args_cli.state_match_proxy, kind_override="auto")
            # Sanity: bundle kind must be consistent with the requested phi space.
            _expected_kind = {
                "state_raw": "mlp",
                "state_latent": "latent",
                "state_whitened": "ensemble",
            }[args_cli.l_tgt_space]
            if state_match_kit.kind != _expected_kind:
                raise SystemExit(
                    f"--l_tgt_space={args_cli.l_tgt_space} expects proxy kind={_expected_kind!r}, "
                    f"got {state_match_kit.kind!r} from {args_cli.state_match_proxy}"
                )
            print(
                f"[INFO] B5 state-match: l_tgt_space={args_cli.l_tgt_space} "
                f"proxy_kind={state_match_kit.kind} match_dim={state_match_kit.match_dim} "
                f"z_source={args_cli.state_match_z_source}",
                flush=True,
            )

    inv_proxy_model = None
    if args_cli.l_tgt_space == "action_bridge":
        if not args_cli.stdw_inv_proxy:
            raise SystemExit("--l_tgt_space=action_bridge requires --stdw_inv_proxy")
        if str(args_cli.state_match_z_source) != "fm_midpoint":
            raise SystemExit("--l_tgt_space=action_bridge requires --state_match_z_source=fm_midpoint.")
        if not (args_cli.phase56_runtime_bundle_dir or args_cli.phase56_runtime_reference_csv):
            raise SystemExit(
                "--l_tgt_space=action_bridge requires --phase56_runtime_bundle_dir "
                "or --phase56_runtime_reference_csv."
            )
        from easyuuv_nc.workflows.tools.train_inv_dynamics_proxy_obs12_v1 import InverseDynamicsProxy
        _d = torch.load(args_cli.stdw_inv_proxy, map_location=runtime_device, weights_only=False)
        inv_proxy_model = InverseDynamicsProxy(state_dim=_d["state_dim"], action_dim=_d["action_dim"], hidden_dim=_d["hidden"], depth=_d["depth"])
        inv_proxy_model.load_state_dict(_d["model_state_dict"])
        inv_proxy_model.eval()
        inv_proxy_model.to(runtime_device)
        inv_proxy_norm = {k: torch.tensor(v, device=runtime_device) for k, v in _d["norm"].items()}
        print(f"[INFO] Loaded inverse dynamics proxy from {args_cli.stdw_inv_proxy}", flush=True)

    # M2: directional hard-constraint guard config. Default mode 'off' makes
    # evaluate() always accept, preserving the legacy soft-mask-only path.
    if stdw_update_target == "zeta4":
        if str(args_cli.l_tgt_space) not in {"state_raw", "state_latent", "state_whitened", "action_bridge"}:
            raise SystemExit("--stdw_update_target=zeta4 requires --l_tgt_space=state_* or action_bridge.")
        if str(args_cli.l_tgt_space) != "action_bridge" and state_match_kit is None:
            raise SystemExit("--stdw_update_target=zeta4 requires a loaded --state_match_proxy (unless action_bridge).")
        if str(args_cli.domain_adapt_backend) != "esuot_light":
            raise SystemExit("--stdw_update_target=zeta4 requires --domain_adapt_backend=esuot_light.")
        if str(args_cli.stdw_target_domain_mode) not in {"mixed_all", "domain_balanced_mix"}:
            raise SystemExit(
                "--stdw_update_target=zeta4 requires --stdw_target_domain_mode=mixed_all "
                "or domain_balanced_mix."
            )

    dir_guard_cfg = stdw_dir_guard.DirGuardConfig(
        mode=str(args_cli.stdw_dir_guard),
        min_pass_rate=float(args_cli.stdw_dir_guard_min_pass_rate),
        align_margin=float(args_cli.stdw_dir_guard_align_margin),
    )
    if dir_guard_cfg.active:
        print(
            f"[INFO] M2 directional guard = {dir_guard_cfg.mode} "
            f"(min_pass_rate={dir_guard_cfg.min_pass_rate}, "
            f"align_margin={dir_guard_cfg.align_margin})",
            flush=True,
        )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    result_run_dir = paths.result_run_dir(args_cli.experiment_name, resolved_load_run, resolved_checkpoint)
    stdw_run_dir = ensure_directory(result_run_dir / f"stdw_new_{timestamp}")
    csv_path = stdw_run_dir / "stdw_output.csv"
    artifact_dir = ensure_directory(
        paths.artifacts_root / args_cli.experiment_name / resolved_load_run / Path(resolved_checkpoint).stem / "stdw_new"
    )
    ckpt_dir = ensure_directory(stdw_run_dir / "checkpoints")
    saved_ckpts: List[Dict[str, Optional[str]]] = []

    _set_initial_disturbance(env, args_cli, yaml_disturbance=yaml_disturbance)

    # Optional: scenario-driven gradual injection schedule. When --scenario is
    # passed, the disturbance ramps from baseline to target between
    # drift_start_step and drift_end_step (in lockstep with the wrapper's COB
    # drift). When --scenario is None, the legacy step-injection above stays in
    # effect.
    schedule = None
    if args_cli.scenario is not None:
        try:
            from easyuuv_nc.workflows.scenarios import resolve_scenario
            from easyuuv_nc.workflows.disturbance_schedule import DisturbanceSchedule
        except ImportError:
            sys.path.insert(0, str(WORKFLOW_DIR))
            from scenarios import resolve_scenario  # type: ignore
            from disturbance_schedule import DisturbanceSchedule  # type: ignore

        fault_thrusters_cli = [int(x.strip()) for x in args_cli.fault_thrusters.split(",") if x.strip()]
        spec = resolve_scenario(
            args_cli.scenario,
            fault_thrusters=fault_thrusters_cli,
            fault_rate_per_second=args_cli.fault_rate_per_second,
            fault_start_offset_steps=args_cli.fault_start_offset_steps,
        )
        schedule = DisturbanceSchedule(
            env.unwrapped,
            spec,
            drift_start_step=args_cli.drift_start_step,
            drift_end_step=args_cli.drift_end_step,
            sim_dt_seconds=sim_dt,
            ramp_shape=args_cli.ramp_shape,
        )
        schedule.reset()
        print(
            f"[INFO] Scenario={spec.name} mode={spec.mode} "
            f"target_amp={spec.target.get('amplitude')} "
            f"target_base_vel={spec.target.get('base_vel')} "
            f"fault_rate={spec.fault_rate_per_second} "
            f"embodiment={args_cli.embodiment} "
            f"drift=[{args_cli.drift_start_step}, {args_cli.drift_end_step}]"
        )

    fieldnames = [
        "step",
        "time_s",
        "rho",
        "drift_fraction",
        "use_stdw",
        "use_filter",
        "use_quantile_filter",
        "raw_error",
        "filtered_error",
        "compound_error",
        "metric_contract_version",
        "depth_reference_frame",
        "depth_surface_z",
        "depth_upper_limit",
        "depth_upper_safe",
        "depth_lower_safe",
        "depth_lower_limit",
        "depth_tube_width",
        "depth_transition_width",
        "env_eval_mode",
        "goal_spawn_radius",
        "init_guidance_rate",
        "env_episode_step",
        "starting_depth_raw",
        "depth_lower_margin",
        "depth_upper_margin",
        "depth_in_hard_tube",
        "des_depth_lower_margin",
        "des_depth_upper_margin",
        "des_depth_in_hard_tube",
        "des_depth_in_safe_core",
        "attitude_tracking_mse",
        "so3_attitude_error",
        "depth_barrier_penalty",
        "depth_violation",
        "depth_upper_transition_penalty",
        "depth_lower_transition_penalty",
        "saturation_authority_proxy",
        "lyapunov_V",
        "lyapunov_dV",
        "lyapunov_pass",
        "lyapunov_pass_rate_window",
        "lyapunov_safety_block",
        "lyapunov_safety_reason",
        "stdw_safety_state",
        "stdw_safety_transition",
        "stdw_fallback_step",
        "stdw_mask",
        "effective_batch_frac",
        "loss",
        "loss_source",
        "loss_target",
        "loss_reg",
        "stdw_update_accepted",
        "stdw_update_rejected",
        "stdw_acceptance_reason",
        "stdw_behavior_mse_before",
        "stdw_behavior_mse_after",
        "stdw_behavior_mse_att_before",
        "stdw_behavior_mse_att_after",
        "stdw_behavior_mse_depth_before",
        "stdw_behavior_mse_depth_after",
        "stdw_action_delta_mse",
        "stdw_target_mse_before",
        "stdw_target_mse_after",
        "stdw_target_mse_after_roll_only",
        "stdw_target_mse_after_pitch_only",
        "stdw_target_mse_after_yaw_only",
        "stdw_target_mse_after_roll_pitch",
        "stdw_target_mse_after_roll_yaw",
        "stdw_target_mse_after_pitch_yaw",
        "stdw_target_mse_att_before",
        "stdw_target_mse_att_after",
        "stdw_target_mse_depth_before",
        "stdw_target_mse_depth_after",
        "stdw_anchor_mse_to_ref",
        "stdw_anchor_mse_to_policy",
        "stdw_anchor_mse_to_opr",
        "stdw_anchor_mse_att_to_policy",
        "stdw_anchor_mse_depth_to_policy",
        "stdw_anchor_mse_att_to_opr",
        "stdw_anchor_mse_depth_to_opr",
        "stdw_anchor_delta_att_norm_to_policy",
        "stdw_anchor_delta_depth_abs_to_policy",
        "stdw_zeta_write_scale",
        "stdw_action_bridge_residual_scale",
        "stdw_action_bridge_residual_clip",
        "stdw_action_bridge_upstream_mode",
        "stdw_reduced_action_anchor_enable",
        "stdw_reduced_action_anchor_scale",
        "stdw_reduced_action_anchor_clip",
        "stdw_reduced_action_anchor_channels",
        "stdw_reduced_action_anchor_geo_residual_scale",
        "stdw_reduced_action_anchor_sswp_sign_enable",
        "stdw_reduced_action_anchor_dual_source_gate",
        "stdw_reduced_action_anchor_sswp_beta",
        "stdw_reduced_action_anchor_consensus_gate",
        "stdw_reduced_action_anchor_consensus_preferred_sign",
        "stdw_bridge_residual_att_norm",
        "stdw_bridge_residual_depth_abs",
        "fast_bridge_residual_att_norm",
        "fast_bridge_residual_depth_abs",
        "fast_reduced_action_anchor_att_norm",
        "fast_reduced_action_anchor_depth_abs",
        "fast_reduced_action_anchor_consensus_changed_frac",
        "fast_reduced_action_anchor_raw_sswp_match_frac",
        "fast_reduced_action_anchor_raw_track_match_frac",
        "fast_reduced_action_anchor_sswp_track_agree_frac",
        "stdw_write_progress_att_ratio",
        "stdw_write_progress_depth_ratio",
        "stdw_tgt_action_roll_abs_before",
        "stdw_tgt_action_pitch_abs_before",
        "stdw_tgt_action_yaw_abs_before",
        "stdw_tgt_action_depth_abs_before",
        "stdw_update_delta_action_roll_abs",
        "stdw_update_delta_action_pitch_abs",
        "stdw_update_delta_action_yaw_abs",
        "stdw_update_delta_action_depth_abs_tgt",
        "stdw_zeta_to_action_gain_roll",
        "stdw_zeta_to_action_gain_pitch",
        "stdw_zeta_to_action_gain_yaw",
        "stdw_zeta_to_action_gain_depth",
        "stdw_anchor_abs_mean",
        "stdw_anchor_abs_max",
        "stdw_action_bridge_delta_id_vs_policy_delta_mean_abs",
        "stdw_action_bridge_delta_id_vs_policy_sign_match_frac",
        "stdw_action_bridge_delta_id_vs_policy_clipped_mean_abs",
        "stdw_action_bridge_self_vs_policy_state_mean_abs",
        "stdw_action_bridge_abs_vs_policy_z_mean_abs",
        "stdw_l_tgt_space",
        "stdw_l_tgt_state_val",
        "stdw_z_match_norm_mean",
        "stdw_phi_pred_norm_mean",
        "stdw_l_tgt_normalize_denom",
        "stdw_state_anchor_source",
        "stdw_fm_bridge_alpha",
        "stdw_fm_bridge_curvature",
        "stdw_fm_bridge_shift_norm_mean",
        "stdw_fm_bridge_shift_norm_p95",
        "stdw_update_target",
        "stdw_target_domain_mode",
        "stdw_zeta_multiplier_roll",
        "stdw_zeta_multiplier_pitch",
        "stdw_zeta_multiplier_yaw",
        "stdw_zeta_multiplier_depth",
        "stdw_zeta_delta_norm",
        "pseudo_action",
        "pseudo_action_delta_norm",
        "pseudo_action_delta_abs_mean",
        "pseudo_action_action_corr",
        "pseudo_action_sign_flip_rate",
        "phase4a_signal_probe",
        "phase4a_legacy_equals_clipped_action",
        "phase4a_pseudo_to_clipped_action_max_abs",
        "phase4a_action_out_of_unit_channel_fraction",
        "phase4a_action_to_clipped_action_delta_norm",
        "phase4a_pseudo_target_clip_channel_fraction",
        "phase4a_sswp_anchor",
        "phase4a_sswp_valid",
        "phase4a_sswp_delta_norm",
        "phase4a_sswp_delta_abs_mean",
        "phase4a_sswp_action_corr",
        "phase4a_sswp_equals_clipped_action",
        "phase4a_sswp_to_clipped_action_max_abs",
        "phase4a_sswp_target_clip_channel_fraction",
        "phase4a_sswp_action_out_of_unit_channel_fraction",
        "phase4a_descent_anchor",
        "phase4a_descent_valid",
        "phase4a_descent_delta_norm",
        "phase4a_descent_delta_abs_mean",
        "phase4a_descent_action_corr",
        "phase4a_descent_equals_clipped_action",
        "phase4a_descent_to_clipped_action_max_abs",
        "phase4a_descent_target_clip_channel_fraction",
        "phase4a_descent_action_out_of_unit_channel_fraction",
        "phase4a_descent_triggered",
        "phase4a_descent_align",
        "stdw_dir_guard_pass_rate",
        "stdw_dir_guard_align",
        "stdw_direction_gate_source",
        "stdw_direction_gate_dot",
        "stdw_direction_gate_dot_att",
        "stdw_direction_gate_dot_depth",
        "stdw_update_delta_action_att_norm",
        "stdw_update_delta_action_depth_abs",
        "stdw_zeta_delta_roll",
        "stdw_zeta_delta_pitch",
        "stdw_zeta_delta_yaw",
        "stdw_zeta_delta_depth",
        "stdw_depth_guard_active",
        "stdw_depth_guard_blocked",
        "stdw_depth_guard_old_multiplier",
        "stdw_depth_guard_new_multiplier",
        "task_a_depth_failsafe_mode",
        "task_a_depth_failsafe_active",
        "task_a_depth_failsafe_depth_v1",
        "task_a_depth_failsafe_delta_norm",
        "stdw_slow_loop_dry_run",
        "stdw_preserve_rng",
        "policy_training_mode",
        "policy_param_l2_from_start",
        "fast_action_ref_mse",
        "fast_action_ref_abs_max",
        "fast_bridge_residual_att_norm",
        "fast_bridge_residual_depth_abs",
        "boundary_submersion_ratio",
        "boundary_residual_dB",
        "boundary_ground_mag",
        "control_effort",
        "trigger_gate_silenced",
        "episode_reset",
        "domain_bias",
        "fluid_vx",
        "fluid_vy",
        "fluid_vz",
        "volume_mean",
        "des_roll",
        "des_pitch",
        "des_yaw",
        "des_depth",
        "des_depth_v1",
        "true_x",
        "true_y",
        "true_z",
        "true_depth_v1",
        "true_roll",
        "true_pitch",
        "true_yaw",
        "true_pose",
        "executed_action",
        "runtime_control_logged",
        "runtime_pid_value",
        "runtime_pid_roll",
        "runtime_pid_pitch",
        "runtime_pid_yaw",
        "runtime_pid_depth",
        "runtime_motor_raw",
        "runtime_motor_clipped",
        "runtime_motor_count",
        "runtime_motor_saturation_ratio",
        "runtime_motor_abs_max_raw",
        "runtime_motor_abs_max_clipped",
        "runtime_geo_zeta1",
        "runtime_geo_zeta1_roll",
        "runtime_geo_zeta1_pitch",
        "runtime_geo_zeta1_yaw",
        "phase56_runtime_binding",
        "phase56_runtime_binding_ready",
        "phase56_runtime_target_alpha",
        "fm_path_curvature_runtime",
        "state_only_marginal_error_runtime",
        "phase56_runtime_state",
        "phase56_runtime_state_transition",
        "phase56_runtime_execution_hooks",
        "phase56_runtime_allows_update",
        "phase56_runtime_freeze_applied",
        "phase56_runtime_clear_freeze_applied",
        "phase56_runtime_zero_drift_applied",
        "phase56_runtime_requests_reset",
        "phase56_runtime_state_age",
        "phase56_runtime_cycle_id",
        "phase56_runtime_cycle_step",
        "phase56_runtime_active_age",
        "phase56_runtime_frozen_age",
        "phase56_runtime_fallback_age",
        "phase56_runtime_reset_age",
        "phase56_runtime_reset_to_rearm_latency",
        "phase56_curvature_relative_enabled",
        "phase56_curvature_baseline_source",
        "phase56_curvature_baseline_window_label",
        "phase56_curvature_baseline_p95",
        "phase56_curvature_baseline_p99",
        "phase56_curvature_minus_p95",
        "phase56_curvature_over_p95",
        "phase56_curvature_watch",
        "phase56_curvature_stress",
        "phase56_curvature_watch_window_count",
        "phase56_curvature_stress_window_count",
        "phase56_curvature_window_size",
        "phase56_curvature_nonbinding_state",
        "phase56_curvature_scope_caveat",
        "com_to_cob_offset_x",
        "com_to_cob_offset_y",
        "com_to_cob_offset_z",
        # Scenario / schedule snapshot fields (filled when --scenario is set).
        "scenario",
        "embodiment",
        "disturbance_mode",
        "episode_id",
        "episode_start_step",
        "episode_length_steps",
        "episode_branch_at_start",
        "episode_branch_at_reset",
        "episode_reset_reason",
        "reference_mode_runtime",
        "mixed_reference_branch",
        "mixed_reference_is_flip",
        "amp_x",
        "amp_y",
        "amp_z",
        "noise_std_eff",
        "fault_active",
        "fault_efficiency_min",
    ]
    logger = STDWCSVLogger(csv_path, fieldnames)

    print("## EVALUATION LOG ## STDW (new) adaptation started")
    obs, _ = env.get_observations()
    final_mse_window: deque = deque(maxlen=int(args_cli.final_mse_window))
    convergence_step: Optional[int] = None
    convergence_streak = 0
    nonfinite_guard_count = 0
    first_nonfinite_step: Optional[int] = None
    reset_count = 0
    slow_loop_triggers = 0
    gate_silenced_count = 0
    lyapunov_block_count = 0
    lyapunov_zero_drift_count = 0
    lyapunov_freeze_drift_count = 0
    stdw_safety_state = "NORMAL"
    stdw_safety_transition_count = 0
    stdw_suspect_enter_count = 0
    stdw_fallback_enter_count = 0
    stdw_recover_count = 0
    stdw_guard_harm_streak = 0
    stdw_guard_clear_streak = 0
    stdw_fallback_step: Optional[int] = None
    stdw_update_accepted_count = 0
    stdw_update_rejected_count = 0
    stdw_last_reject_reason = ""
    stdw_dir_guard_blocked_count = 0
    phase4a_sswp_ema: Optional[torch.Tensor] = None
    task_a_depth_failsafe_sswp_ema: Optional[torch.Tensor] = None
    task_a_depth_failsafe_latched = False
    task_a_depth_failsafe_active_count = 0
    task_a_depth_failsafe_delta_norm_sum = 0.0
    phase56_runtime_bundle: Optional[dict[str, object]] = None
    phase56_runtime_binding_ready = False
    phase56_runtime_binding_error = ""
    phase56_runtime_state = "DISABLED"
    phase56_runtime_state_age = 0
    phase56_runtime_recovery_streak = 0
    phase56_runtime_state_counts: Dict[str, int] = {}
    phase56_runtime_state_transition_count = 0
    phase56_runtime_execution_blocked_count = 0
    phase56_runtime_freeze_apply_count = 0
    phase56_runtime_clear_freeze_count = 0
    phase56_runtime_zero_drift_count = 0
    phase56_runtime_reset_request_count = 0
    phase56_runtime_wake_count = 0
    phase56_runtime_sleep_count = 0
    phase56_runtime_completed_cycle_count = 0
    phase56_runtime_cycle_id = 0
    phase56_runtime_cycle_start_step: Optional[int] = None
    phase56_runtime_active_entry_step: Optional[int] = None
    phase56_runtime_frozen_entry_step: Optional[int] = None
    phase56_runtime_fallback_entry_step: Optional[int] = None
    phase56_runtime_reset_entry_step: Optional[int] = None
    phase56_runtime_last_reset_step: Optional[int] = None
    phase56_runtime_last_reset_to_rearm_latency = float("nan")
    phase56_runtime_active_durations: list[int] = []
    phase56_runtime_frozen_durations: list[int] = []
    phase56_runtime_fallback_durations: list[int] = []
    phase56_runtime_reset_durations: list[int] = []
    phase56_runtime_cycle_durations: list[int] = []
    phase56_runtime_reset_to_rearm_latencies: list[int] = []
    phase56_curvature_watch_history: deque = deque(maxlen=max(int(args_cli.phase56_curvature_window_size), 1))
    phase56_curvature_stress_history: deque = deque(maxlen=max(int(args_cli.phase56_curvature_window_size), 1))
    phase56_curvature_nonbinding_state_counts: Dict[str, int] = {}
    current_episode_id = 0
    current_episode_start_step = 0
    _, current_episode_branch, _ = _runtime_reference_context(raw_env)
    prev_V: Optional[float] = None
    # Baseline compound-error tracker for relative stability threshold (5.2 fix).
    # Collected over the pre-drift window steps in [0, drift_start_step). After the
    # window closes we freeze the mean and use max(abs_thr, rel * baseline) as the
    # effective threshold for convergence detection.
    baseline_err_sum: float = 0.0
    baseline_err_count: int = 0
    baseline_err_mean: Optional[float] = None
    effective_stability_threshold: float = float(args_cli.stability_threshold)

    if bool(args_cli.phase56_runtime_binding):
        bundle_dir = str(args_cli.phase56_runtime_bundle_dir) if args_cli.phase56_runtime_bundle_dir else ""
        if bundle_dir:
            try:
                phase56_runtime_bundle = load_phase56_runtime_bundle(
                    bundle_dir,
                    device=str(args_cli.phase56_runtime_device),
                )
                phase56_runtime_bundle["feature_set"] = str(args_cli.phase56_runtime_feature_set)
                phase56_runtime_bundle["fm_profile"] = str(args_cli.phase56_runtime_fm_profile)
                phase56_runtime_bundle["device"] = str(args_cli.phase56_runtime_device)
                phase56_runtime_binding_ready = True
                phase56_runtime_state = "NOMINAL_LOCKED"
                print(
                    "[PHASE56-RUNTIME] loaded bundle "
                    f"bundle_dir={bundle_dir} "
                    f"target_alpha={phase56_runtime_bundle.get('target_alpha')} "
                    f"context_gate={phase56_runtime_bundle.get('context_gate')}",
                    flush=True,
                )
            except Exception as exc:
                phase56_runtime_binding_error = str(exc)
                phase56_runtime_state = "BINDING_NOT_READY"
                print(f"[WARN] Phase 5/6 live runtime binding disabled: {exc}", flush=True)
        elif not args_cli.phase56_runtime_reference_csv:
            phase56_runtime_binding_error = "missing --phase56_runtime_reference_csv or --phase56_runtime_bundle_dir"
            phase56_runtime_state = "BINDING_NOT_READY"
            print("[WARN] Phase 5/6 live runtime binding requested without reference csv/bundle.", flush=True)
        else:
            try:
                phase56_runtime_bundle = _phase56_prepare_live_bundle(
                    args_cli.phase56_runtime_reference_csv,
                    feature_set=str(args_cli.phase56_runtime_feature_set),
                    context_gate=str(args_cli.phase56_runtime_context_gate),
                    fm_profile=str(args_cli.phase56_runtime_fm_profile),
                    max_samples=int(args_cli.phase56_runtime_max_samples),
                    target_alpha=float(args_cli.phase56_runtime_target_alpha),
                    device=str(args_cli.phase56_runtime_device),
                )
                phase56_runtime_binding_ready = True
                phase56_runtime_state = "NOMINAL_LOCKED"
                print(
                    "[PHASE56-RUNTIME] live bundle ready "
                    f"feature_set={args_cli.phase56_runtime_feature_set} "
                    f"context_gate={args_cli.phase56_runtime_context_gate} "
                    f"fm_profile={args_cli.phase56_runtime_fm_profile} "
                    f"target_alpha={phase56_runtime_bundle.get('target_alpha')} "
                    f"reference_csv={args_cli.phase56_runtime_reference_csv}",
                    flush=True,
                )
            except Exception as exc:
                phase56_runtime_binding_error = str(exc)
                phase56_runtime_state = "BINDING_NOT_READY"
                print(f"[WARN] Phase 5/6 live runtime binding disabled: {exc}", flush=True)

    state_match_fm_bridge_bundle: Optional[dict[str, object]] = (
        phase56_runtime_bundle if phase56_runtime_binding_ready else None
    )
    state_match_fm_bridge_alpha = (
        float(args_cli.stdw_fm_bridge_alpha)
        if args_cli.stdw_fm_bridge_alpha is not None
        else float(
            state_match_fm_bridge_bundle.get("target_alpha", args_cli.phase56_runtime_target_alpha)
            if isinstance(state_match_fm_bridge_bundle, dict)
            else args_cli.phase56_runtime_target_alpha
        )
    )
    state_match_z_source = str(args_cli.state_match_z_source)
    if state_match_z_source == "fm_midpoint":
        if state_match_kit is None and args_cli.l_tgt_space != "action_bridge":
            raise SystemExit("--state_match_z_source=fm_midpoint requires --l_tgt_space=state_* and --state_match_proxy (or action_bridge).")
        if state_match_fm_bridge_bundle is None:
            bridge_bundle_dir = str(args_cli.phase56_runtime_bundle_dir) if args_cli.phase56_runtime_bundle_dir else ""
            if bridge_bundle_dir:
                try:
                    state_match_fm_bridge_bundle = load_phase56_runtime_bundle(
                        bridge_bundle_dir,
                        device=str(args_cli.phase56_runtime_device),
                    )
                    state_match_fm_bridge_bundle["feature_set"] = str(args_cli.phase56_runtime_feature_set)
                    state_match_fm_bridge_bundle["fm_profile"] = str(args_cli.phase56_runtime_fm_profile)
                    state_match_fm_bridge_bundle["device"] = str(args_cli.phase56_runtime_device)
                except Exception as exc:
                    raise SystemExit(f"--state_match_z_source=fm_midpoint failed to load Phase56 bundle: {exc}") from exc
            elif args_cli.phase56_runtime_reference_csv:
                try:
                    state_match_fm_bridge_bundle = _phase56_prepare_live_bundle(
                        args_cli.phase56_runtime_reference_csv,
                        feature_set=str(args_cli.phase56_runtime_feature_set),
                        context_gate=str(args_cli.phase56_runtime_context_gate),
                        fm_profile=str(args_cli.phase56_runtime_fm_profile),
                        max_samples=int(args_cli.phase56_runtime_max_samples),
                        target_alpha=float(args_cli.phase56_runtime_target_alpha),
                        device=str(args_cli.phase56_runtime_device),
                    )
                except Exception as exc:
                    raise SystemExit(f"--state_match_z_source=fm_midpoint failed to prepare Phase56 bundle: {exc}") from exc
            else:
                raise SystemExit(
                    "--state_match_z_source=fm_midpoint requires --phase56_runtime_bundle_dir "
                    "or --phase56_runtime_reference_csv. Prefer an obs/state-space bundle whose "
                    "feature_dim matches --state_match_proxy state_dim."
                )

        norm = state_match_fm_bridge_bundle.get("norm") if isinstance(state_match_fm_bridge_bundle, dict) else None
        if not isinstance(norm, dict) or "mean" not in norm:
            raise SystemExit("--state_match_z_source=fm_midpoint loaded a malformed Phase56 bundle.")
        fm_dim = int(np.asarray(norm["mean"], dtype=np.float32).reshape(-1).shape[0])
        expected_dim = int(state_match_kit.state_dim) if state_match_kit is not None else int(inv_proxy_model.state_dim)
        if expected_dim != fm_dim:
            raise SystemExit(
                "--state_match_z_source=fm_midpoint requires Phase56 bundle feature_dim "
                f"({fm_dim}) == proxy state_dim ({expected_dim}). "
                "Use an obs12/native-state FM bundle rather than a core6 telemetry bundle."
            )
        state_match_fm_bridge_alpha = (
            float(args_cli.stdw_fm_bridge_alpha)
            if args_cli.stdw_fm_bridge_alpha is not None
            else float(state_match_fm_bridge_bundle.get("target_alpha", args_cli.phase56_runtime_target_alpha))
        )
        print(
            "[INFO] Phase-8 FM midpoint z_bridge active: "
            f"alpha={state_match_fm_bridge_alpha:.3f} "
            f"feature_dim={fm_dim} source={args_cli.phase56_runtime_bundle_dir or args_cli.phase56_runtime_reference_csv}",
            flush=True,
        )
    elif state_match_z_source == "buffer_next_state":
        if state_match_kit is None:
            raise SystemExit(
                "--state_match_z_source=buffer_next_state requires --l_tgt_space=state_* and --state_match_proxy."
            )
        print(
            "[INFO] Phase-8 buffer_next_state z_bridge active: replay next_states used as "
            "diagnostic one-step targets (FM/Sinkhorn target generation bypassed).",
            flush=True,
        )

    print(f"[INFO] Entering step loop, total_steps={args_cli.total_steps}", flush=True)
    for step in range(args_cli.total_steps):
        if not simulation_app.is_running():
            break

        # ---- fast loop ----
        with torch.no_grad():
            fast_reduced_action_anchor_consensus_changed_frac = float("nan")
            fast_reduced_action_anchor_raw_sswp_match_frac = float("nan")
            fast_reduced_action_anchor_raw_track_match_frac = float("nan")
            fast_reduced_action_anchor_sswp_track_agree_frac = float("nan")
            normalized = obs_normalizer(obs)
            policy_action = _policy_forward_eval(policy, normalized).detach()
            ref_action = (
                _policy_forward_eval(policy_ref, normalized).detach()
                if args_cli.analytic_action_mode != "off" or args_cli.log_policy_diagnostics
                else None
            )
            action = _apply_analytic_action_shim(obs, policy_action, ref_action, args_cli).detach()
            if stdw_zeta_delta is not None and stdw_runtime_action_bridge_delta is not None:
                fast_bridge_multiplier = _zeta4_multipliers(
                    stdw_zeta_delta, float(args_cli.stdw_zeta_bound)
                ).detach()
                action, fast_bridge_residual_term = _apply_deployed_action_bridge_residual(
                    action=action,
                    residual_basis=stdw_runtime_action_bridge_delta,
                    deployed_multiplier=fast_bridge_multiplier,
                    residual_scale=float(args_cli.stdw_action_bridge_residual_scale),
                    residual_clip=float(args_cli.stdw_action_bridge_residual_clip),
                )
            else:
                fast_bridge_residual_term = torch.zeros_like(action)
            reduced_anchor_tracking_dir = None
            if bool(args_cli.stdw_reduced_action_anchor_consensus_gate) or bool(
                args_cli.stdw_reduced_action_anchor_consensus_preferred_sign
            ):
                reduced_anchor_tracking_dir = _tracking_error_direction(
                    env,
                    batch_shape=(action.shape[0], 4),
                    device=action.device,
                    dtype=action.dtype,
                    depth_reference_frame=str(args_cli.depth_reference_frame),
                    depth_surface_z=float(args_cli.depth_surface_z),
                )
            if stdw_runtime_reduced_action_anchor is not None:
                (
                    action,
                    fast_reduced_action_anchor_term,
                    fast_reduced_action_anchor_stats,
                ) = _apply_deployed_reduced_action_anchor(
                    action=action,
                    residual_basis=stdw_runtime_reduced_action_anchor,
                    anchor_scale=float(args_cli.stdw_reduced_action_anchor_scale),
                    anchor_clip=float(args_cli.stdw_reduced_action_anchor_clip),
                    channels=str(args_cli.stdw_reduced_action_anchor_channels),
                    sswp_sign_ema=stdw_reduced_action_anchor_sswp_ema,
                    tracking_error_dir=reduced_anchor_tracking_dir,
                    use_sswp_sign=bool(args_cli.stdw_reduced_action_anchor_sswp_sign_enable),
                    dual_source_gate=bool(args_cli.stdw_reduced_action_anchor_dual_source_gate),
                    consensus_gate=bool(args_cli.stdw_reduced_action_anchor_consensus_gate),
                    consensus_preferred_sign=bool(
                        args_cli.stdw_reduced_action_anchor_consensus_preferred_sign
                    ),
                )
            else:
                fast_reduced_action_anchor_term = torch.zeros_like(action)
                fast_reduced_action_anchor_stats = {
                    "consensus_changed_frac": float("nan"),
                    "raw_sswp_match_frac": float("nan"),
                    "raw_track_match_frac": float("nan"),
                    "sswp_track_agree_frac": float("nan"),
                }
            (
                action,
                task_a_depth_failsafe_active,
                task_a_depth_failsafe_delta_norm,
                task_a_depth_failsafe_depth_v1,
                task_a_depth_failsafe_sswp_ema,
                task_a_depth_failsafe_latched,
            ) = _apply_task_a_depth_failsafe_shim(
                raw_obs=obs,
                action=action,
                env=env,
                args=args_cli,
                depth_reference_frame=str(args_cli.depth_reference_frame),
                depth_surface_z=float(args_cli.depth_surface_z),
                sswp_ema=task_a_depth_failsafe_sswp_ema,
                latched=task_a_depth_failsafe_latched,
            )
            if task_a_depth_failsafe_active:
                task_a_depth_failsafe_active_count += 1
                task_a_depth_failsafe_delta_norm_sum += float(task_a_depth_failsafe_delta_norm)
            if args_cli.log_policy_diagnostics:
                fast_action_ref_mse = float(((action - ref_action) ** 2).mean().item())
                fast_action_ref_abs_max = float((action - ref_action).abs().max().item())
            else:
                fast_action_ref_mse = float("nan")
                fast_action_ref_abs_max = float("nan")
            fast_bridge_residual_att_norm = float(
                fast_bridge_residual_term[:, :3].norm(dim=-1).mean().item()
            ) if fast_bridge_residual_term.shape[-1] >= 3 else float("nan")
            fast_bridge_residual_depth_abs = float(
                fast_bridge_residual_term[:, 3].abs().mean().item()
            ) if fast_bridge_residual_term.shape[-1] >= 4 else float("nan")
            fast_reduced_action_anchor_att_norm = float(
                fast_reduced_action_anchor_term[:, :3].norm(dim=-1).mean().item()
            ) if fast_reduced_action_anchor_term.shape[-1] >= 3 else float("nan")
            fast_reduced_action_anchor_depth_abs = float(
                fast_reduced_action_anchor_term[:, 3].abs().mean().item()
            ) if fast_reduced_action_anchor_term.shape[-1] >= 4 else float("nan")
            fast_reduced_action_anchor_consensus_changed_frac = float(
                fast_reduced_action_anchor_stats["consensus_changed_frac"]
            )
            fast_reduced_action_anchor_raw_sswp_match_frac = float(
                fast_reduced_action_anchor_stats["raw_sswp_match_frac"]
            )
            fast_reduced_action_anchor_raw_track_match_frac = float(
                fast_reduced_action_anchor_stats["raw_track_match_frac"]
            )
            fast_reduced_action_anchor_sswp_track_agree_frac = float(
                fast_reduced_action_anchor_stats["sswp_track_agree_frac"]
            )
        policy_param_l2_from_start = (
            _policy_param_l2(policy, theta_pre) if args_cli.log_policy_diagnostics else float("nan")
        )
        if not torch.isfinite(action).all():
            nonfinite_guard_count += 1
            first_nonfinite_step = step if first_nonfinite_step is None else first_nonfinite_step
            reset_count += 1
            obs = _reset_wrapper_env(env)
            current_episode_id += 1
            current_episode_start_step = int(step + 1)
            _, current_episode_branch, _ = _runtime_reference_context(raw_env)
            print(f"## EVALUATION LOG ## Step {step}: nonfinite_action_guard_reset")
            continue

        reference_mode_pre, mixed_reference_branch_pre, mixed_reference_is_flip_pre = _runtime_reference_context(raw_env)
        next_obs, reward, dones, extras = env.step(action)

        # Gradual disturbance injection (only when --scenario was set).
        if schedule is not None:
            try:
                schedule_snapshot = schedule.tick(step)
            except Exception as exc:
                print(f"[WARN] schedule.tick failed at step {step}: {exc}")
                schedule_snapshot = {}
        else:
            schedule_snapshot = {}
        injected = stdw_wrapper.last_extras or {}
        if isinstance(extras, dict):
            for key in ("stdw_raw_error", "stdw_filt_error", "stdw_drift_fraction", "stdw_step", "stdw_V", "stdw_mask"):
                if key in extras:
                    injected[key] = extras[key]
        raw_err = float(injected.get("stdw_raw_error", 0.0))
        filt_err = float(injected.get("stdw_filt_error", raw_err))
        drift_frac = float(injected.get("stdw_drift_fraction", stdw_wrapper.current_drift()))
        V_t = float(injected.get("stdw_V", 0.0))
        stdw_mask_val = float(injected.get("stdw_mask", 1.0))
        stdw_dV = float(injected.get("stdw_dV", float("nan")))
        lyapunov_pass = float(injected.get("stdw_lyap_pass", stdw_mask_val))
        lyapunov_pass_rate = float(injected.get("stdw_lyap_pass_rate_window", 1.0))
        lyapunov_safety_block = float(injected.get("stdw_safety_block", 0.0))
        lyapunov_safety_reason = str(injected.get("stdw_safety_reason", ""))
        is_lyapunov_blocked = bool(lyapunov_safety_block > 0.0)
        stdw_safety_transition = ""
        if is_lyapunov_blocked:
            lyapunov_block_count += 1
            stdw_guard_harm_streak += 1
            stdw_guard_clear_streak = 0
        else:
            stdw_guard_harm_streak = 0
            stdw_guard_clear_streak += 1

        if stdw_safety_state == "NORMAL" and is_lyapunov_blocked:
            stdw_safety_state = "SUSPECT"
            stdw_safety_transition = "NORMAL->SUSPECT"
            stdw_safety_transition_count += 1
            stdw_suspect_enter_count += 1
            stdw_wrapper.freeze_current_drift()
            lyapunov_freeze_drift_count += 1
        elif stdw_safety_state == "SUSPECT":
            if (
                is_lyapunov_blocked
                and stdw_guard_harm_streak >= max(int(args_cli.lyapunov_guard_confirm_steps), 1)
            ):
                stdw_safety_state = "FALLBACK"
                stdw_safety_transition = "SUSPECT->FALLBACK"
                stdw_safety_transition_count += 1
                stdw_fallback_enter_count += 1
                stdw_fallback_step = step if stdw_fallback_step is None else stdw_fallback_step
                if args_cli.lyapunov_guard_action == "zero_drift":
                    stdw_wrapper.target_drift = 0.0
                    lyapunov_zero_drift_count += 1
                elif args_cli.lyapunov_guard_action == "freeze_drift":
                    stdw_wrapper.freeze_current_drift()
                    lyapunov_freeze_drift_count += 1
            elif (
                not is_lyapunov_blocked
                and stdw_guard_clear_streak >= max(int(args_cli.lyapunov_guard_recover_steps), 1)
            ):
                stdw_safety_state = "NORMAL"
                stdw_safety_transition = "SUSPECT->NORMAL"
                stdw_safety_transition_count += 1
                stdw_recover_count += 1
                stdw_wrapper.clear_drift_freeze()

        lyapunov_guard_blocks_slow_loop = stdw_safety_state in {"SUSPECT", "FALLBACK"}

        # ---- pseudo-action ----
        # 改良 2：在 pseudo_gain 上叠加 drift_frac 自适应衰减 + 修正量 clip 门控。
        #   pseudo_gain(ρ) = pseudo_gain_0 * (1 - pseudo_decay * ρ)
        #   correction      = clip(pseudo_gain(ρ) * J^-1 * Δu, -gate, +gate)
        a_pseudo = _build_pseudo_action_target(
            obs,
            action,
            stdw_wrapper,
            env,
            drift_frac,
            args_cli,
        )
        policy_action_list = _tensor_1d_list(action)
        pseudo_action_list = _tensor_1d_list(a_pseudo)
        pseudo_delta = [p - a for p, a in zip(pseudo_action_list, policy_action_list)]
        pseudo_action_delta_norm = float(np.linalg.norm(np.asarray(pseudo_delta, dtype=float)))
        pseudo_action_delta_abs_mean = float(np.mean(np.abs(np.asarray(pseudo_delta, dtype=float)))) if pseudo_delta else float("nan")
        pseudo_action_action_corr = _safe_vector_corr(policy_action_list, pseudo_action_list)
        pseudo_action_sign_flip_rate = (
            float(np.mean([1.0 if (p * a) < 0.0 else 0.0 for p, a in zip(pseudo_action_list, policy_action_list)]))
            if pseudo_delta
            else float("nan")
        )
        if bool(args_cli.phase4a_signal_probe) and pseudo_delta:
            action_arr = np.asarray(policy_action_list, dtype=float)
            pseudo_arr = np.asarray(pseudo_action_list, dtype=float)
            clipped_action_arr = np.clip(action_arr, -1.0, 1.0)
            pseudo_to_clip_abs = np.abs(pseudo_arr - clipped_action_arr)
            phase4a_pseudo_to_clip_max_abs = float(np.max(pseudo_to_clip_abs))
            phase4a_legacy_equals_clipped_action = float(phase4a_pseudo_to_clip_max_abs <= 1.0e-6)
            phase4a_action_oob_fraction = float(np.mean(np.abs(action_arr) > 1.0))
            phase4a_action_to_clip_delta_norm = float(np.linalg.norm(action_arr - clipped_action_arr))
            phase4a_pseudo_target_clip_fraction = float(np.mean(np.abs(pseudo_arr) >= 0.999))
        else:
            phase4a_pseudo_to_clip_max_abs = float("nan")
            phase4a_legacy_equals_clipped_action = float("nan")
            phase4a_action_oob_fraction = float("nan")
            phase4a_action_to_clip_delta_norm = float("nan")
            phase4a_pseudo_target_clip_fraction = float("nan")
        phase4a_sswp_contract = _phase4a_empty_anchor_contract("phase4a_sswp")
        phase4a_descent_contract = _phase4a_empty_anchor_contract("phase4a_descent")
        phase4a_descent_triggered = 0
        phase4a_descent_align = float("nan")
        if bool(args_cli.phase4a_signal_probe) and pseudo_delta:
            phase4a_runtime_control = _runtime_control_snapshot(env, True)
            runtime_pid = phase4a_runtime_control.get("runtime_pid_value", [])
            if isinstance(runtime_pid, list) and runtime_pid:
                runtime_pid_arr = np.asarray(runtime_pid, dtype=float)
                low_level_delta_arr = np.zeros_like(action_arr)
                count = min(low_level_delta_arr.size, runtime_pid_arr.size)
                low_level_delta_arr[:count] = runtime_pid_arr[:count]
                low_level_delta = torch.as_tensor(
                    low_level_delta_arr,
                    device=action.device,
                    dtype=action.dtype,
                )
                beta = min(max(float(args_cli.phase4a_sswp_beta), 0.0), 0.999999)
                if phase4a_sswp_ema is None or phase4a_sswp_ema.shape != low_level_delta.shape:
                    phase4a_sswp_ema = torch.zeros_like(low_level_delta)
                phase4a_sswp_ema = beta * phase4a_sswp_ema + (1.0 - beta) * low_level_delta
                sswp_delta = np.asarray(_tensor_1d_list(phase4a_sswp_ema), dtype=float)
                if sswp_delta.shape == action_arr.shape:
                    sswp_anchor = np.clip(action_arr - float(args_cli.phase4a_anchor_scale) * sswp_delta, -1.0, 1.0)
                    phase4a_sswp_contract = _phase4a_anchor_contract("phase4a_sswp", action_arr, sswp_anchor)

            analytic_anchor = _analytic_s_surface_action(
                obs,
                action_dim=action.shape[-1],
                depth_target=float(args_cli.analytic_depth_target),
                roll_pitch_action_lim=float(args_cli.analytic_roll_pitch_action_lim),
                yaw_action_lim=float(args_cli.analytic_yaw_action_lim),
                depth_action_lim=float(args_cli.analytic_depth_action_lim),
            )
            analytic_arr = np.asarray(_tensor_1d_list(analytic_anchor), dtype=float)
            descent_residual = analytic_arr - action_arr
            descent_residual = np.clip(
                descent_residual,
                -float(args_cli.phase4a_descent_residual_clip),
                float(args_cli.phase4a_descent_residual_clip),
            )
            descent_residual = float(args_cli.phase4a_descent_residual_scale) * descent_residual
            phase4a_descent_align = float(np.dot(descent_residual, analytic_arr - action_arr))
            lyapunov_failed = bool(
                is_lyapunov_blocked
                or (np.isfinite(stdw_dV) and float(stdw_dV) >= 0.0)
                or (np.isfinite(lyapunov_pass) and float(lyapunov_pass) < 0.5)
            )
            if lyapunov_failed and np.isfinite(phase4a_descent_align):
                phase4a_descent_triggered = 1
                descent_anchor = np.clip(action_arr + descent_residual, -1.0, 1.0)
                phase4a_descent_contract = _phase4a_anchor_contract(
                    "phase4a_descent",
                    action_arr,
                    descent_anchor,
                )

        # ---- buffer add (env_id=0) ----
        try:
            obs_row = obs[0] if obs.ndim > 1 else obs
            next_row = next_obs[0] if next_obs.ndim > 1 else next_obs
            action_row = action[0] if action.ndim > 1 else action
            pseudo_row = a_pseudo[0] if a_pseudo.ndim > 1 else a_pseudo
            reward_scalar = reward[0] if isinstance(reward, torch.Tensor) and reward.ndim > 0 else reward
            buffer.add(
                state=obs_row,
                action=action_row,
                pseudo_action=pseudo_row,
                reward=reward_scalar,
                next_state=next_row,
                error=filt_err if args_cli.enable_filter else raw_err,
                stdw_mask=stdw_mask_val,
                lyapunov_V=V_t,
                drift_frac=drift_frac,
                step=step,
            )
        except Exception as exc:
            print(f"[WARN] buffer.add failed at step {step}: {exc}")

        runtime_control_enabled = bool(args_cli.log_runtime_control) or bool(args_cli.phase56_runtime_binding)
        runtime_control = _runtime_control_snapshot(env, runtime_control_enabled)
        if bool(args_cli.stdw_reduced_action_anchor_enable) and (
            bool(args_cli.stdw_reduced_action_anchor_sswp_sign_enable)
            or bool(args_cli.stdw_reduced_action_anchor_dual_source_gate)
            or bool(args_cli.stdw_reduced_action_anchor_consensus_gate)
            or bool(args_cli.stdw_reduced_action_anchor_consensus_preferred_sign)
        ):
            runtime_pid = runtime_control.get("runtime_pid_value", [])
            if isinstance(runtime_pid, list) and runtime_pid:
                low_level_delta_arr = np.zeros(4, dtype=float)
                runtime_pid_arr = np.asarray(runtime_pid, dtype=float)
                count = min(low_level_delta_arr.size, runtime_pid_arr.size)
                low_level_delta_arr[:count] = runtime_pid_arr[:count]
                low_level_delta = torch.as_tensor(
                    low_level_delta_arr, device=runtime_device, dtype=torch.float32
                )
                beta = min(max(float(args_cli.stdw_reduced_action_anchor_sswp_beta), 0.0), 0.999999)
                if (
                    stdw_reduced_action_anchor_sswp_ema is None
                    or stdw_reduced_action_anchor_sswp_ema.shape != low_level_delta.shape
                ):
                    stdw_reduced_action_anchor_sswp_ema = torch.zeros_like(low_level_delta)
                stdw_reduced_action_anchor_sswp_ema = (
                    beta * stdw_reduced_action_anchor_sswp_ema
                    + (1.0 - beta) * low_level_delta
                )
        des_roll, des_pitch, des_yaw, des_depth = _get_desired_pose(env)
        true_x, true_y, true_z, true_roll, true_pitch, true_yaw = _get_true_pose(env)
        true_depth_v1 = float(_depth_to_v1(true_z))
        des_depth_v1 = float(_depth_to_v1(des_depth))
        depth_barrier = _depth_barrier_for_v1(true_depth_v1)
        phase56_runtime_row = _phase56_runtime_monitor_defaults(
            enabled=bool(args_cli.phase56_runtime_binding),
            ready=bool(phase56_runtime_binding_ready),
            target_alpha=(
                float(phase56_runtime_bundle["target_alpha"])
                if isinstance(phase56_runtime_bundle, dict) and "target_alpha" in phase56_runtime_bundle
                else float(args_cli.phase56_runtime_target_alpha)
            ),
            current_state=str(phase56_runtime_state),
        )
        phase56_execution_blocks_slow_loop = False
        phase56_requested_reset = False
        phase56_prev_state = str(phase56_runtime_state)
        if bool(args_cli.phase56_runtime_binding) and phase56_runtime_binding_ready and phase56_runtime_bundle is not None:
            phase56_feature_vector = _phase56_runtime_feature_vector(
                feature_columns=list(phase56_runtime_bundle["feature_columns"]),
                true_roll=float(true_roll),
                true_pitch=float(true_pitch),
                true_yaw=float(true_yaw),
                true_depth_v1=float(true_depth_v1),
                runtime_motor_saturation_ratio=float(runtime_control.get("runtime_motor_saturation_ratio", float("nan"))),
                runtime_motor_abs_max_raw=float(runtime_control.get("runtime_motor_abs_max_raw", float("nan"))),
                phase4a_sswp_delta_norm=float(phase4a_sswp_contract.get("phase4a_sswp_delta_norm", float("nan"))),
                phase4a_sswp_delta_abs_mean=float(phase4a_sswp_contract.get("phase4a_sswp_delta_abs_mean", float("nan"))),
                fault_efficiency_min=float(schedule_snapshot.get("fault_efficiency_min", float("nan"))),
                depth_barrier_penalty=float(depth_barrier["depth_barrier_penalty"]),
            )
            if phase56_feature_vector is not None:
                try:
                    (
                        phase56_runtime_row,
                        phase56_runtime_state,
                        phase56_runtime_recovery_streak,
                        phase56_runtime_state_age,
                    ) = _phase56_runtime_live_contract(
                        phase56_runtime_bundle,
                        phase56_feature_vector,
                        current_state=str(phase56_runtime_state),
                        state_age=int(phase56_runtime_state_age),
                        recovery_streak=int(phase56_runtime_recovery_streak),
                        lyapunov_pass=float(lyapunov_pass),
                        lyapunov_pass_rate_window=float(lyapunov_pass_rate),
                        depth_violation=float(depth_barrier["depth_violation"]),
                        runtime_motor_saturation_ratio=float(runtime_control.get("runtime_motor_saturation_ratio", float("nan"))),
                        fault_active=bool(schedule_snapshot.get("fault_active", False)),
                        include_marginal_trip=not bool(args_cli.phase56_runtime_execution_hooks),
                        frozen_min_dwell_steps=int(args_cli.phase56_runtime_frozen_min_dwell_steps),
                        frozen_recover_steps=int(args_cli.phase56_runtime_frozen_recover_steps),
                        fallback_dwell_steps=int(args_cli.phase56_runtime_fallback_dwell_steps),
                    )
                    phase56_exec = _phase56_runtime_execution_directives(
                        prev_state=phase56_prev_state,
                        current_state=str(phase56_runtime_state),
                        current_state_age=int(phase56_runtime_state_age),
                        reset_dwell_steps=int(args_cli.phase56_runtime_reset_dwell_steps),
                    )
                    phase56_runtime_row["phase56_runtime_allows_update"] = bool(phase56_exec["allows_update"])
                    phase56_runtime_row["phase56_runtime_requests_reset"] = bool(phase56_exec["requests_reset"])
                    if bool(args_cli.phase56_runtime_execution_hooks):
                        phase56_runtime_row["phase56_runtime_execution_hooks"] = True
                        phase56_runtime_row["phase56_runtime_freeze_applied"] = bool(phase56_exec["freeze_applied"])
                        phase56_runtime_row["phase56_runtime_clear_freeze_applied"] = bool(phase56_exec["clear_freeze_applied"])
                        phase56_runtime_row["phase56_runtime_zero_drift_applied"] = bool(phase56_exec["zero_drift_applied"])
                        if phase56_exec["freeze_applied"]:
                            stdw_wrapper.freeze_current_drift()
                            phase56_runtime_freeze_apply_count += 1
                        if phase56_exec["clear_freeze_applied"]:
                            stdw_wrapper.clear_drift_freeze()
                            phase56_runtime_clear_freeze_count += 1
                        if phase56_exec["zero_drift_applied"]:
                            stdw_wrapper.target_drift = 0.0
                            phase56_runtime_zero_drift_count += 1
                        if phase56_exec["requests_reset"]:
                            phase56_requested_reset = True
                            phase56_runtime_reset_request_count += 1
                        phase56_execution_blocks_slow_loop = not bool(phase56_exec["allows_update"])
                except Exception as exc:
                    phase56_runtime_binding_error = str(exc)
                    phase56_runtime_row = _phase56_runtime_monitor_defaults(
                        enabled=True,
                        ready=False,
                        target_alpha=float(args_cli.phase56_runtime_target_alpha),
                        current_state="BINDING_RUNTIME_ERROR",
                    )
                    phase56_runtime_state = "BINDING_RUNTIME_ERROR"
                    phase56_runtime_state_age = 1

        # ---- slow loop ----
        loss_total = 0.0
        loss_src_val = 0.0
        loss_tgt_val = 0.0
        loss_reg_val = 0.0
        stdw_update_accepted = 0
        stdw_update_rejected = 0
        stdw_acceptance_reason = ""
        stdw_behavior_mse_before = float("nan")
        stdw_behavior_mse_after = float("nan")
        stdw_behavior_mse_att_before = float("nan")
        stdw_behavior_mse_att_after = float("nan")
        stdw_behavior_mse_depth_before = float("nan")
        stdw_behavior_mse_depth_after = float("nan")
        stdw_action_delta_mse = float("nan")
        stdw_target_mse_before = float("nan")
        stdw_target_mse_after = float("nan")
        stdw_target_mse_after_roll_only = float("nan")
        stdw_target_mse_after_pitch_only = float("nan")
        stdw_target_mse_after_yaw_only = float("nan")
        stdw_target_mse_after_roll_pitch = float("nan")
        stdw_target_mse_after_roll_yaw = float("nan")
        stdw_target_mse_after_pitch_yaw = float("nan")
        stdw_target_mse_att_before = float("nan")
        stdw_target_mse_att_after = float("nan")
        stdw_target_mse_depth_before = float("nan")
        stdw_target_mse_depth_after = float("nan")
        stdw_anchor_mse_to_ref = float("nan")
        stdw_anchor_mse_to_policy = float("nan")
        stdw_anchor_mse_to_opr = float("nan")
        stdw_anchor_mse_att_to_policy = float("nan")
        stdw_anchor_mse_depth_to_policy = float("nan")
        stdw_anchor_mse_att_to_opr = float("nan")
        stdw_anchor_mse_depth_to_opr = float("nan")
        stdw_anchor_delta_att_norm_to_policy = float("nan")
        stdw_anchor_delta_depth_abs_to_policy = float("nan")
        stdw_zeta_write_scale = float(args_cli.stdw_zeta_write_scale)
        stdw_action_bridge_residual_scale = float(args_cli.stdw_action_bridge_residual_scale)
        stdw_action_bridge_residual_clip = float(args_cli.stdw_action_bridge_residual_clip)
        stdw_reduced_action_anchor_enable = bool(args_cli.stdw_reduced_action_anchor_enable)
        stdw_reduced_action_anchor_scale = float(args_cli.stdw_reduced_action_anchor_scale)
        stdw_reduced_action_anchor_clip = float(args_cli.stdw_reduced_action_anchor_clip)
        stdw_reduced_action_anchor_channels = str(args_cli.stdw_reduced_action_anchor_channels)
        stdw_bridge_residual_att_norm = float("nan")
        stdw_bridge_residual_depth_abs = float("nan")
        stdw_write_progress_att_ratio = float("nan")
        stdw_write_progress_depth_ratio = float("nan")
        stdw_tgt_action_roll_abs_before = float("nan")
        stdw_tgt_action_pitch_abs_before = float("nan")
        stdw_tgt_action_yaw_abs_before = float("nan")
        stdw_tgt_action_depth_abs_before = float("nan")
        stdw_update_delta_action_roll_abs = float("nan")
        stdw_update_delta_action_pitch_abs = float("nan")
        stdw_update_delta_action_yaw_abs = float("nan")
        stdw_update_delta_action_depth_abs_tgt = float("nan")
        stdw_zeta_to_action_gain_roll = float("nan")
        stdw_zeta_to_action_gain_pitch = float("nan")
        stdw_zeta_to_action_gain_yaw = float("nan")
        stdw_zeta_to_action_gain_depth = float("nan")
        stdw_anchor_abs_mean = float("nan")
        stdw_anchor_abs_max = float("nan")
        stdw_action_bridge_delta_id_vs_policy_delta_mean_abs = float("nan")
        stdw_action_bridge_delta_id_vs_policy_sign_match_frac = float("nan")
        stdw_action_bridge_delta_id_vs_policy_clipped_mean_abs = float("nan")
        stdw_action_bridge_self_vs_policy_state_mean_abs = float("nan")
        stdw_action_bridge_abs_vs_policy_z_mean_abs = float("nan")
        stdw_l_tgt_space = str(args_cli.l_tgt_space)
        stdw_l_tgt_state_val = float("nan")
        stdw_z_match_norm_mean = float("nan")
        stdw_phi_pred_norm_mean = float("nan")
        stdw_l_tgt_normalize_denom = float("nan")
        stdw_state_anchor_source = str(args_cli.state_match_z_source)
        stdw_fm_bridge_alpha = float("nan")
        stdw_fm_bridge_curvature = float("nan")
        stdw_fm_bridge_shift_norm_mean = float("nan")
        stdw_fm_bridge_shift_norm_p95 = float("nan")
        stdw_dir_guard_pass_rate = float("nan")
        stdw_dir_guard_align = float("nan")
        stdw_direction_gate_dot = float("nan")
        stdw_direction_gate_dot_att = float("nan")
        stdw_direction_gate_dot_depth = float("nan")
        stdw_update_delta_action_att_norm = float("nan")
        stdw_update_delta_action_depth_abs = float("nan")
        stdw_depth_guard_blocked = 0
        stdw_depth_guard_old_multiplier = float("nan")
        stdw_depth_guard_new_multiplier = float("nan")
        stdw_zeta_delta_roll = float("nan")
        stdw_zeta_delta_pitch = float("nan")
        stdw_zeta_delta_yaw = float("nan")
        stdw_zeta_delta_depth = float("nan")
        task_a_depth_failsafe_active = 0
        task_a_depth_failsafe_depth_v1 = float("nan")
        task_a_depth_failsafe_delta_norm = 0.0
        effective_batch_frac = 0.0
        triggered_slow = False
        gate_silenced = False
        slow_due = (
            args_cli.use_stdw
            and step % args_cli.slow_loop_interval == 0
            and len(buffer) >= args_cli.batch_size
        )
        # TAG: 仅当滤波复合误差达到阈值（或门限关闭）才允许激活慢环更新。
        is_triggered = True
        if args_cli.enable_trigger_gate:
            is_triggered = (filt_err >= args_cli.trigger_threshold)
        # Line 3: trust-as-trigger. Use the analytic S-surface action as a trust
        # signal on WHETHER to run the slow loop this step (never as a target
        # value). Only fire when the analytic and policy actions are directionally
        # consistent (cosine similarity over the first four channels >= threshold),
        # i.e. the physics prior trusts the current policy direction. Orthogonal to
        # the residual-value gates in _build_pseudo_action_target.
        if is_triggered and str(getattr(args_cli, "pseudo_trust_trigger", "off")) == "gate":
            try:
                depth_tgt = float(getattr(env.unwrapped.cfg, "starting_depth", float(args_cli.analytic_depth_target)))
                analytic_trust = _analytic_s_surface_action(
                    obs,
                    action_dim=action.shape[-1],
                    depth_target=depth_tgt,
                    roll_pitch_action_lim=float(args_cli.analytic_roll_pitch_action_lim),
                    yaw_action_lim=float(args_cli.analytic_yaw_action_lim),
                    depth_action_lim=float(args_cli.analytic_depth_action_lim),
                )
                a_vec = action[0, 0:4] if action.ndim > 1 else action[0:4]
                d_vec = analytic_trust[0, 0:4] if analytic_trust.ndim > 1 else analytic_trust[0:4]
                cos_sim = torch.nn.functional.cosine_similarity(
                    a_vec.reshape(1, -1).float(), d_vec.reshape(1, -1).float(), dim=-1, eps=1.0e-8
                )
                cos_val = float(cos_sim.item())
                if not math.isfinite(cos_val) or cos_val < float(getattr(args_cli, "pseudo_trust_align_threshold", 0.0)):
                    is_triggered = False
            except Exception as exc:
                print(f"[WARN] pseudo_trust_trigger eval failed at step {step}: {exc}")
        if slow_due and lyapunov_guard_blocks_slow_loop:
            gate_silenced = True
        elif slow_due and not is_triggered:
            gate_silenced = True
            gate_silenced_count += 1
        elif slow_due and phase56_execution_blocks_slow_loop:
            gate_silenced = True
            gate_silenced_count += 1
            phase56_runtime_execution_blocked_count += 1
        if slow_due and is_triggered and not lyapunov_guard_blocks_slow_loop and not phase56_execution_blocks_slow_loop:
            triggered_slow = True
            slow_loop_triggers += 1
            rho = float(drift_frac)
            rng_state = _capture_torch_rng_state() if args_cli.preserve_rng_around_slow_loop else None
            try:
                B_src, B_tgt, _ = buffer.sample_pair(
                    args_cli.batch_size,
                    rho,
                    use_quantile_filter=args_cli.use_quantile_filter,
                    discard_ratio=args_cli.discard_ratio,
                    target_domain_mode=str(args_cli.stdw_target_domain_mode),
                    target_intermediate_fraction=float(args_cli.stdw_target_intermediate_frac),
                )
                a_src_policy = _policy_forward_train(policy, obs_normalizer(B_src["states"]))
                a_tgt_policy = _policy_forward_train(policy, obs_normalizer(B_tgt["states"]))
                with torch.no_grad():
                    a_src_ref_for_shim = _policy_forward_eval(policy_ref, obs_normalizer(B_src["states"]))
                    a_tgt_ref_for_shim = _policy_forward_eval(policy_ref, obs_normalizer(B_tgt["states"]))
                a_src_pred = _apply_analytic_action_shim(
                    B_src["states"], a_src_policy, a_src_ref_for_shim, args_cli
                )
                a_tgt_pred = _apply_analytic_action_shim(
                    B_tgt["states"], a_tgt_policy, a_tgt_ref_for_shim, args_cli
                )
                a_src_for_loss = a_src_pred
                a_tgt_for_loss = a_tgt_pred
                action_bridge_residual_term_for_loss = torch.zeros_like(a_tgt_pred)
                if stdw_update_target == "zeta4":
                    if stdw_zeta_delta is None:
                        raise RuntimeError("zeta4 update target missing stdw_zeta_delta parameter")
                    a_src_for_loss = _apply_zeta4_surrogate(
                        a_src_pred,
                        stdw_zeta_delta,
                        float(args_cli.stdw_zeta_bound),
                        write_scale=float(args_cli.stdw_zeta_write_scale),
                    )
                    a_tgt_for_loss = _apply_zeta4_surrogate(
                        a_tgt_pred,
                        stdw_zeta_delta,
                        float(args_cli.stdw_zeta_bound),
                        write_scale=float(args_cli.stdw_zeta_write_scale),
                    )
                if stdw_update_target == "policy" and not a_tgt_pred.requires_grad:
                    raise RuntimeError("policy training forward path is detached")
                if stdw_update_target == "zeta4" and not a_tgt_for_loss.requires_grad:
                    raise RuntimeError("zeta4 training path is detached")
                opr_pseudo_actions = B_tgt["pseudo_actions"].detach()
                direction_gate_anchor = None

                # M5: target-anchor source selection.
                #   opr        -> keep B_tgt["pseudo_actions"] (physics-prior, legacy).
                #   esuot_*     -> replace it with the prior-free E-SUOT transport anchor
                #                  derived purely from the state-action distribution.
                #   none        -> disable the target term (anchor = current prediction,
                #                  so L_tgt and its gradient vanish).
                if domain_adapt_adapter is not None:
                    # The esuot_full backend trains its own potential/transport
                    # networks internally (needs autograd), so we must NOT disable
                    # grad here. Inputs come from the (detached) replay buffer and
                    # the adapter uses separate modules/optimizers, so this stays
                    # isolated from the policy graph; the anchor is detached below.
                    with torch.enable_grad():
                        esuot_anchor = domain_adapt_adapter.compute_target_anchor(B_src, B_tgt)
                    B_tgt["pseudo_actions"] = esuot_anchor.to(a_tgt_pred.device).detach()
                elif args_cli.domain_adapt_backend == "none":
                    B_tgt["pseudo_actions"] = a_tgt_pred.detach()

                # Source / target anchors: frozen reference policy on the same observations.
                # Replaces B_src["actions"] which would be ≈ policy(obs_src) and
                # leak L_src ≡ 0 once the fine-tuned policy stays close to itself.
                # 改良 1：同时计算 target obs 上的 anchor，供双向 behavior_kl 使用。
                with torch.no_grad():
                    a_src_anchor = _policy_forward_train(
                        policy_ref, obs_normalizer(B_src["states"])
                    ).detach()
                    a_tgt_anchor = _policy_forward_train(
                        policy_ref, obs_normalizer(B_tgt["states"])
                    ).detach()

                mse_src = ((a_src_for_loss - a_src_anchor) ** 2).mean(dim=-1)
                # B5 route (iv): l_tgt_space branch. `action` path is the legacy
                # pseudo-action anchor (byte-identical to pre-B5). `state_*` path
                # replaces the target term with a state-manifold match in the
                # proxy's phi space: mse_tgt_i = ||phi_pred(s_i,a_tgt_pred_i) - phi_target(z_bridge_i)||^2.
                # z_bridge is a read-out of the SAME Sinkhorn plan used for the
                # action anchor above, so no extra transport is trained.
                stdw_l_tgt_space = str(args_cli.l_tgt_space)
                z_match = None
                runtime_action_bridge_delta_candidate = None
                if stdw_l_tgt_space == "zero":
                    # Live A/B (U4) null control: shape-preserving zero tensor so
                    # loss = (1-rho)*L_src + rho*0 + lambda_reg*L_reg. The tensor
                    # is derived from a_tgt_pred so it inherits device/dtype and
                    # keeps the reduction (mean over batch, mean over action dim)
                    # bit-consistent with the action arm shape contract.
                    mse_tgt = (a_tgt_pred * 0.0).mean(dim=-1)
                    stdw_z_match_norm_mean = float("nan")
                    stdw_phi_pred_norm_mean = float("nan")
                    stdw_l_tgt_normalize_denom = float("nan")
                elif stdw_l_tgt_space == "action_bridge":
                    # Phase-8 E: Reduced Action Anchor.
                    # Convert z_bridge (from FM) to a_bridge using inv_proxy.
                    with torch.no_grad():
                        if state_match_z_source == "fm_midpoint":
                            if state_match_fm_bridge_bundle is None:
                                raise RuntimeError("FM midpoint z_bridge requested but no Phase56 bundle is loaded.")
                            z_bridge, fm_bridge_info = _phase8_fm_midpoint_state_anchor(
                                state_match_fm_bridge_bundle,
                                B_tgt["states"],
                                alpha=float(state_match_fm_bridge_alpha),
                            )
                            stdw_fm_bridge_alpha = float(fm_bridge_info["alpha"])
                            stdw_fm_bridge_curvature = float(fm_bridge_info["curvature"])
                            stdw_fm_bridge_shift_norm_mean = float(fm_bridge_info["shift_norm_mean"])
                            stdw_fm_bridge_shift_norm_p95 = float(fm_bridge_info["shift_norm_p95"])
                        else:
                            raise RuntimeError("action_bridge requires state_match_z_source=fm_midpoint")
                        
                        z_bridge = z_bridge.to(a_tgt_pred.device).detach()
                        
                        s_norm = inv_proxy_norm["s_mean"], inv_proxy_norm["s_std"]
                        a_norm = inv_proxy_norm["a_mean"], inv_proxy_norm["a_std"]
                        
                        s_t_std = (B_tgt["states"].to(a_tgt_pred.device) - s_norm[0]) / s_norm[1]
                        z_bridge_std = (z_bridge - s_norm[0]) / s_norm[1]
                        a_bridge_abs_std = inv_proxy_model(s_t_std, z_bridge_std)
                        a_bridge_abs = a_bridge_abs_std * a_norm[1] + a_norm[0]
                        a_self = None
                        a_bridge_policy_z = None
                        action_bridge_upstream_mode = str(args_cli.stdw_action_bridge_upstream_mode)
                        if action_bridge_upstream_mode == "delta_id":
                            a_self_std = inv_proxy_model(s_t_std, s_t_std)
                            a_self = a_self_std * a_norm[1] + a_norm[0]
                            a_bridge = a_tgt_pred.detach() + (a_bridge_abs - a_self)
                        elif action_bridge_upstream_mode == "policy_on_zbridge":
                            a_bridge_policy_z = _policy_forward_train(
                                policy_ref, obs_normalizer(z_bridge)
                            ).detach()
                            a_bridge = a_tgt_pred.detach() + (a_bridge_policy_z - a_tgt_anchor)
                        else:
                            a_bridge = a_bridge_abs
                        if bool(args_cli.stdw_action_bridge_equiv_audit):
                            if a_self is None:
                                a_self_std = inv_proxy_model(s_t_std, s_t_std)
                                a_self = a_self_std * a_norm[1] + a_norm[0]
                            if a_bridge_policy_z is None:
                                a_bridge_policy_z = _policy_forward_train(
                                    policy_ref, obs_normalizer(z_bridge)
                                ).detach()
                            delta_id_delta = a_bridge_abs - a_self
                            policy_delta = a_bridge_policy_z - a_tgt_anchor
                            stdw_action_bridge_delta_id_vs_policy_delta_mean_abs = float(
                                (delta_id_delta - policy_delta).abs().mean().item()
                            )
                            att_n = min(3, delta_id_delta.shape[-1], policy_delta.shape[-1])
                            if att_n > 0:
                                delta_id_att = delta_id_delta[..., :att_n]
                                policy_att = policy_delta[..., :att_n]
                                delta_id_sign = torch.sign(delta_id_att)
                                policy_sign = torch.sign(policy_att)
                                stdw_action_bridge_delta_id_vs_policy_sign_match_frac = float(
                                    (delta_id_sign == policy_sign).to(torch.float32).mean().item()
                                )
                                clip_val = float(args_cli.stdw_reduced_action_anchor_clip)
                                if clip_val > 0.0:
                                    delta_id_att = delta_id_att.clamp(-clip_val, clip_val)
                                    policy_att = policy_att.clamp(-clip_val, clip_val)
                                stdw_action_bridge_delta_id_vs_policy_clipped_mean_abs = float(
                                    (delta_id_att - policy_att).abs().mean().item()
                                )
                            stdw_action_bridge_self_vs_policy_state_mean_abs = float(
                                (a_self - a_tgt_anchor).abs().mean().item()
                            )
                            stdw_action_bridge_abs_vs_policy_z_mean_abs = float(
                                (a_bridge_abs - a_bridge_policy_z).abs().mean().item()
                            )
                        a_bridge = a_bridge.detach()

                    mse_tgt = ((a_tgt_for_loss - a_bridge) ** 2).mean(dim=-1)
                    direction_gate_anchor = a_bridge.detach()
                    stdw_anchor_mse_to_ref = float(((a_bridge - a_tgt_anchor) ** 2).mean().item())
                    stdw_anchor_mse_to_policy = float(((a_bridge - a_tgt_pred.detach()) ** 2).mean().item())
                    stdw_anchor_mse_to_opr = float(
                        ((a_bridge - opr_pseudo_actions.to(a_bridge.device)) ** 2).mean().item()
                    )
                    stdw_anchor_mse_att_to_policy = float(
                        ((a_bridge[:, :3] - a_tgt_pred.detach()[:, :3]) ** 2).mean().item()
                    )
                    stdw_anchor_mse_depth_to_policy = float(
                        ((a_bridge[:, 3:4] - a_tgt_pred.detach()[:, 3:4]) ** 2).mean().item()
                    )
                    stdw_anchor_mse_att_to_opr = float(
                        ((a_bridge[:, :3] - opr_pseudo_actions.to(a_bridge.device)[:, :3]) ** 2).mean().item()
                    )
                    stdw_anchor_mse_depth_to_opr = float(
                        ((a_bridge[:, 3:4] - opr_pseudo_actions.to(a_bridge.device)[:, 3:4]) ** 2).mean().item()
                    )
                    stdw_anchor_delta_att_norm_to_policy = float(
                        (a_bridge[:, :3] - a_tgt_pred.detach()[:, :3]).norm(dim=-1).mean().item()
                    )
                    stdw_anchor_delta_depth_abs_to_policy = float(
                        (a_bridge[:, 3] - a_tgt_pred.detach()[:, 3]).abs().mean().item()
                    )
                    runtime_action_bridge_delta_candidate = (
                        a_bridge.detach() - a_tgt_pred.detach()
                    ).mean(dim=0)
                    if float(args_cli.stdw_action_bridge_residual_clip) > 0.0:
                        runtime_action_bridge_delta_candidate = runtime_action_bridge_delta_candidate.clamp(
                            -float(args_cli.stdw_action_bridge_residual_clip),
                            float(args_cli.stdw_action_bridge_residual_clip),
                        )
                    if abs(float(args_cli.stdw_action_bridge_residual_scale)) > 0.0:
                        a_tgt_for_loss, action_bridge_residual_term_for_loss = _apply_action_bridge_residual_write(
                            base_action=a_tgt_pred,
                            action=a_tgt_for_loss,
                            anchor_action=a_bridge,
                            zeta_delta=stdw_zeta_delta,
                            bound=float(args_cli.stdw_zeta_bound),
                            residual_scale=float(args_cli.stdw_action_bridge_residual_scale),
                            residual_clip=float(args_cli.stdw_action_bridge_residual_clip),
                        )
                        stdw_bridge_residual_att_norm = float(
                            action_bridge_residual_term_for_loss[:, :3].norm(dim=-1).mean().item()
                        )
                        stdw_bridge_residual_depth_abs = float(
                            action_bridge_residual_term_for_loss[:, 3].abs().mean().item()
                        )
                        mse_tgt = ((a_tgt_for_loss - a_bridge) ** 2).mean(dim=-1)
                    stdw_anchor_abs_mean = float(a_bridge.abs().mean().item())
                    stdw_anchor_abs_max = float(a_bridge.abs().max().item())
                    stdw_z_match_norm_mean = float("nan")
                    stdw_phi_pred_norm_mean = float("nan")
                    stdw_l_tgt_normalize_denom = float("nan")
                elif state_match_kit is None or stdw_l_tgt_space == "action":
                    mse_tgt = ((a_tgt_for_loss - B_tgt["pseudo_actions"]) ** 2).mean(dim=-1)
                    direction_gate_anchor = B_tgt["pseudo_actions"].detach()
                    stdw_z_match_norm_mean = float("nan")
                    stdw_phi_pred_norm_mean = float("nan")
                    stdw_l_tgt_normalize_denom = float("nan")
                else:
                    with torch.no_grad():
                        if state_match_z_source == "fm_midpoint":
                            if state_match_fm_bridge_bundle is None:
                                raise RuntimeError("FM midpoint z_bridge requested but no Phase56 bundle is loaded.")
                            z_bridge, fm_bridge_info = _phase8_fm_midpoint_state_anchor(
                                state_match_fm_bridge_bundle,
                                B_tgt["states"],
                                alpha=float(state_match_fm_bridge_alpha),
                            )
                            stdw_fm_bridge_alpha = float(fm_bridge_info["alpha"])
                            stdw_fm_bridge_curvature = float(fm_bridge_info["curvature"])
                            stdw_fm_bridge_shift_norm_mean = float(fm_bridge_info["shift_norm_mean"])
                            stdw_fm_bridge_shift_norm_p95 = float(fm_bridge_info["shift_norm_p95"])
                        elif state_match_z_source == "buffer_next_state":
                            # Diagnostic-only proxy audit: directly supervise against the
                            # observed one-step successor already stored in the replay row.
                            # This bypasses FM/Sinkhorn target generation so we can check
                            # whether the proxy path itself carries a usable gradient.
                            z_bridge = B_tgt["next_states"]
                            stdw_fm_bridge_alpha = float("nan")
                            stdw_fm_bridge_curvature = float("nan")
                            stdw_fm_bridge_shift_norm_mean = float("nan")
                            stdw_fm_bridge_shift_norm_p95 = float("nan")
                        else:
                            z_bridge = domain_adapt_adapter.compute_state_anchor(B_src, B_tgt)
                        z_bridge = z_bridge.to(a_tgt_pred.device).detach()
                        z_match = state_match_kit.phi_target(z_bridge).detach()
                        stdw_z_match_norm_mean = float(z_match.norm(dim=-1).mean().item())
                    phi_pred = state_match_kit.phi_pred(B_tgt["states"].to(a_tgt_for_loss.device), a_tgt_for_loss)
                    mse_tgt = ((phi_pred - z_match) ** 2).mean(dim=-1)
                    # B5 ii-a follow-up: opt-in scale normalization. When 'std',
                    # divide by z_match.std()^2 to bring phi-space L_tgt to O(1),
                    # matching the action-arm gradient magnitude regime.
                    if str(args_cli.l_tgt_state_normalize) == "std":
                        z_std = z_match.detach().std().clamp_min(1e-6)
                        denom = (z_std * z_std)
                        mse_tgt = mse_tgt / denom
                        stdw_l_tgt_normalize_denom = float(denom.item())
                    else:
                        stdw_l_tgt_normalize_denom = float("nan")
                    with torch.no_grad():
                        stdw_phi_pred_norm_mean = float(phi_pred.detach().norm(dim=-1).mean().item())
                stdw_l_tgt_state_val = float(mse_tgt.detach().mean().item())
                with torch.no_grad():
                    anchor = B_tgt["pseudo_actions"].detach()
                    stdw_anchor_mse_to_ref = float(((anchor - a_tgt_anchor) ** 2).mean().item())
                    stdw_anchor_mse_to_policy = float(((anchor - a_tgt_pred.detach()) ** 2).mean().item())
                    stdw_anchor_mse_to_opr = float(
                        ((anchor - opr_pseudo_actions.to(anchor.device)) ** 2).mean().item()
                    )
                    stdw_anchor_abs_mean = float(anchor.abs().mean().item())
                    stdw_anchor_abs_max = float(anchor.abs().max().item())

                if args_cli.enable_lyapunov_mask:
                    m_src = B_src["stdw_masks"]
                    m_tgt = B_tgt["stdw_masks"]
                    L_src = (m_src * mse_src).sum() / m_src.sum().clamp_min(1.0)
                    L_tgt = (m_tgt * mse_tgt).sum() / m_tgt.sum().clamp_min(1.0)
                    eff_num = float((m_src.sum() + m_tgt.sum()).item())
                    eff_den = float(len(m_src) + len(m_tgt))
                    effective_batch_frac = eff_num / max(eff_den, 1.0)
                else:
                    L_src = mse_src.mean()
                    L_tgt = mse_tgt.mean()
                    effective_batch_frac = 1.0

                # Regularization: parameter-space L2 vs behavior KL.
                # 改良 1：双向 behavioral anchoring（Bi-directional Behavioral KL）
                #   L_reg = (1-ρ) * MSE(π(s_src), π_ref(s_src))
                #         +     ρ * MSE(π(s_tgt), π_ref(s_tgt))
                # 物理意义：源域时锁住源域行为；目标域时锁住目标域不偏离 baseline。
                # 这给 OOD 状态下的网络退化加了一根"动态拉力弹簧"（解 §8.6 第 2 点）。
                # L2 模式保留作为 legacy 对照。
                if args_cli.reg_mode == "behavior_kl":
                    L_reg_src = ((a_src_for_loss - a_src_anchor) ** 2).mean()
                    L_reg_tgt = ((a_tgt_for_loss - a_tgt_anchor) ** 2).mean()
                    L_reg = (1.0 - rho) * L_reg_src + rho * L_reg_tgt
                elif stdw_update_target == "zeta4":
                    zeta_offset = _zeta4_multipliers(
                        stdw_zeta_delta, float(args_cli.stdw_zeta_bound)
                    ) - 1.0
                    L_reg = float(args_cli.stdw_zeta_reg) * (zeta_offset * zeta_offset).mean()
                else:
                    L_reg = sum(
                        ((p - theta_pre[n]) ** 2).sum()
                        for n, p in policy.named_parameters()
                    )
                loss = (1.0 - rho) * L_src + rho * L_tgt + args_cli.lambda_reg * L_reg

                loss_src_val = float(L_src.detach().item())
                loss_tgt_val = float(L_tgt.detach().item())
                loss_reg_val = float(L_reg.detach().item()) if isinstance(L_reg, torch.Tensor) else float(L_reg)
                loss_total = float(loss.detach().item())

                # M2: directional hard-constraint guard. Builds on M1's dV-sign
                # mask (B_*["stdw_masks"], always recorded in the buffer). When
                # mode != 'off' this *rejects* the whole update -- rather than
                # merely down-weighting it -- if the batch lacks Lyapunov-descent
                # evidence (pass_rate) or its target pull points anti-descent
                # (descent_align). Evaluated BEFORE the optimizer step so a
                # rejected batch never perturbs the policy. Default 'off' always
                # accepts => zero behaviour change.
                dir_guard_ok, dir_guard_reason, dir_guard_metrics = stdw_dir_guard.evaluate(
                    dir_guard_cfg,
                    B_src["stdw_masks"],
                    B_tgt["stdw_masks"],
                    mse_tgt,
                )
                stdw_dir_guard_pass_rate = dir_guard_metrics["dir_guard_pass_rate"]
                stdw_dir_guard_align = dir_guard_metrics["dir_guard_align"]

                if bool(args_cli.slow_loop_dry_run):
                    stdw_update_rejected = 1
                    stdw_update_rejected_count += 1
                    stdw_acceptance_reason = "slow_loop_dry_run"
                    stdw_last_reject_reason = stdw_acceptance_reason
                elif not dir_guard_ok:
                    stdw_update_rejected = 1
                    stdw_update_rejected_count += 1
                    stdw_dir_guard_blocked_count += 1
                    stdw_acceptance_reason = dir_guard_reason
                    stdw_last_reject_reason = dir_guard_reason
                elif torch.isfinite(loss) and effective_batch_frac > 0.0:
                    use_batch_trust = args_cli.stdw_update_acceptance == "batch_trust"
                    if use_batch_trust:
                        with torch.no_grad():
                            stdw_behavior_mse_before = float(
                                0.5 * (
                                    ((a_src_for_loss.detach() - a_src_anchor) ** 2).mean()
                                    + ((a_tgt_for_loss.detach() - a_tgt_anchor) ** 2).mean()
                                ).item()
                            )
                            stdw_behavior_mse_att_before = float(
                                0.5
                                * (
                                    ((a_src_for_loss.detach()[:, :3] - a_src_anchor[:, :3]) ** 2).mean()
                                    + ((a_tgt_for_loss.detach()[:, :3] - a_tgt_anchor[:, :3]) ** 2).mean()
                                ).item()
                            )
                            stdw_behavior_mse_depth_before = float(
                                0.5
                                * (
                                    ((a_src_for_loss.detach()[:, 3:4] - a_src_anchor[:, 3:4]) ** 2).mean()
                                    + ((a_tgt_for_loss.detach()[:, 3:4] - a_tgt_anchor[:, 3:4]) ** 2).mean()
                                ).item()
                            )
                            stdw_target_mse_before = float(mse_tgt.detach().mean().item())
                        if effective_batch_frac < float(args_cli.stdw_min_effective_batch_frac):
                            stdw_update_rejected = 1
                            stdw_update_rejected_count += 1
                            stdw_acceptance_reason = "low_effective_batch_frac"
                            stdw_last_reject_reason = stdw_acceptance_reason
                        else:
                            policy_before = (
                                {k: v.detach().clone() for k, v in policy.state_dict().items()}
                                if stdw_update_target == "policy"
                                else None
                            )
                            zeta_before = (
                                stdw_zeta_delta.detach().clone()
                                if stdw_update_target == "zeta4" and stdw_zeta_delta is not None
                                else None
                            )
                            optimizer_before = copy.deepcopy(optimizer.state_dict())
                            a_src_before = a_src_for_loss.detach()
                            a_tgt_before = a_tgt_for_loss.detach()
                            optimizer.zero_grad(set_to_none=True)
                            loss.backward()
                            if (
                                stdw_update_target == "zeta4"
                                and stdw_zeta_delta is not None
                                and stdw_zeta_delta.grad is not None
                                and stdw_zeta_grad_mask is not None
                            ):
                                stdw_zeta_delta.grad.mul_(
                                    stdw_zeta_grad_mask.to(
                                        stdw_zeta_delta.grad.device,
                                        dtype=stdw_zeta_delta.grad.dtype,
                                    )
                                )
                            if stdw_update_target == "zeta4":
                                torch.nn.utils.clip_grad_norm_([stdw_zeta_delta], max_norm=1.0)
                            else:
                                torch.nn.utils.clip_grad_norm_(policy.parameters(), max_norm=1.0)
                            optimizer.step()
                            if stdw_update_target == "zeta4":
                                _enforce_zeta_depth_floor_(
                                    stdw_zeta_delta,
                                    bound=float(args_cli.stdw_zeta_bound),
                                    min_multiplier=float(args_cli.stdw_zeta_depth_min_multiplier),
                                )
                            with torch.no_grad():
                                if stdw_update_target == "zeta4":
                                    a_src_after = _apply_zeta4_surrogate(
                                        a_src_pred,
                                        stdw_zeta_delta,
                                        float(args_cli.stdw_zeta_bound),
                                        write_scale=float(args_cli.stdw_zeta_write_scale),
                                    )
                                    a_tgt_after = _apply_zeta4_surrogate(
                                        a_tgt_pred,
                                        stdw_zeta_delta,
                                        float(args_cli.stdw_zeta_bound),
                                        write_scale=float(args_cli.stdw_zeta_write_scale),
                                    )
                                    if (
                                        stdw_l_tgt_space == "action_bridge"
                                        and abs(float(args_cli.stdw_action_bridge_residual_scale)) > 0.0
                                    ):
                                        a_tgt_after, action_bridge_residual_term_after = (
                                            _apply_action_bridge_residual_write(
                                                base_action=a_tgt_pred,
                                                action=a_tgt_after,
                                                anchor_action=a_bridge,
                                                zeta_delta=stdw_zeta_delta,
                                                bound=float(args_cli.stdw_zeta_bound),
                                                residual_scale=float(args_cli.stdw_action_bridge_residual_scale),
                                                residual_clip=float(args_cli.stdw_action_bridge_residual_clip),
                                            )
                                        )
                                    else:
                                        action_bridge_residual_term_after = torch.zeros_like(a_tgt_after)
                                else:
                                    a_src_after = _policy_forward_train(policy, obs_normalizer(B_src["states"]))
                                    a_tgt_after = _policy_forward_train(policy, obs_normalizer(B_tgt["states"]))
                                    action_bridge_residual_term_after = torch.zeros_like(a_tgt_after)
                                stdw_behavior_mse_after = float(
                                    0.5 * (
                                        ((a_src_after - a_src_anchor) ** 2).mean()
                                        + ((a_tgt_after - a_tgt_anchor) ** 2).mean()
                                    ).item()
                                )
                                stdw_behavior_mse_att_after = float(
                                    0.5
                                    * (
                                        ((a_src_after[:, :3] - a_src_anchor[:, :3]) ** 2).mean()
                                        + ((a_tgt_after[:, :3] - a_tgt_anchor[:, :3]) ** 2).mean()
                                    ).item()
                                )
                                stdw_behavior_mse_depth_after = float(
                                    0.5
                                    * (
                                        ((a_src_after[:, 3:4] - a_src_anchor[:, 3:4]) ** 2).mean()
                                        + ((a_tgt_after[:, 3:4] - a_tgt_anchor[:, 3:4]) ** 2).mean()
                                    ).item()
                                )
                                stdw_action_delta_mse = float(
                                    0.5 * (
                                        ((a_src_after - a_src_before) ** 2).mean()
                                        + ((a_tgt_after - a_tgt_before) ** 2).mean()
                                    ).item()
                                )
                                stdw_update_delta_action_att_norm = float(
                                    0.5
                                    * (
                                        (a_src_after[:, :3] - a_src_before[:, :3]).norm(dim=-1).mean()
                                        + (a_tgt_after[:, :3] - a_tgt_before[:, :3]).norm(dim=-1).mean()
                                    ).item()
                                )
                                stdw_update_delta_action_depth_abs = float(
                                    0.5
                                    * (
                                        (a_src_after[:, 3] - a_src_before[:, 3]).abs().mean()
                                        + (a_tgt_after[:, 3] - a_tgt_before[:, 3]).abs().mean()
                                    ).item()
                                )
                                target_anchor_eval = (
                                    direction_gate_anchor
                                    if direction_gate_anchor is not None
                                    else B_tgt["pseudo_actions"].detach()
                                ).to(a_tgt_after.device)
                                if state_match_kit is not None and z_match is not None:
                                    phi_after = state_match_kit.phi_pred(B_tgt["states"].to(a_tgt_after.device), a_tgt_after)
                                    target_after = ((phi_after - z_match.to(phi_after.device)) ** 2).mean(dim=-1)
                                    stdw_target_mse_after = float(target_after.mean().item())
                                else:
                                    stdw_target_mse_after = float(((a_tgt_after - target_anchor_eval) ** 2).mean().item())
                                stdw_target_mse_att_before = float(
                                    ((a_tgt_before[:, :3] - target_anchor_eval[:, :3]) ** 2).mean().item()
                                )
                                stdw_target_mse_att_after = float(
                                    ((a_tgt_after[:, :3] - target_anchor_eval[:, :3]) ** 2).mean().item()
                                )
                                stdw_target_mse_depth_before = float(
                                    ((a_tgt_before[:, 3:4] - target_anchor_eval[:, 3:4]) ** 2).mean().item()
                                )
                                stdw_target_mse_depth_after = float(
                                    ((a_tgt_after[:, 3:4] - target_anchor_eval[:, 3:4]) ** 2).mean().item()
                                )
                                if stdw_update_target == "zeta4" and zeta_before is not None and stdw_zeta_delta is not None:
                                    if bool(getattr(args_cli, "stdw_target_mse_axis_audit", False)):
                                        axis_targets: dict[str, float] = {}
                                        combo_map = {
                                            "roll": (0,),
                                            "pitch": (1,),
                                            "yaw": (2,),
                                            "roll_pitch": (0, 1),
                                            "roll_yaw": (0, 2),
                                            "pitch_yaw": (1, 2),
                                        }
                                        for axis_name, axis_indices in combo_map.items():
                                            zeta_axis = zeta_before.detach().clone()
                                            for axis_idx in axis_indices:
                                                zeta_axis[axis_idx] = stdw_zeta_delta[axis_idx].detach()
                                            a_tgt_axis = _apply_zeta4_surrogate(
                                                a_tgt_pred,
                                                zeta_axis,
                                                float(args_cli.stdw_zeta_bound),
                                                write_scale=float(args_cli.stdw_zeta_write_scale),
                                            )
                                            if (
                                                stdw_l_tgt_space == "action_bridge"
                                                and abs(float(args_cli.stdw_action_bridge_residual_scale)) > 0.0
                                            ):
                                                a_tgt_axis, _ = _apply_action_bridge_residual_write(
                                                    base_action=a_tgt_pred,
                                                    action=a_tgt_axis,
                                                    anchor_action=a_bridge,
                                                    zeta_delta=zeta_axis,
                                                    bound=float(args_cli.stdw_zeta_bound),
                                                    residual_scale=float(args_cli.stdw_action_bridge_residual_scale),
                                                    residual_clip=float(args_cli.stdw_action_bridge_residual_clip),
                                                )
                                            if state_match_kit is not None and z_match is not None:
                                                phi_axis = state_match_kit.phi_pred(
                                                    B_tgt["states"].to(a_tgt_axis.device), a_tgt_axis
                                                )
                                                axis_targets[axis_name] = float(
                                                    ((phi_axis - z_match.to(phi_axis.device)) ** 2).mean(dim=-1).mean().item()
                                                )
                                            else:
                                                axis_targets[axis_name] = float(
                                                    ((a_tgt_axis - target_anchor_eval.to(a_tgt_axis.device)) ** 2).mean().item()
                                                )
                                        stdw_target_mse_after_roll_only = axis_targets["roll"]
                                        stdw_target_mse_after_pitch_only = axis_targets["pitch"]
                                        stdw_target_mse_after_yaw_only = axis_targets["yaw"]
                                        stdw_target_mse_after_roll_pitch = axis_targets["roll_pitch"]
                                        stdw_target_mse_after_roll_yaw = axis_targets["roll_yaw"]
                                        stdw_target_mse_after_pitch_yaw = axis_targets["pitch_yaw"]
                                    old_mult_vec = _effective_zeta4_multipliers(
                                        zeta_before,
                                        float(args_cli.stdw_zeta_bound),
                                        float(args_cli.stdw_zeta_write_scale),
                                    ).detach()
                                    new_mult_vec = _effective_zeta4_multipliers(
                                        stdw_zeta_delta,
                                        float(args_cli.stdw_zeta_bound),
                                        float(args_cli.stdw_zeta_write_scale),
                                    ).detach()
                                    stdw_zeta_delta_roll = float((new_mult_vec[0] - old_mult_vec[0]).item())
                                    stdw_zeta_delta_pitch = float((new_mult_vec[1] - old_mult_vec[1]).item())
                                    stdw_zeta_delta_yaw = float((new_mult_vec[2] - old_mult_vec[2]).item())
                                    stdw_zeta_delta_depth = float((new_mult_vec[3] - old_mult_vec[3]).item())
                                    stdw_tgt_action_roll_abs_before = float(a_tgt_before[:, 0].abs().mean().item())
                                    stdw_tgt_action_pitch_abs_before = float(a_tgt_before[:, 1].abs().mean().item())
                                    stdw_tgt_action_yaw_abs_before = float(a_tgt_before[:, 2].abs().mean().item())
                                    stdw_tgt_action_depth_abs_before = float(a_tgt_before[:, 3].abs().mean().item())
                                    stdw_update_delta_action_roll_abs = float(
                                        (a_tgt_after[:, 0] - a_tgt_before[:, 0]).abs().mean().item()
                                    )
                                    stdw_update_delta_action_pitch_abs = float(
                                        (a_tgt_after[:, 1] - a_tgt_before[:, 1]).abs().mean().item()
                                    )
                                    stdw_update_delta_action_yaw_abs = float(
                                        (a_tgt_after[:, 2] - a_tgt_before[:, 2]).abs().mean().item()
                                    )
                                    stdw_update_delta_action_depth_abs_tgt = float(
                                        (a_tgt_after[:, 3] - a_tgt_before[:, 3]).abs().mean().item()
                                    )
                                    anchor_att_gap = float(
                                        (target_anchor_eval[:, :3] - a_tgt_before[:, :3]).norm(dim=-1).mean().item()
                                    )
                                    anchor_depth_gap = float(
                                        (target_anchor_eval[:, 3] - a_tgt_before[:, 3]).abs().mean().item()
                                    )
                                    stdw_write_progress_att_ratio = float(
                                        stdw_update_delta_action_att_norm / max(anchor_att_gap, 1.0e-12)
                                    )
                                    stdw_write_progress_depth_ratio = float(
                                        stdw_update_delta_action_depth_abs_tgt / max(anchor_depth_gap, 1.0e-12)
                                    )
                                    stdw_zeta_to_action_gain_roll = float(
                                        stdw_update_delta_action_roll_abs / max(abs(stdw_zeta_delta_roll), 1.0e-12)
                                    )
                                    stdw_zeta_to_action_gain_pitch = float(
                                        stdw_update_delta_action_pitch_abs / max(abs(stdw_zeta_delta_pitch), 1.0e-12)
                                    )
                                    stdw_zeta_to_action_gain_yaw = float(
                                        stdw_update_delta_action_yaw_abs / max(abs(stdw_zeta_delta_yaw), 1.0e-12)
                                    )
                                    stdw_zeta_to_action_gain_depth = float(
                                        stdw_update_delta_action_depth_abs_tgt / max(abs(stdw_zeta_delta_depth), 1.0e-12)
                                    )

                            reject_reasons = []
                            if stdw_behavior_mse_after > stdw_behavior_mse_before + float(args_cli.stdw_max_behavior_mse):
                                reject_reasons.append("behavior_mse")
                            if stdw_action_delta_mse > float(args_cli.stdw_max_action_delta_mse):
                                reject_reasons.append("action_delta")
                            if stdw_target_mse_after > stdw_target_mse_before + float(args_cli.stdw_max_target_mse_increase):
                                reject_reasons.append("target_mse")

                            if (
                                bool(getattr(args_cli, "stdw_depth_guard", False))
                                and stdw_update_target == "zeta4"
                                and stdw_zeta_delta is not None
                            ):
                                _, _, true_z_guard, _, _, _ = _get_true_pose(env)
                                true_depth_guard = float(_depth_to_v1(true_z_guard))
                                old_mult = float(
                                    _effective_zeta4_multipliers(
                                        zeta_before if zeta_before is not None else stdw_zeta_delta,
                                        float(args_cli.stdw_zeta_bound),
                                        float(args_cli.stdw_zeta_write_scale),
                                    )[3].detach().item()
                                )
                                new_mult = float(
                                    _effective_zeta4_multipliers(
                                        stdw_zeta_delta,
                                        float(args_cli.stdw_zeta_bound),
                                        float(args_cli.stdw_zeta_write_scale),
                                    )[3].detach().item()
                                )
                                stdw_depth_guard_old_multiplier = old_mult
                                stdw_depth_guard_new_multiplier = new_mult
                                near_depth_boundary = (
                                    true_depth_guard <= float(args_cli.stdw_depth_guard_lower_trigger)
                                    or true_depth_guard >= float(args_cli.stdw_depth_guard_upper_trigger)
                                )
                                if near_depth_boundary and new_mult < old_mult - float(args_cli.stdw_depth_guard_eps):
                                    stdw_depth_guard_blocked = 1
                                    reject_reasons.append(
                                        "depth_guard("
                                        f"{true_depth_guard:.6f},"
                                        f"{old_mult:.6f}->{new_mult:.6f},"
                                        f"eps={float(args_cli.stdw_depth_guard_eps):.1e}"
                                        ")"
                                    )

                            if getattr(args_cli, "stdw_direction_gate", False):
                                # Check if the proposed action change aligns with the selected
                                # deployable correction direction.
                                d_action = a_tgt_after - a_tgt_before
                                e_action = _direction_gate_correction_direction(
                                    source=stdw_direction_gate_source,
                                    action_before=a_tgt_before,
                                    pseudo_anchor=B_tgt["pseudo_actions"].detach(),
                                    target_anchor=direction_gate_anchor,
                                    env=env,
                                    depth_reference_frame=str(args_cli.depth_reference_frame),
                                    depth_surface_z=float(args_cli.depth_surface_z),
                                )
                                dot_product = float((d_action * e_action).sum(dim=-1).mean().item())
                                stdw_direction_gate_dot = dot_product
                                stdw_direction_gate_dot_att = float(
                                    (d_action[:, :3] * e_action[:, :3]).sum(dim=-1).mean().item()
                                )
                                stdw_direction_gate_dot_depth = float(
                                    (d_action[:, 3] * e_action[:, 3]).mean().item()
                                )
                                if dot_product <= float(args_cli.stdw_direction_gate_min_dot):
                                    reject_reasons.append(f"direction_gate({dot_product:.4f})")

                            if reject_reasons:
                                if stdw_update_target == "policy" and policy_before is not None:
                                    policy.load_state_dict(policy_before)
                                if stdw_update_target == "zeta4" and zeta_before is not None and stdw_zeta_delta is not None:
                                    stdw_zeta_delta.data.copy_(zeta_before)
                                optimizer.load_state_dict(optimizer_before)
                                stdw_update_rejected = 1
                                stdw_update_rejected_count += 1
                                stdw_acceptance_reason = "+".join(reject_reasons)
                                stdw_last_reject_reason = stdw_acceptance_reason
                            else:
                                if stdw_update_target == "zeta4" and stdw_zeta_delta is not None and stdw_zeta_last_multiplier is not None:
                                    new_mult = _effective_zeta4_multipliers(
                                        stdw_zeta_delta,
                                        float(args_cli.stdw_zeta_bound),
                                        float(args_cli.stdw_zeta_write_scale),
                                    ).detach()
                                    rel_mult = new_mult / stdw_zeta_last_multiplier.clamp_min(1.0e-6)
                                    _apply_runtime_zeta4_update(
                                        raw_env,
                                        rel_mult,
                                        attitude_zeta_path=str(args_cli.stdw_runtime_attitude_zeta_path),
                                    )
                                    stdw_zeta_last_multiplier.copy_(new_mult)
                                    if runtime_action_bridge_delta_candidate is not None:
                                        stdw_runtime_action_bridge_delta = runtime_action_bridge_delta_candidate.detach().clone()
                                        if stdw_reduced_action_anchor_enable:
                                            stdw_runtime_reduced_action_anchor = runtime_action_bridge_delta_candidate.detach().clone()
                                stdw_update_accepted = 1
                                stdw_update_accepted_count += 1
                                stdw_acceptance_reason = "accepted"
                    else:
                        optimizer.zero_grad(set_to_none=True)
                        loss.backward()
                        if (
                            stdw_update_target == "zeta4"
                            and stdw_zeta_delta is not None
                            and stdw_zeta_delta.grad is not None
                            and stdw_zeta_grad_mask is not None
                        ):
                            stdw_zeta_delta.grad.mul_(
                                stdw_zeta_grad_mask.to(
                                    stdw_zeta_delta.grad.device,
                                    dtype=stdw_zeta_delta.grad.dtype,
                                )
                            )
                        if stdw_update_target == "zeta4":
                            torch.nn.utils.clip_grad_norm_([stdw_zeta_delta], max_norm=1.0)
                        else:
                            torch.nn.utils.clip_grad_norm_(policy.parameters(), max_norm=1.0)
                        optimizer.step()
                        if stdw_update_target == "zeta4":
                            _enforce_zeta_depth_floor_(
                                stdw_zeta_delta,
                                bound=float(args_cli.stdw_zeta_bound),
                                min_multiplier=float(args_cli.stdw_zeta_depth_min_multiplier),
                            )
                        if stdw_update_target == "zeta4" and stdw_zeta_delta is not None and stdw_zeta_last_multiplier is not None:
                            new_mult = _effective_zeta4_multipliers(
                                stdw_zeta_delta,
                                float(args_cli.stdw_zeta_bound),
                                float(args_cli.stdw_zeta_write_scale),
                            ).detach()
                            rel_mult = new_mult / stdw_zeta_last_multiplier.clamp_min(1.0e-6)
                            _apply_runtime_zeta4_update(
                                raw_env,
                                rel_mult,
                                attitude_zeta_path=str(args_cli.stdw_runtime_attitude_zeta_path),
                            )
                            stdw_zeta_last_multiplier.copy_(new_mult)
                            if runtime_action_bridge_delta_candidate is not None:
                                stdw_runtime_action_bridge_delta = runtime_action_bridge_delta_candidate.detach().clone()
                                if stdw_reduced_action_anchor_enable:
                                    stdw_runtime_reduced_action_anchor = runtime_action_bridge_delta_candidate.detach().clone()
                        stdw_update_accepted = 1
                        stdw_update_accepted_count += 1
            except Exception as exc:
                print(f"[WARN] slow-loop failure at step {step}: {exc}")
            finally:
                if rng_state is not None:
                    _restore_torch_rng_state(rng_state)

        # ---- metrics & domain readout ----
        try:
            fluid_velocity = env.unwrapped.get_current_fluid_velocity()[0].detach().cpu().tolist()
        except Exception:
            fluid_velocity = [0.0, 0.0, 0.0]
        try:
            volume_mean = float(env.unwrapped.volumes.mean().item())
            volume_scale = volume_mean / float(env.unwrapped.cfg.volume)
        except Exception:
            volume_mean = 0.0
            volume_scale = 1.0
        domain_bias = calculate_domain_bias(volume_scale, fluid_velocity)
        control_effort = calculate_control_effort(action)
        des_roll, des_pitch, des_yaw, des_depth = _get_desired_pose(env)
        true_x, true_y, true_z, true_roll, true_pitch, true_yaw = _get_true_pose(env)

        compound_error = calculate_compound_error(
            des_roll,
            des_pitch,
            des_yaw,
            true_roll,
            true_pitch,
            true_yaw,
            des_depth,
            true_z,
        )
        attitude_tracking_mse = calculate_attitude_tracking_mse(
            des_roll,
            des_pitch,
            des_yaw,
            true_roll,
            true_pitch,
            true_yaw,
        )
        so3_attitude_error = calculate_attitude_error_so3(
            des_roll,
            des_pitch,
            des_yaw,
            true_roll,
            true_pitch,
            true_yaw,
        )
        true_depth_v1 = float(_depth_to_v1(true_z))
        des_depth_v1 = float(_depth_to_v1(des_depth))
        depth_barrier = _depth_barrier_for_v1(true_depth_v1)
        signal_for_eval = filt_err if args_cli.enable_filter else compound_error
        final_mse_window.append(float(signal_for_eval))
        # Accumulate baseline mean before drift starts (5.2: relative threshold).
        if step < int(args_cli.drift_start_step):
            baseline_err_sum += float(compound_error)
            baseline_err_count += 1
        elif baseline_err_mean is None and baseline_err_count > 0:
            baseline_err_mean = baseline_err_sum / float(baseline_err_count)
            if float(args_cli.stability_threshold_rel) > 0.0:
                relative = float(args_cli.stability_threshold_rel) * baseline_err_mean
                effective_stability_threshold = max(
                    float(args_cli.stability_threshold), relative
                )
                print(
                    f"[stability] baseline mean={baseline_err_mean:.4f}, "
                    f"abs_thr={args_cli.stability_threshold:.4f}, "
                    f"rel({args_cli.stability_threshold_rel}x)={relative:.4f}, "
                    f"effective={effective_stability_threshold:.4f}"
                )
        if signal_for_eval < effective_stability_threshold:
            convergence_streak += 1
            if convergence_streak >= args_cli.stability_window and convergence_step is None:
                convergence_step = step
        else:
            convergence_streak = 0

        # com_to_cob_offset readout (env_id=0).
        try:
            offset_row = env.unwrapped.com_to_cob_offsets[0].detach().cpu().tolist()
        except Exception:
            offset_row = [0.0, 0.0, 0.0]

        # M4 boundary diagnostics readout (env_id=0). NaN when M4 is off / absent
        # so the boundary plot degrades gracefully (zero behaviour change).
        def _boundary_scalar(key: str) -> float:
            info = getattr(env.unwrapped, "_last_boundary_info", None)
            if not info or key not in info:
                return float("nan")
            try:
                return float(info[key][0])
            except Exception:
                return float("nan")

        boundary_submersion_ratio = _boundary_scalar("submersion_ratio")
        boundary_residual_dB = _boundary_scalar("residual_dB")
        boundary_ground_mag = _boundary_scalar("ground_mag")

        done_flag = bool(torch.any(dones > 0).item()) if isinstance(dones, torch.Tensor) else bool(dones)
        if done_flag:
            reset_count += 1

        executed_action_list = action.squeeze(0).detach().cpu().tolist() if action.ndim > 1 else action.detach().cpu().tolist()
        try:
            sat_ratio_for_row = float(runtime_control.get("runtime_motor_saturation_ratio", float("nan")))
            saturation_authority_proxy = 1.0 - min(max(sat_ratio_for_row, 0.0), 1.0)
        except Exception:
            saturation_authority_proxy = float("nan")

        try:
            env_episode_step = int(raw_env.unwrapped.episode_length_buf[0].item())
        except Exception:
            env_episode_step = -1
        reference_mode_runtime = reference_mode_pre
        mixed_reference_branch = mixed_reference_branch_pre
        mixed_reference_is_flip = mixed_reference_is_flip_pre
        episode_length_steps = int(step - current_episode_start_step + 1)
        episode_reset_reason = ""
        if done_flag:
            episode_reset_reason = "env_done"
        elif bool(args_cli.phase56_runtime_execution_hooks) and phase56_requested_reset:
            episode_reset_reason = "phase56_requested_reset"
        episode_branch_at_reset = current_episode_branch if episode_reset_reason else ""
        depth_lower_margin = float(true_depth_v1 - float(depth_limits["depth_lower_limit"]))
        depth_upper_margin = float(float(depth_limits["depth_upper_limit"]) - true_depth_v1)
        depth_in_hard_tube = (
            float(depth_limits["depth_lower_limit"]) <= true_depth_v1 <= float(depth_limits["depth_upper_limit"])
        )
        des_depth_lower_margin = float(des_depth_v1 - float(depth_limits["depth_lower_limit"]))
        des_depth_upper_margin = float(float(depth_limits["depth_upper_limit"]) - des_depth_v1)
        des_depth_in_hard_tube = (
            float(depth_limits["depth_lower_limit"]) <= des_depth_v1 <= float(depth_limits["depth_upper_limit"])
        )
        des_depth_in_safe_core = (
            float(depth_limits["depth_lower_safe"]) <= des_depth_v1 <= float(depth_limits["depth_upper_safe"])
        )
        phase56_state_for_row = str(phase56_runtime_row.get("phase56_runtime_state", phase56_runtime_state))
        phase56_transition_for_row = str(phase56_runtime_row.get("phase56_runtime_state_transition", ""))
        phase56_runtime_row["phase56_runtime_state_age"] = int(phase56_runtime_state_age)
        if phase56_transition_for_row:
            _, phase56_next_state_for_row = phase56_transition_for_row.split("->", 1)
            if phase56_next_state_for_row == "ADAPT_ARMED":
                phase56_runtime_wake_count += 1
                phase56_runtime_cycle_id += 1
                phase56_runtime_cycle_start_step = int(step)
                if phase56_runtime_last_reset_step is not None:
                    phase56_runtime_last_reset_to_rearm_latency = int(step - phase56_runtime_last_reset_step)
                    phase56_runtime_reset_to_rearm_latencies.append(int(phase56_runtime_last_reset_to_rearm_latency))
                else:
                    phase56_runtime_last_reset_to_rearm_latency = float("nan")
            if phase56_prev_state == "ADAPT_ACTIVE" and phase56_runtime_active_entry_step is not None:
                phase56_runtime_active_durations.append(int(step - phase56_runtime_active_entry_step))
                phase56_runtime_active_entry_step = None
            if phase56_prev_state == "FROZEN" and phase56_runtime_frozen_entry_step is not None:
                phase56_runtime_frozen_durations.append(int(step - phase56_runtime_frozen_entry_step))
                phase56_runtime_frozen_entry_step = None
            if phase56_prev_state == "FALLBACK_ZERO_DRIFT" and phase56_runtime_fallback_entry_step is not None:
                phase56_runtime_fallback_durations.append(int(step - phase56_runtime_fallback_entry_step))
                phase56_runtime_fallback_entry_step = None
            if phase56_next_state_for_row == "ADAPT_ACTIVE":
                phase56_runtime_active_entry_step = int(step)
            elif phase56_next_state_for_row == "FROZEN":
                phase56_runtime_frozen_entry_step = int(step)
            elif phase56_next_state_for_row == "FALLBACK_ZERO_DRIFT":
                phase56_runtime_fallback_entry_step = int(step)
            elif phase56_next_state_for_row == "RESET_REQUIRED":
                phase56_runtime_reset_entry_step = int(step)
        phase56_runtime_row["phase56_runtime_cycle_id"] = int(phase56_runtime_cycle_id)
        phase56_runtime_row["phase56_runtime_cycle_step"] = (
            int(step - phase56_runtime_cycle_start_step + 1) if phase56_runtime_cycle_start_step is not None else 0
        )
        phase56_runtime_row["phase56_runtime_active_age"] = (
            int(step - phase56_runtime_active_entry_step + 1)
            if phase56_state_for_row == "ADAPT_ACTIVE" and phase56_runtime_active_entry_step is not None
            else 0
        )
        phase56_runtime_row["phase56_runtime_frozen_age"] = (
            int(step - phase56_runtime_frozen_entry_step + 1)
            if phase56_state_for_row == "FROZEN" and phase56_runtime_frozen_entry_step is not None
            else 0
        )
        phase56_runtime_row["phase56_runtime_fallback_age"] = (
            int(step - phase56_runtime_fallback_entry_step + 1)
            if phase56_state_for_row == "FALLBACK_ZERO_DRIFT" and phase56_runtime_fallback_entry_step is not None
            else 0
        )
        phase56_runtime_row["phase56_runtime_reset_age"] = (
            int(step - phase56_runtime_reset_entry_step + 1)
            if phase56_state_for_row == "RESET_REQUIRED" and phase56_runtime_reset_entry_step is not None
            else 0
        )
        phase56_runtime_row["phase56_runtime_reset_to_rearm_latency"] = float(
            phase56_runtime_last_reset_to_rearm_latency
        )
        phase56_runtime_state_counts[phase56_state_for_row] = phase56_runtime_state_counts.get(phase56_state_for_row, 0) + 1
        if phase56_transition_for_row:
            phase56_runtime_state_transition_count += 1
        phase56_curvature_row = _phase56_curvature_relative_row(
            enabled=bool(args_cli.phase56_curvature_relative_logging),
            curvature_value=float(phase56_runtime_row.get("fm_path_curvature_runtime", float("nan"))),
            baseline_source=str(args_cli.phase56_curvature_baseline_source),
            baseline_window_label=str(args_cli.phase56_curvature_baseline_window_label),
            baseline_p95=float(args_cli.phase56_curvature_baseline_p95),
            baseline_p99=float(args_cli.phase56_curvature_baseline_p99),
            window_size=int(args_cli.phase56_curvature_window_size),
            scope_caveat="observed_direct replay evidence only; not full selected-chain coverage",
            watch_history=phase56_curvature_watch_history,
            stress_history=phase56_curvature_stress_history,
        )
        phase56_curvature_state_for_row = str(
            phase56_curvature_row.get("phase56_curvature_nonbinding_state", "disabled")
        )
        phase56_curvature_nonbinding_state_counts[phase56_curvature_state_for_row] = (
            phase56_curvature_nonbinding_state_counts.get(phase56_curvature_state_for_row, 0) + 1
        )
        if stdw_zeta_delta is not None:
            zeta_multiplier_row = _effective_zeta4_multipliers(
                stdw_zeta_delta,
                float(args_cli.stdw_zeta_bound),
                float(args_cli.stdw_zeta_write_scale),
            ).detach().cpu().tolist()
            stdw_zeta_delta_norm = float(stdw_zeta_delta.detach().norm().item())
        else:
            zeta_multiplier_row = [float("nan")] * 4
            stdw_zeta_delta_norm = float("nan")

        row = {
            "step": step,
            "time_s": float(step * time_axis_dt),
            "rho": float(drift_frac),
            "drift_fraction": float(drift_frac),
            "use_stdw": bool(args_cli.use_stdw),
            "use_filter": bool(args_cli.enable_filter),
            "use_quantile_filter": bool(args_cli.use_quantile_filter),
            "raw_error": float(raw_err),
            "filtered_error": float(filt_err),
            "compound_error": float(compound_error),
            "metric_contract_version": DEPTH_BARRIER_CONTRACT_VERSION,
            "depth_reference_frame": str(args_cli.depth_reference_frame),
            "depth_surface_z": float(args_cli.depth_surface_z),
            "depth_upper_limit": float(depth_limits["depth_upper_limit"]),
            "depth_upper_safe": float(depth_limits["depth_upper_safe"]),
            "depth_lower_safe": float(depth_limits["depth_lower_safe"]),
            "depth_lower_limit": float(depth_limits["depth_lower_limit"]),
            "depth_tube_width": float(depth_limits["depth_tube_width"]),
            "depth_transition_width": float(depth_limits["depth_transition_width"]),
            "env_eval_mode": bool(getattr(raw_env.unwrapped.cfg, "eval_mode", False)),
            "goal_spawn_radius": float(getattr(raw_env.unwrapped.cfg, "goal_spawn_radius", float("nan"))),
            "init_guidance_rate": float(getattr(raw_env.unwrapped.cfg, "init_guidance_rate", float("nan"))),
            "env_episode_step": int(env_episode_step),
            "starting_depth_raw": float(getattr(raw_env.unwrapped.cfg, "starting_depth", float("nan"))),
            "depth_lower_margin": depth_lower_margin,
            "depth_upper_margin": depth_upper_margin,
            "depth_in_hard_tube": int(depth_in_hard_tube),
            "des_depth_lower_margin": des_depth_lower_margin,
            "des_depth_upper_margin": des_depth_upper_margin,
            "des_depth_in_hard_tube": int(des_depth_in_hard_tube),
            "des_depth_in_safe_core": int(des_depth_in_safe_core),
            "attitude_tracking_mse": float(attitude_tracking_mse),
            "so3_attitude_error": float(so3_attitude_error),
            "depth_barrier_penalty": float(depth_barrier["depth_barrier_penalty"]),
            "depth_violation": float(depth_barrier["depth_violation"]),
            "depth_upper_transition_penalty": float(depth_barrier["depth_upper_transition_penalty"]),
            "depth_lower_transition_penalty": float(depth_barrier["depth_lower_transition_penalty"]),
            "saturation_authority_proxy": float(saturation_authority_proxy),
            "lyapunov_V": float(V_t),
            "lyapunov_dV": float(stdw_dV),
            "lyapunov_pass": float(lyapunov_pass),
            "lyapunov_pass_rate_window": float(lyapunov_pass_rate),
            "lyapunov_safety_block": int(is_lyapunov_blocked),
            "lyapunov_safety_reason": lyapunov_safety_reason,
            "stdw_safety_state": stdw_safety_state,
            "stdw_safety_transition": stdw_safety_transition,
            "stdw_fallback_step": int(stdw_fallback_step) if stdw_fallback_step is not None else "",
            "stdw_mask": float(stdw_mask_val),
            "effective_batch_frac": float(effective_batch_frac) if triggered_slow else float("nan"),
            "loss": float(loss_total) if triggered_slow else float("nan"),
            "loss_source": float(loss_src_val) if triggered_slow else float("nan"),
            "loss_target": float(loss_tgt_val) if triggered_slow else float("nan"),
            "loss_reg": float(loss_reg_val) if triggered_slow else float("nan"),
            "stdw_update_accepted": int(stdw_update_accepted),
            "stdw_update_rejected": int(stdw_update_rejected),
            "stdw_acceptance_reason": stdw_acceptance_reason,
            "stdw_behavior_mse_before": float(stdw_behavior_mse_before),
            "stdw_behavior_mse_after": float(stdw_behavior_mse_after),
            "stdw_behavior_mse_att_before": float(stdw_behavior_mse_att_before),
            "stdw_behavior_mse_att_after": float(stdw_behavior_mse_att_after),
            "stdw_behavior_mse_depth_before": float(stdw_behavior_mse_depth_before),
            "stdw_behavior_mse_depth_after": float(stdw_behavior_mse_depth_after),
            "stdw_action_delta_mse": float(stdw_action_delta_mse),
            "stdw_target_mse_before": float(stdw_target_mse_before),
            "stdw_target_mse_after": float(stdw_target_mse_after),
            "stdw_target_mse_after_roll_only": float(stdw_target_mse_after_roll_only),
            "stdw_target_mse_after_pitch_only": float(stdw_target_mse_after_pitch_only),
            "stdw_target_mse_after_yaw_only": float(stdw_target_mse_after_yaw_only),
            "stdw_target_mse_after_roll_pitch": float(stdw_target_mse_after_roll_pitch),
            "stdw_target_mse_after_roll_yaw": float(stdw_target_mse_after_roll_yaw),
            "stdw_target_mse_after_pitch_yaw": float(stdw_target_mse_after_pitch_yaw),
            "stdw_target_mse_att_before": float(stdw_target_mse_att_before),
            "stdw_target_mse_att_after": float(stdw_target_mse_att_after),
            "stdw_target_mse_depth_before": float(stdw_target_mse_depth_before),
            "stdw_target_mse_depth_after": float(stdw_target_mse_depth_after),
            "stdw_anchor_mse_to_ref": float(stdw_anchor_mse_to_ref),
            "stdw_anchor_mse_to_policy": float(stdw_anchor_mse_to_policy),
            "stdw_anchor_mse_to_opr": float(stdw_anchor_mse_to_opr),
            "stdw_anchor_mse_att_to_policy": float(stdw_anchor_mse_att_to_policy),
            "stdw_anchor_mse_depth_to_policy": float(stdw_anchor_mse_depth_to_policy),
            "stdw_anchor_mse_att_to_opr": float(stdw_anchor_mse_att_to_opr),
            "stdw_anchor_mse_depth_to_opr": float(stdw_anchor_mse_depth_to_opr),
            "stdw_anchor_delta_att_norm_to_policy": float(stdw_anchor_delta_att_norm_to_policy),
            "stdw_anchor_delta_depth_abs_to_policy": float(stdw_anchor_delta_depth_abs_to_policy),
            "stdw_zeta_write_scale": float(stdw_zeta_write_scale),
            "stdw_action_bridge_residual_scale": float(stdw_action_bridge_residual_scale),
            "stdw_action_bridge_residual_clip": float(stdw_action_bridge_residual_clip),
            "stdw_action_bridge_upstream_mode": str(args_cli.stdw_action_bridge_upstream_mode),
            "stdw_reduced_action_anchor_enable": bool(stdw_reduced_action_anchor_enable),
            "stdw_reduced_action_anchor_scale": float(stdw_reduced_action_anchor_scale),
            "stdw_reduced_action_anchor_clip": float(stdw_reduced_action_anchor_clip),
            "stdw_reduced_action_anchor_channels": str(stdw_reduced_action_anchor_channels),
            "stdw_reduced_action_anchor_geo_residual_scale": float(
                args_cli.stdw_reduced_action_anchor_geo_residual_scale
            ),
            "stdw_reduced_action_anchor_sswp_sign_enable": bool(
                args_cli.stdw_reduced_action_anchor_sswp_sign_enable
            ),
            "stdw_reduced_action_anchor_dual_source_gate": bool(
                args_cli.stdw_reduced_action_anchor_dual_source_gate
            ),
            "stdw_reduced_action_anchor_sswp_beta": float(
                args_cli.stdw_reduced_action_anchor_sswp_beta
            ),
            "stdw_reduced_action_anchor_consensus_gate": bool(
                args_cli.stdw_reduced_action_anchor_consensus_gate
            ),
            "stdw_reduced_action_anchor_consensus_preferred_sign": bool(
                args_cli.stdw_reduced_action_anchor_consensus_preferred_sign
            ),
            "stdw_bridge_residual_att_norm": float(stdw_bridge_residual_att_norm),
            "stdw_bridge_residual_depth_abs": float(stdw_bridge_residual_depth_abs),
            "fast_reduced_action_anchor_att_norm": float(fast_reduced_action_anchor_att_norm),
            "fast_reduced_action_anchor_depth_abs": float(fast_reduced_action_anchor_depth_abs),
            "fast_reduced_action_anchor_consensus_changed_frac": float(
                fast_reduced_action_anchor_consensus_changed_frac
            ),
            "fast_reduced_action_anchor_raw_sswp_match_frac": float(
                fast_reduced_action_anchor_raw_sswp_match_frac
            ),
            "fast_reduced_action_anchor_raw_track_match_frac": float(
                fast_reduced_action_anchor_raw_track_match_frac
            ),
            "fast_reduced_action_anchor_sswp_track_agree_frac": float(
                fast_reduced_action_anchor_sswp_track_agree_frac
            ),
            "stdw_write_progress_att_ratio": float(stdw_write_progress_att_ratio),
            "stdw_write_progress_depth_ratio": float(stdw_write_progress_depth_ratio),
            "stdw_tgt_action_roll_abs_before": float(stdw_tgt_action_roll_abs_before),
            "stdw_tgt_action_pitch_abs_before": float(stdw_tgt_action_pitch_abs_before),
            "stdw_tgt_action_yaw_abs_before": float(stdw_tgt_action_yaw_abs_before),
            "stdw_tgt_action_depth_abs_before": float(stdw_tgt_action_depth_abs_before),
            "stdw_update_delta_action_roll_abs": float(stdw_update_delta_action_roll_abs),
            "stdw_update_delta_action_pitch_abs": float(stdw_update_delta_action_pitch_abs),
            "stdw_update_delta_action_yaw_abs": float(stdw_update_delta_action_yaw_abs),
            "stdw_update_delta_action_depth_abs_tgt": float(stdw_update_delta_action_depth_abs_tgt),
            "stdw_zeta_to_action_gain_roll": float(stdw_zeta_to_action_gain_roll),
            "stdw_zeta_to_action_gain_pitch": float(stdw_zeta_to_action_gain_pitch),
            "stdw_zeta_to_action_gain_yaw": float(stdw_zeta_to_action_gain_yaw),
            "stdw_zeta_to_action_gain_depth": float(stdw_zeta_to_action_gain_depth),
            "stdw_anchor_abs_mean": float(stdw_anchor_abs_mean),
            "stdw_anchor_abs_max": float(stdw_anchor_abs_max),
            "stdw_action_bridge_delta_id_vs_policy_delta_mean_abs": float(
                stdw_action_bridge_delta_id_vs_policy_delta_mean_abs
            ),
            "stdw_action_bridge_delta_id_vs_policy_sign_match_frac": float(
                stdw_action_bridge_delta_id_vs_policy_sign_match_frac
            ),
            "stdw_action_bridge_delta_id_vs_policy_clipped_mean_abs": float(
                stdw_action_bridge_delta_id_vs_policy_clipped_mean_abs
            ),
            "stdw_action_bridge_self_vs_policy_state_mean_abs": float(
                stdw_action_bridge_self_vs_policy_state_mean_abs
            ),
            "stdw_action_bridge_abs_vs_policy_z_mean_abs": float(
                stdw_action_bridge_abs_vs_policy_z_mean_abs
            ),
            "stdw_l_tgt_space": str(stdw_l_tgt_space),
            "stdw_l_tgt_state_val": float(stdw_l_tgt_state_val),
            "stdw_z_match_norm_mean": float(stdw_z_match_norm_mean),
            "stdw_phi_pred_norm_mean": float(stdw_phi_pred_norm_mean),
            "stdw_l_tgt_normalize_denom": float(stdw_l_tgt_normalize_denom),
            "stdw_state_anchor_source": str(stdw_state_anchor_source),
            "stdw_fm_bridge_alpha": float(stdw_fm_bridge_alpha),
            "stdw_fm_bridge_curvature": float(stdw_fm_bridge_curvature),
            "stdw_fm_bridge_shift_norm_mean": float(stdw_fm_bridge_shift_norm_mean),
            "stdw_fm_bridge_shift_norm_p95": float(stdw_fm_bridge_shift_norm_p95),
            "stdw_update_target": str(stdw_update_target),
            "stdw_target_domain_mode": str(args_cli.stdw_target_domain_mode),
            "stdw_zeta_multiplier_roll": float(zeta_multiplier_row[0]),
            "stdw_zeta_multiplier_pitch": float(zeta_multiplier_row[1]),
            "stdw_zeta_multiplier_yaw": float(zeta_multiplier_row[2]),
            "stdw_zeta_multiplier_depth": float(zeta_multiplier_row[3]),
            "stdw_zeta_delta_norm": float(stdw_zeta_delta_norm),
            "pseudo_action": pseudo_action_list,
            "pseudo_action_delta_norm": float(pseudo_action_delta_norm),
            "pseudo_action_delta_abs_mean": float(pseudo_action_delta_abs_mean),
            "pseudo_action_action_corr": float(pseudo_action_action_corr),
            "pseudo_action_sign_flip_rate": float(pseudo_action_sign_flip_rate),
            "phase4a_signal_probe": bool(args_cli.phase4a_signal_probe),
            "phase4a_legacy_equals_clipped_action": float(phase4a_legacy_equals_clipped_action),
            "phase4a_pseudo_to_clipped_action_max_abs": float(phase4a_pseudo_to_clip_max_abs),
            "phase4a_action_out_of_unit_channel_fraction": float(phase4a_action_oob_fraction),
            "phase4a_action_to_clipped_action_delta_norm": float(phase4a_action_to_clip_delta_norm),
            "phase4a_pseudo_target_clip_channel_fraction": float(phase4a_pseudo_target_clip_fraction),
            **phase4a_sswp_contract,
            **phase4a_descent_contract,
            "phase4a_descent_triggered": int(phase4a_descent_triggered),
            "phase4a_descent_align": float(phase4a_descent_align),
            "stdw_dir_guard_pass_rate": float(stdw_dir_guard_pass_rate),
            "stdw_dir_guard_align": float(stdw_dir_guard_align),
            "stdw_direction_gate_source": str(stdw_direction_gate_source),
            "stdw_direction_gate_dot": float(stdw_direction_gate_dot),
            "stdw_direction_gate_dot_att": float(stdw_direction_gate_dot_att),
            "stdw_direction_gate_dot_depth": float(stdw_direction_gate_dot_depth),
            "stdw_update_delta_action_att_norm": float(stdw_update_delta_action_att_norm),
            "stdw_update_delta_action_depth_abs": float(stdw_update_delta_action_depth_abs),
            "stdw_zeta_delta_roll": float(stdw_zeta_delta_roll),
            "stdw_zeta_delta_pitch": float(stdw_zeta_delta_pitch),
            "stdw_zeta_delta_yaw": float(stdw_zeta_delta_yaw),
            "stdw_zeta_delta_depth": float(stdw_zeta_delta_depth),
            "stdw_depth_guard_active": int(bool(args_cli.stdw_depth_guard)),
            "stdw_depth_guard_blocked": int(stdw_depth_guard_blocked),
            "stdw_depth_guard_old_multiplier": float(stdw_depth_guard_old_multiplier),
            "stdw_depth_guard_new_multiplier": float(stdw_depth_guard_new_multiplier),
            "task_a_depth_failsafe_mode": str(args_cli.task_a_depth_failsafe_mode),
            "task_a_depth_failsafe_active": int(task_a_depth_failsafe_active),
            "task_a_depth_failsafe_depth_v1": float(task_a_depth_failsafe_depth_v1),
            "task_a_depth_failsafe_delta_norm": float(task_a_depth_failsafe_delta_norm),
            "stdw_slow_loop_dry_run": bool(args_cli.slow_loop_dry_run),
            "stdw_preserve_rng": bool(args_cli.preserve_rng_around_slow_loop),
            "policy_training_mode": bool(policy.training),
            "policy_param_l2_from_start": float(policy_param_l2_from_start),
            "fast_action_ref_mse": float(fast_action_ref_mse),
            "fast_action_ref_abs_max": float(fast_action_ref_abs_max),
            "fast_bridge_residual_att_norm": float(fast_bridge_residual_att_norm),
            "fast_bridge_residual_depth_abs": float(fast_bridge_residual_depth_abs),
            "boundary_submersion_ratio": boundary_submersion_ratio,
            "boundary_residual_dB": boundary_residual_dB,
            "boundary_ground_mag": boundary_ground_mag,
            "control_effort": float(control_effort),
            "trigger_gate_silenced": int(gate_silenced),
            "episode_reset": int(done_flag),
            "domain_bias": float(domain_bias),
            "fluid_vx": fluid_velocity[0] if len(fluid_velocity) > 0 else 0.0,
            "fluid_vy": fluid_velocity[1] if len(fluid_velocity) > 1 else 0.0,
            "fluid_vz": fluid_velocity[2] if len(fluid_velocity) > 2 else 0.0,
            "volume_mean": float(volume_mean),
            "des_roll": des_roll,
            "des_pitch": des_pitch,
            "des_yaw": des_yaw,
            "des_depth": des_depth,
            "des_depth_v1": des_depth_v1,
            "true_x": true_x,
            "true_y": true_y,
            "true_z": true_z,
            "true_depth_v1": true_depth_v1,
            "true_roll": true_roll,
            "true_pitch": true_pitch,
            "true_yaw": true_yaw,
            "true_pose": [true_x, true_y, true_z, true_roll, true_pitch, true_yaw],
            "executed_action": executed_action_list,
            "runtime_control_logged": bool(runtime_control.get("runtime_control_logged", False)),
            "com_to_cob_offset_x": offset_row[0] if len(offset_row) > 0 else 0.0,
            "com_to_cob_offset_y": offset_row[1] if len(offset_row) > 1 else 0.0,
            "com_to_cob_offset_z": offset_row[2] if len(offset_row) > 2 else 0.0,
            # Scenario / disturbance-schedule snapshot (NaN/empty when --scenario is None).
            "scenario": schedule_snapshot.get("scenario", args_cli.scenario or "manual"),
            "embodiment": str(args_cli.embodiment),
            "disturbance_mode": schedule_snapshot.get("disturbance_mode", ""),
            "episode_id": int(current_episode_id),
            "episode_start_step": int(current_episode_start_step),
            "episode_length_steps": int(episode_length_steps),
            "episode_branch_at_start": current_episode_branch,
            "episode_branch_at_reset": episode_branch_at_reset,
            "episode_reset_reason": episode_reset_reason,
            "reference_mode_runtime": reference_mode_runtime,
            "mixed_reference_branch": mixed_reference_branch,
            "mixed_reference_is_flip": mixed_reference_is_flip,
            "amp_x": schedule_snapshot.get("amp_x", float("nan")),
            "amp_y": schedule_snapshot.get("amp_y", float("nan")),
            "amp_z": schedule_snapshot.get("amp_z", float("nan")),
            "noise_std_eff": schedule_snapshot.get("noise_std_eff", ""),
            "fault_active": bool(schedule_snapshot.get("fault_active", False)),
            "fault_efficiency_min": schedule_snapshot.get("fault_efficiency_min", ""),
        }
        row.update(runtime_control)
        row.update(phase56_runtime_row)
        row.update(phase56_curvature_row)
        logger.append(row)

        if slow_due:
            print(
                f"## EVALUATION LOG ## [STDW-Slow] Triggered: {is_triggered} "
                f"(step={step} filt_err={filt_err:.6f} thr={args_cli.trigger_threshold:.6f} "
                f"gate={'on' if args_cli.enable_trigger_gate else 'off'} "
                f"lyap_block={int(is_lyapunov_blocked)} state={stdw_safety_state} "
                f"phase56_state={phase56_state_for_row} "
                f"phase56_exec_block={int(phase56_execution_blocks_slow_loop)} "
                f"transition={stdw_safety_transition or '-'} reason={lyapunov_safety_reason})",
                flush=True,
            )
        if triggered_slow:
            print(
                "## EVALUATION LOG ## "
                f"[STDW-Slow] step={step} rho={drift_frac:.3f} loss={loss_total:.6e} "
                f"L_src={loss_src_val:.6e} L_tgt={loss_tgt_val:.6e} L_reg={loss_reg_val:.6e} "
                f"eff_frac={effective_batch_frac:.3f}",
                flush=True,
            )

        if (
            bool(args_cli.save_stdw_ckpt)
            and int(args_cli.stdw_ckpt_interval) > 0
            and (step > 0)
            and (
                step % int(args_cli.stdw_ckpt_interval) == 0
                or step == int(args_cli.total_steps) - 1
            )
        ):
            ckpt_info = _save_stdw_checkpoint(
                ckpt_dir=ckpt_dir,
                step=step,
                policy=policy,
                obs_normalizer=obs_normalizer,
                optimizer=optimizer,
                metadata={
                    "step": int(step),
                    "source_checkpoint": str(resume_path),
                    "task": str(args_cli.task),
                    "embodiment": str(args_cli.embodiment),
                    "target_drift": float(effective_target_drift),
                    "drift_axes": list(effective_drift_axes),
                    "slow_loop_triggers": int(slow_loop_triggers),
                    "final_mse_window_mean": float(np.mean(final_mse_window)) if len(final_mse_window) > 0 else None,
                },
                export_deploy_jit=bool(args_cli.export_deploy_jit),
                dummy_obs_dim=int(env_cfg.num_observations),
                device=runtime_device,
            )
            saved_ckpts.append(ckpt_info)
            keep_last = int(args_cli.stdw_ckpt_keep_last)
            if keep_last > 0 and len(saved_ckpts) > keep_last:
                stale = saved_ckpts[:-keep_last]
                saved_ckpts = saved_ckpts[-keep_last:]
                for item in stale:
                    for path_value in item.values():
                        if path_value:
                            try:
                                Path(path_value).unlink(missing_ok=True)
                            except Exception:
                                pass
            print(f"[STDW-CKPT] saved step={step} paths={ckpt_info}", flush=True)

        if bool(args_cli.phase56_runtime_execution_hooks) and phase56_requested_reset:
            try:
                if phase56_runtime_reset_entry_step is not None:
                    phase56_runtime_reset_durations.append(int(step - phase56_runtime_reset_entry_step + 1))
                if phase56_runtime_cycle_start_step is not None:
                    phase56_runtime_cycle_durations.append(int(step - phase56_runtime_cycle_start_step + 1))
                    phase56_runtime_completed_cycle_count += 1
                phase56_runtime_sleep_count += 1
                phase56_runtime_last_reset_step = int(step)
                next_obs = _reset_wrapper_env(env)
                if not done_flag:
                    reset_count += 1
                stdw_wrapper.clear_drift_freeze()
                phase56_runtime_state = "NOMINAL_LOCKED"
                phase56_runtime_state_age = 1
                phase56_runtime_recovery_streak = 0
                phase56_runtime_active_entry_step = None
                phase56_runtime_frozen_entry_step = None
                phase56_runtime_fallback_entry_step = None
                phase56_runtime_reset_entry_step = None
                phase56_runtime_cycle_start_step = None
                current_episode_id += 1
                current_episode_start_step = int(step + 1)
                _, current_episode_branch, _ = _runtime_reference_context(raw_env)
            except Exception as exc:
                print(f"[WARN] phase56 runtime reset hook failed at step {step}: {exc}", flush=True)
        elif done_flag:
            current_episode_id += 1
            current_episode_start_step = int(step + 1)
            _, current_episode_branch, _ = _runtime_reference_context(raw_env)

        obs = next_obs
        prev_V = float(V_t)

    logger.close()

    # ---- collect final summary + plots ----
    csv_df = logger.to_frame()

    try:
        diagnostic_plot_paths, tracking_mse_summary = _plot_stdw_diagnostics(
            csv_df,
            stdw_run_dir,
            volume_jump_step=None,
            flow_jump_step=None,
            best_save_step=None,
        )
    except Exception as exc:
        import traceback as _tb
        print(f"[WARN] plotting failed: {exc}")
        _tb.print_exc()
        diagnostic_plot_paths = {}
        tracking_mse_summary = {}

    final_mse = float(np.mean(final_mse_window)) if len(final_mse_window) > 0 else None
    if bool(args_cli.save_stdw_ckpt) and not saved_ckpts:
        final_step = max(int(args_cli.total_steps) - 1, 0)
        ckpt_info = _save_stdw_checkpoint(
            ckpt_dir=ckpt_dir,
            step=final_step,
            policy=policy,
            obs_normalizer=obs_normalizer,
            optimizer=optimizer,
            metadata={
                "step": int(final_step),
                "source_checkpoint": str(resume_path),
                "task": str(args_cli.task),
                "embodiment": str(args_cli.embodiment),
                "target_drift": float(effective_target_drift),
                "drift_axes": list(effective_drift_axes),
                "slow_loop_triggers": int(slow_loop_triggers),
                "final_mse_window_mean": final_mse,
            },
            export_deploy_jit=bool(args_cli.export_deploy_jit),
            dummy_obs_dim=int(env_cfg.num_observations),
            device=runtime_device,
        )
        saved_ckpts.append(ckpt_info)
        print(f"[STDW-CKPT] saved final paths={ckpt_info}", flush=True)

    # Stationary-window MSE: only steps strictly after drift_end_step (when scenario
    # has fully ramped). Falls back to None if no qualifying rows are present.
    final_mse_after_drift: Optional[float] = None
    lyapunov_pass_rate_mean: Optional[float] = None
    effective_batch_frac_mean: Optional[float] = None
    anchor_mse_to_ref_mean: Optional[float] = None
    anchor_mse_to_policy_mean: Optional[float] = None
    anchor_mse_to_opr_mean: Optional[float] = None
    pseudo_action_delta_norm_mean: Optional[float] = None
    pseudo_action_delta_norm_p95: Optional[float] = None
    pseudo_action_delta_abs_mean: Optional[float] = None
    pseudo_action_action_corr_mean: Optional[float] = None
    pseudo_action_sign_flip_rate_mean: Optional[float] = None
    policy_param_l2_from_start_final: Optional[float] = None
    runtime_motor_saturation_ratio_mean: Optional[float] = None
    runtime_motor_abs_max_raw_mean: Optional[float] = None
    runtime_motor_abs_max_raw_p95: Optional[float] = None
    runtime_motor_abs_max_raw_max: Optional[float] = None
    runtime_motor_headroom_min: Optional[float] = None
    runtime_motor_near_saturation_time_fraction: Optional[float] = None
    runtime_pid_depth_mean: Optional[float] = None
    runtime_pid_depth_min: Optional[float] = None
    runtime_pid_depth_max: Optional[float] = None
    final_attitude_mse: Optional[float] = None
    mean_so3_attitude_error: Optional[float] = None
    true_depth_v1_mean: Optional[float] = None
    true_depth_v1_min: Optional[float] = None
    true_depth_v1_max: Optional[float] = None
    des_depth_v1_mean: Optional[float] = None
    des_depth_v1_min: Optional[float] = None
    des_depth_v1_max: Optional[float] = None
    first_true_z: Optional[float] = None
    first_true_depth_v1: Optional[float] = None
    first_des_depth_v1: Optional[float] = None
    first_depth_raw_offset_from_starting: Optional[float] = None
    first_depth_lower_margin: Optional[float] = None
    first_depth_upper_margin: Optional[float] = None
    first_depth_in_hard_tube: Optional[bool] = None
    first_des_depth_in_safe_core: Optional[bool] = None
    v1_depth_barrier_summary: dict = {}
    v1_saturation_summary: dict = {}
    try:
        if "compound_error" in csv_df.columns and "step" in csv_df.columns:
            tail = csv_df[csv_df["step"] > int(args_cli.drift_end_step)]
            if len(tail) > 0:
                signal_col = "filtered_error" if (args_cli.enable_filter and "filtered_error" in tail.columns) else "compound_error"
                vals = tail[signal_col].astype(float).dropna()
                if len(vals) > 0:
                    final_mse_after_drift = float(vals.mean())
        if "lyapunov_pass" in csv_df.columns:
            vals = csv_df["lyapunov_pass"].astype(float).dropna()
            if len(vals) > 0:
                lyapunov_pass_rate_mean = float(vals.mean())
        if "effective_batch_frac" in csv_df.columns:
            vals = csv_df["effective_batch_frac"].astype(float).dropna()
            if len(vals) > 0:
                effective_batch_frac_mean = float(vals.mean())
        if "stdw_anchor_mse_to_ref" in csv_df.columns:
            vals = csv_df["stdw_anchor_mse_to_ref"].astype(float).dropna()
            if len(vals) > 0:
                anchor_mse_to_ref_mean = float(vals.mean())
        if "stdw_anchor_mse_to_policy" in csv_df.columns:
            vals = csv_df["stdw_anchor_mse_to_policy"].astype(float).dropna()
            if len(vals) > 0:
                anchor_mse_to_policy_mean = float(vals.mean())
        if "stdw_anchor_mse_to_opr" in csv_df.columns:
            vals = csv_df["stdw_anchor_mse_to_opr"].astype(float).dropna()
            if len(vals) > 0:
                anchor_mse_to_opr_mean = float(vals.mean())
        if "pseudo_action_delta_norm" in csv_df.columns:
            vals = csv_df["pseudo_action_delta_norm"].astype(float).dropna()
            if len(vals) > 0:
                pseudo_action_delta_norm_mean = float(vals.mean())
                pseudo_action_delta_norm_p95 = float(vals.quantile(0.95))
        if "pseudo_action_delta_abs_mean" in csv_df.columns:
            vals = csv_df["pseudo_action_delta_abs_mean"].astype(float).dropna()
            if len(vals) > 0:
                pseudo_action_delta_abs_mean = float(vals.mean())
        if "pseudo_action_action_corr" in csv_df.columns:
            vals = csv_df["pseudo_action_action_corr"].astype(float).dropna()
            if len(vals) > 0:
                pseudo_action_action_corr_mean = float(vals.mean())
        if "pseudo_action_sign_flip_rate" in csv_df.columns:
            vals = csv_df["pseudo_action_sign_flip_rate"].astype(float).dropna()
            if len(vals) > 0:
                pseudo_action_sign_flip_rate_mean = float(vals.mean())
        if "policy_param_l2_from_start" in csv_df.columns:
            vals = csv_df["policy_param_l2_from_start"].astype(float).dropna()
            if len(vals) > 0:
                policy_param_l2_from_start_final = float(vals.iloc[-1])
        if "runtime_motor_saturation_ratio" in csv_df.columns:
            vals = csv_df["runtime_motor_saturation_ratio"].astype(float).dropna()
            if len(vals) > 0:
                runtime_motor_saturation_ratio_mean = float(vals.mean())
                v1_saturation_summary = calculate_actuator_saturation_stats(vals.to_numpy(dtype=float))
        if "runtime_motor_abs_max_raw" in csv_df.columns:
            vals = csv_df["runtime_motor_abs_max_raw"].astype(float).dropna()
            if len(vals) > 0:
                runtime_motor_abs_max_raw_mean = float(vals.mean())
                runtime_motor_abs_max_raw_p95 = float(vals.quantile(0.95))
                runtime_motor_abs_max_raw_max = float(vals.max())
                runtime_motor_headroom_min = float(1.0 - vals.max())
                runtime_motor_near_saturation_time_fraction = float((vals >= 0.98).mean())
        if "runtime_pid_depth" in csv_df.columns:
            vals = csv_df["runtime_pid_depth"].astype(float).dropna()
            if len(vals) > 0:
                runtime_pid_depth_mean = float(vals.mean())
                runtime_pid_depth_min = float(vals.min())
                runtime_pid_depth_max = float(vals.max())
        if "attitude_tracking_mse" in csv_df.columns:
            tail = csv_df.tail(max(int(args_cli.final_mse_window), 1))
            vals = tail["attitude_tracking_mse"].astype(float).dropna()
            if len(vals) > 0:
                final_attitude_mse = float(vals.mean())
        if "so3_attitude_error" in csv_df.columns:
            vals = csv_df["so3_attitude_error"].astype(float).dropna()
            if len(vals) > 0:
                mean_so3_attitude_error = float(vals.mean())
        true_depth_v1_values = np.asarray([], dtype=float)
        if "true_depth_v1" in csv_df.columns:
            true_depth_v1_values = csv_df["true_depth_v1"].astype(float).to_numpy()
        elif "true_z" in csv_df.columns:
            true_depth_v1_values = np.asarray(_depth_to_v1(csv_df["true_z"].astype(float).to_numpy()), dtype=float)
        true_depth_v1_finite = true_depth_v1_values[np.isfinite(true_depth_v1_values)]
        if true_depth_v1_finite.size > 0:
            true_depth_v1_mean = float(np.mean(true_depth_v1_finite))
            true_depth_v1_min = float(np.min(true_depth_v1_finite))
            true_depth_v1_max = float(np.max(true_depth_v1_finite))
            v1_depth_barrier_summary = _depth_barrier_for_v1(true_depth_v1_values)
            v1_depth_barrier_summary.update(
                {
                    "depth_reference_frame": str(args_cli.depth_reference_frame),
                    "depth_surface_z": float(args_cli.depth_surface_z),
                    "depth_tube_width": float(depth_limits["depth_tube_width"]),
                    "depth_transition_width": float(depth_limits["depth_transition_width"]),
                }
            )
        des_depth_v1_values = np.asarray([], dtype=float)
        if "des_depth_v1" in csv_df.columns:
            des_depth_v1_values = csv_df["des_depth_v1"].astype(float).to_numpy()
        elif "des_depth" in csv_df.columns:
            des_depth_v1_values = np.asarray(_depth_to_v1(csv_df["des_depth"].astype(float).to_numpy()), dtype=float)
        des_depth_v1_finite = des_depth_v1_values[np.isfinite(des_depth_v1_values)]
        if des_depth_v1_finite.size > 0:
            des_depth_v1_mean = float(np.mean(des_depth_v1_finite))
            des_depth_v1_min = float(np.min(des_depth_v1_finite))
            des_depth_v1_max = float(np.max(des_depth_v1_finite))
        if len(csv_df) > 0:
            first_row = csv_df.iloc[0]
            if "true_z" in csv_df.columns:
                first_true_z = float(first_row["true_z"])
            if true_depth_v1_values.size > 0:
                first_true_depth_v1 = float(true_depth_v1_values[0])
                first_depth_lower_margin = float(first_true_depth_v1 - float(depth_limits["depth_lower_limit"]))
                first_depth_upper_margin = float(float(depth_limits["depth_upper_limit"]) - first_true_depth_v1)
                first_depth_in_hard_tube = bool(
                    float(depth_limits["depth_lower_limit"])
                    <= first_true_depth_v1
                    <= float(depth_limits["depth_upper_limit"])
                )
            if des_depth_v1_values.size > 0:
                first_des_depth_v1 = float(des_depth_v1_values[0])
                first_des_depth_in_safe_core = bool(
                    float(depth_limits["depth_lower_safe"])
                    <= first_des_depth_v1
                    <= float(depth_limits["depth_upper_safe"])
                )
            if first_true_z is not None:
                first_depth_raw_offset_from_starting = float(
                    first_true_z - float(getattr(raw_env.unwrapped.cfg, "starting_depth", 0.0))
                )
    except Exception as exc:  # pragma: no cover
        print(f"[WARN] final_mse_after_drift computation failed: {exc}")

    summary = {
        "csv_path": str(csv_path),
        "buffer_path": str(stdw_run_dir / "buffer.pt"),
        "use_stdw": bool(args_cli.use_stdw),
        "enable_filter": bool(args_cli.enable_filter),
        "use_quantile_filter": bool(args_cli.use_quantile_filter),
        "discard_ratio": float(args_cli.discard_ratio),
        "g_C_lr": float(args_cli.g_C_lr),
        "lambda_reg": float(args_cli.lambda_reg),
        "reg_mode": str(args_cli.reg_mode),
        "stdw_update_target": str(stdw_update_target),
        "stdw_zeta_lr": float(args_cli.stdw_zeta_lr) if args_cli.stdw_zeta_lr is not None else None,
        "stdw_zeta_bound": float(args_cli.stdw_zeta_bound),
        "stdw_zeta_reg": float(args_cli.stdw_zeta_reg),
        "stdw_zeta_write_scale": float(args_cli.stdw_zeta_write_scale),
        "stdw_action_bridge_residual_scale": float(args_cli.stdw_action_bridge_residual_scale),
        "stdw_action_bridge_residual_clip": float(args_cli.stdw_action_bridge_residual_clip),
        "stdw_zeta_grad_mask": (
            stdw_zeta_grad_mask.detach().cpu().tolist() if stdw_zeta_grad_mask is not None else None
        ),
        "stdw_zeta_multiplier_final": (
            _effective_zeta4_multipliers(
                stdw_zeta_delta,
                float(args_cli.stdw_zeta_bound),
                float(args_cli.stdw_zeta_write_scale),
            ).detach().cpu().tolist()
            if stdw_zeta_delta is not None
            else None
        ),
        "stdw_state_anchor_source": str(args_cli.state_match_z_source),
        "stdw_fm_bridge_alpha": (
            float(state_match_fm_bridge_alpha)
            if str(args_cli.state_match_z_source) == "fm_midpoint"
            else None
        ),
        "stdw_fm_bridge_curvature_mean": (
            float(pd.to_numeric(csv_df.get("stdw_fm_bridge_curvature"), errors="coerce").mean())
            if "stdw_fm_bridge_curvature" in csv_df.columns
            else None
        ),
        "stdw_fm_bridge_curvature_p95": (
            float(pd.to_numeric(csv_df.get("stdw_fm_bridge_curvature"), errors="coerce").quantile(0.95))
            if "stdw_fm_bridge_curvature" in csv_df.columns
            else None
        ),
        "stdw_fm_bridge_shift_norm_mean": (
            float(pd.to_numeric(csv_df.get("stdw_fm_bridge_shift_norm_mean"), errors="coerce").mean())
            if "stdw_fm_bridge_shift_norm_mean" in csv_df.columns
            else None
        ),
        "target_drift": float(effective_target_drift),
        "target_drift_requested": float(args_cli.target_drift),
        "drift_start_step": int(args_cli.drift_start_step),
        "drift_end_step": int(args_cli.drift_end_step),
        "drift_axes": list(effective_drift_axes),
        "drift_axes_requested": list(_parse_axes(args_cli.drift_axes)),
        "auto_drift_router": bool(args_cli.auto_drift_router),
        "drift_router_mode": str(args_cli.drift_router_mode),
        "drift_router_xy_threshold": float(args_cli.drift_router_xy_threshold),
        "initial_com_to_cob_x": float(initial_cob_xy[0]),
        "initial_com_to_cob_y": float(initial_cob_xy[1]),
        "ramp_shape": str(args_cli.ramp_shape),
        "pid_multipliers": args_cli.pid_multipliers,
        "ctrl_mismatch": args_cli.ctrl_mismatch,
        "boundary_effect": args_cli.boundary_effect,
        "domain_adapt_backend": str(args_cli.domain_adapt_backend),
        "esuot_eps": float(args_cli.esuot_eps),
        "esuot_eta": float(args_cli.esuot_eta),
        "esuot_lambda1": float(args_cli.esuot_lambda1),
        "esuot_lambda2": float(args_cli.esuot_lambda2),
        "esuot_divergence": str(args_cli.esuot_divergence),
        "esuot_inner_iters": int(args_cli.esuot_inner_iters),
        "esuot_num_steps": int(args_cli.esuot_num_steps),
        "esuot_sinkhorn_iters": int(args_cli.esuot_sinkhorn_iters),
        "filter_window_seconds": float(args_cli.filter_window_seconds),
        "slow_loop_interval": int(args_cli.slow_loop_interval),
        "batch_size": int(args_cli.batch_size),
        "buffer_capacity": int(args_cli.buffer_capacity),
        "stdw_target_domain_mode": str(args_cli.stdw_target_domain_mode),
        "stdw_target_intermediate_frac": float(args_cli.stdw_target_intermediate_frac),
        "enable_pseudo_action": bool(args_cli.enable_pseudo_action),
        "pseudo_gain": float(args_cli.pseudo_gain),
        "pseudo_gate_limit": float(args_cli.pseudo_gate_limit),
        "pseudo_decay": float(args_cli.pseudo_decay),
        "pseudo_error_driven": bool(args_cli.pseudo_error_driven),
        "pseudo_error_gain": float(args_cli.pseudo_error_gain),
        "pseudo_action_target_mode": str(args_cli.pseudo_action_target_mode),
        "pseudo_action_analytic_mix": float(args_cli.pseudo_action_analytic_mix),
        "pseudo_action_residual_scale": float(args_cli.pseudo_action_residual_scale),
        "pseudo_action_residual_clip": float(args_cli.pseudo_action_residual_clip),
        "pseudo_action_residual_channels": str(args_cli.pseudo_action_residual_channels),
        "pseudo_action_residual_sign_aware": bool(args_cli.pseudo_action_residual_sign_aware),
        "pseudo_action_error_gate_metric": str(args_cli.pseudo_action_error_gate_metric),
        "pseudo_action_error_gate_threshold": float(args_cli.pseudo_action_error_gate_threshold),
        "control_profile": str(args_cli.control_profile),
        "enable_lyapunov_mask": bool(args_cli.enable_lyapunov_mask),
        "lyapunov_eps": float(args_cli.lyapunov_eps),
        "lyapunov_p_diag": list(_parse_p_diag(args_cli.lyapunov_p_diag)),
        "lyapunov_gate_mode": str(args_cli.lyapunov_gate_mode),
        "lyapunov_abs_margin": float(args_cli.lyapunov_abs_margin),
        "lyapunov_rel_margin": float(args_cli.lyapunov_rel_margin),
        "lyapunov_window_steps": int(args_cli.lyapunov_window_steps),
        "lyapunov_min_pass_rate": float(args_cli.lyapunov_min_pass_rate),
        "lyapunov_v_mode": str(args_cli.lyapunov_v_mode),
        "lyapunov_q_diag": list(_parse_p_diag(args_cli.lyapunov_q_diag)),
        "lyapunov_decay_alpha": float(args_cli.lyapunov_decay_alpha),
        "lyapunov_depth_barrier_mode": str(args_cli.lyapunov_depth_barrier_mode),
        "lyapunov_depth_barrier_half": float(args_cli.lyapunov_depth_barrier_half),
        "lyapunov_depth_barrier_soft": float(args_cli.lyapunov_depth_barrier_soft),
        "lyapunov_dv_criterion": str(args_cli.lyapunov_dv_criterion),
        "lyapunov_dv_eps_rel": float(args_cli.lyapunov_dv_eps_rel),
        "lyapunov_v_floor": float(args_cli.lyapunov_v_floor),
        "stdw_dir_guard": str(args_cli.stdw_dir_guard),
        "stdw_dir_guard_min_pass_rate": float(args_cli.stdw_dir_guard_min_pass_rate),
        "stdw_dir_guard_align_margin": float(args_cli.stdw_dir_guard_align_margin),
        "stdw_dir_guard_blocked_count": int(stdw_dir_guard_blocked_count),
        "stdw_direction_gate": bool(args_cli.stdw_direction_gate),
        "stdw_direction_gate_source": str(stdw_direction_gate_source),
        "stdw_direction_gate_min_dot": float(args_cli.stdw_direction_gate_min_dot),
        "stdw_depth_guard": bool(args_cli.stdw_depth_guard),
        "stdw_depth_guard_upper_trigger": float(args_cli.stdw_depth_guard_upper_trigger),
        "stdw_depth_guard_lower_trigger": float(args_cli.stdw_depth_guard_lower_trigger),
        "stdw_depth_guard_eps": float(args_cli.stdw_depth_guard_eps),
        "stdw_zeta_depth_min_multiplier": float(args_cli.stdw_zeta_depth_min_multiplier),
        "stdw_zeta_write_scale": float(args_cli.stdw_zeta_write_scale),
        "stdw_runtime_attitude_zeta_path": str(args_cli.stdw_runtime_attitude_zeta_path),
        "stdw_action_bridge_residual_scale": float(args_cli.stdw_action_bridge_residual_scale),
        "stdw_action_bridge_residual_clip": float(args_cli.stdw_action_bridge_residual_clip),
        "stdw_action_bridge_upstream_mode": str(args_cli.stdw_action_bridge_upstream_mode),
        "stdw_reduced_action_anchor_enable": bool(args_cli.stdw_reduced_action_anchor_enable),
        "stdw_reduced_action_anchor_scale": float(args_cli.stdw_reduced_action_anchor_scale),
        "stdw_reduced_action_anchor_clip": float(args_cli.stdw_reduced_action_anchor_clip),
        "stdw_reduced_action_anchor_channels": str(args_cli.stdw_reduced_action_anchor_channels),
        "stdw_reduced_action_anchor_geo_residual_scale": float(
            args_cli.stdw_reduced_action_anchor_geo_residual_scale
        ),
        "stdw_reduced_action_anchor_sswp_sign_enable": bool(
            args_cli.stdw_reduced_action_anchor_sswp_sign_enable
        ),
        "stdw_reduced_action_anchor_dual_source_gate": bool(
            args_cli.stdw_reduced_action_anchor_dual_source_gate
        ),
        "stdw_reduced_action_anchor_sswp_beta": float(
            args_cli.stdw_reduced_action_anchor_sswp_beta
        ),
        "stdw_reduced_action_anchor_consensus_gate": bool(
            args_cli.stdw_reduced_action_anchor_consensus_gate
        ),
        "stdw_reduced_action_anchor_consensus_preferred_sign": bool(
            args_cli.stdw_reduced_action_anchor_consensus_preferred_sign
        ),
        "task_a_depth_failsafe_mode": str(args_cli.task_a_depth_failsafe_mode),
        "task_a_depth_failsafe_lower_trigger": float(args_cli.task_a_depth_failsafe_lower_trigger),
        "task_a_depth_failsafe_release_trigger": float(args_cli.task_a_depth_failsafe_release_trigger),
        "task_a_depth_failsafe_target_v1": float(args_cli.task_a_depth_failsafe_target_v1),
        "task_a_depth_failsafe_blend": float(args_cli.task_a_depth_failsafe_blend),
        "task_a_depth_failsafe_sswp_scale": float(args_cli.task_a_depth_failsafe_sswp_scale),
        "task_a_depth_failsafe_active_count": int(task_a_depth_failsafe_active_count),
        "task_a_depth_failsafe_delta_norm_mean": float(
            task_a_depth_failsafe_delta_norm_sum / max(task_a_depth_failsafe_active_count, 1)
        ),
        "lyapunov_guard_action": str(args_cli.lyapunov_guard_action),
        "lyapunov_guard_confirm_steps": int(args_cli.lyapunov_guard_confirm_steps),
        "lyapunov_guard_recover_steps": int(args_cli.lyapunov_guard_recover_steps),
        "lyapunov_block_count": int(lyapunov_block_count),
        "lyapunov_zero_drift_count": int(lyapunov_zero_drift_count),
        "lyapunov_freeze_drift_count": int(lyapunov_freeze_drift_count),
        "stdw_safety_state_final": str(stdw_safety_state),
        "stdw_safety_transition_count": int(stdw_safety_transition_count),
        "stdw_suspect_enter_count": int(stdw_suspect_enter_count),
        "stdw_fallback_enter_count": int(stdw_fallback_enter_count),
        "stdw_recover_count": int(stdw_recover_count),
        "stdw_fallback_step": int(stdw_fallback_step) if stdw_fallback_step is not None else None,
          "stdw_update_acceptance": str(args_cli.stdw_update_acceptance),
          "stdw_target_domain_mode": str(args_cli.stdw_target_domain_mode),
          "stdw_target_intermediate_frac": float(args_cli.stdw_target_intermediate_frac),
          "stdw_replay_domain_counts": buffer.domain_counts(),
        "stdw_max_behavior_mse": float(args_cli.stdw_max_behavior_mse),
        "stdw_max_action_delta_mse": float(args_cli.stdw_max_action_delta_mse),
        "stdw_max_target_mse_increase": float(args_cli.stdw_max_target_mse_increase),
        "stdw_min_effective_batch_frac": float(args_cli.stdw_min_effective_batch_frac),
        "stdw_update_accepted_count": int(stdw_update_accepted_count),
        "stdw_update_rejected_count": int(stdw_update_rejected_count),
        "stdw_last_reject_reason": str(stdw_last_reject_reason),
        "lyapunov_pass_rate_mean": lyapunov_pass_rate_mean,
        "effective_batch_frac_mean": effective_batch_frac_mean,
        "stdw_anchor_mse_to_ref_mean": anchor_mse_to_ref_mean,
        "stdw_anchor_mse_to_policy_mean": anchor_mse_to_policy_mean,
        "stdw_anchor_mse_to_opr_mean": anchor_mse_to_opr_mean,
        "pseudo_action_delta_norm_mean": pseudo_action_delta_norm_mean,
        "pseudo_action_delta_norm_p95": pseudo_action_delta_norm_p95,
        "pseudo_action_delta_abs_mean": pseudo_action_delta_abs_mean,
        "pseudo_action_action_corr_mean": pseudo_action_action_corr_mean,
        "pseudo_action_sign_flip_rate_mean": pseudo_action_sign_flip_rate_mean,
        "policy_param_l2_from_start": policy_param_l2_from_start_final,
        "runtime_motor_saturation_ratio": runtime_motor_saturation_ratio_mean,
        "runtime_motor_abs_max_raw_mean": runtime_motor_abs_max_raw_mean,
        "runtime_motor_abs_max_raw_p95": runtime_motor_abs_max_raw_p95,
        "runtime_motor_abs_max_raw_max": runtime_motor_abs_max_raw_max,
        "runtime_motor_headroom_min": runtime_motor_headroom_min,
        "runtime_motor_near_saturation_time_fraction": runtime_motor_near_saturation_time_fraction,
        "runtime_pid_depth_mean": runtime_pid_depth_mean,
        "runtime_pid_depth_min": runtime_pid_depth_min,
        "runtime_pid_depth_max": runtime_pid_depth_max,
        "phase56_runtime_binding": bool(args_cli.phase56_runtime_binding),
        "phase56_runtime_binding_ready": bool(phase56_runtime_binding_ready),
        "phase56_runtime_reference_csv": str(args_cli.phase56_runtime_reference_csv) if args_cli.phase56_runtime_reference_csv else None,
        "phase56_runtime_bundle_dir": str(args_cli.phase56_runtime_bundle_dir) if args_cli.phase56_runtime_bundle_dir else None,
        "phase56_runtime_feature_set": str(args_cli.phase56_runtime_feature_set),
        "phase56_runtime_feature_columns": (
            list(phase56_runtime_bundle["feature_columns"])
            if isinstance(phase56_runtime_bundle, dict) and "feature_columns" in phase56_runtime_bundle
            else []
        ),
        "phase56_runtime_context_gate": str(args_cli.phase56_runtime_context_gate),
        "phase56_runtime_fm_profile": str(args_cli.phase56_runtime_fm_profile),
        "phase56_runtime_target_alpha": (
            float(phase56_runtime_bundle["target_alpha"])
            if isinstance(phase56_runtime_bundle, dict) and "target_alpha" in phase56_runtime_bundle
            else float(args_cli.phase56_runtime_target_alpha)
        ),
        "phase56_runtime_device": str(args_cli.phase56_runtime_device),
        "phase56_runtime_execution_hooks": bool(args_cli.phase56_runtime_execution_hooks),
        "phase56_runtime_frozen_min_dwell_steps": int(args_cli.phase56_runtime_frozen_min_dwell_steps),
        "phase56_runtime_frozen_recover_steps": int(args_cli.phase56_runtime_frozen_recover_steps),
        "phase56_runtime_fallback_dwell_steps": int(args_cli.phase56_runtime_fallback_dwell_steps),
        "phase56_runtime_reset_dwell_steps": int(args_cli.phase56_runtime_reset_dwell_steps),
        "phase56_runtime_binding_error": str(phase56_runtime_binding_error),
        "phase56_runtime_state_final": str(phase56_runtime_state),
        "phase56_runtime_state_age_final": int(phase56_runtime_state_age),
        "phase56_runtime_state_counts": phase56_runtime_state_counts,
        "phase56_runtime_state_transition_count": int(phase56_runtime_state_transition_count),
        "phase56_runtime_execution_blocked_count": int(phase56_runtime_execution_blocked_count),
        "phase56_runtime_freeze_apply_count": int(phase56_runtime_freeze_apply_count),
        "phase56_runtime_clear_freeze_count": int(phase56_runtime_clear_freeze_count),
        "phase56_runtime_zero_drift_count": int(phase56_runtime_zero_drift_count),
        "phase56_runtime_reset_request_count": int(phase56_runtime_reset_request_count),
        "phase56_runtime_wake_count": int(phase56_runtime_wake_count),
        "phase56_runtime_sleep_count": int(phase56_runtime_sleep_count),
        "phase56_runtime_completed_cycle_count": int(phase56_runtime_completed_cycle_count),
        "phase56_runtime_active_duration_mean": (
            float(np.mean(phase56_runtime_active_durations)) if phase56_runtime_active_durations else None
        ),
        "phase56_runtime_active_duration_max": (
            int(max(phase56_runtime_active_durations)) if phase56_runtime_active_durations else None
        ),
        "phase56_runtime_frozen_duration_mean": (
            float(np.mean(phase56_runtime_frozen_durations)) if phase56_runtime_frozen_durations else None
        ),
        "phase56_runtime_frozen_duration_max": (
            int(max(phase56_runtime_frozen_durations)) if phase56_runtime_frozen_durations else None
        ),
        "phase56_runtime_fallback_duration_mean": (
            float(np.mean(phase56_runtime_fallback_durations)) if phase56_runtime_fallback_durations else None
        ),
        "phase56_runtime_fallback_duration_max": (
            int(max(phase56_runtime_fallback_durations)) if phase56_runtime_fallback_durations else None
        ),
        "phase56_runtime_reset_duration_mean": (
            float(np.mean(phase56_runtime_reset_durations)) if phase56_runtime_reset_durations else None
        ),
        "phase56_runtime_reset_duration_max": (
            int(max(phase56_runtime_reset_durations)) if phase56_runtime_reset_durations else None
        ),
        "phase56_runtime_cycle_duration_mean": (
            float(np.mean(phase56_runtime_cycle_durations)) if phase56_runtime_cycle_durations else None
        ),
        "phase56_runtime_cycle_duration_max": (
            int(max(phase56_runtime_cycle_durations)) if phase56_runtime_cycle_durations else None
        ),
        "phase56_runtime_reset_to_rearm_latency_mean": (
            float(np.mean(phase56_runtime_reset_to_rearm_latencies))
            if phase56_runtime_reset_to_rearm_latencies
            else None
        ),
        "phase56_runtime_reset_to_rearm_latency_max": (
            int(max(phase56_runtime_reset_to_rearm_latencies))
            if phase56_runtime_reset_to_rearm_latencies
            else None
        ),
        "fm_path_curvature_runtime_mean": (
            float(pd.to_numeric(csv_df.get("fm_path_curvature_runtime"), errors="coerce").mean())
            if "fm_path_curvature_runtime" in csv_df.columns
            else None
        ),
        "fm_path_curvature_runtime_p95": (
            float(pd.to_numeric(csv_df.get("fm_path_curvature_runtime"), errors="coerce").quantile(0.95))
            if "fm_path_curvature_runtime" in csv_df.columns
            else None
        ),
        "fm_path_curvature_runtime_max": (
            float(pd.to_numeric(csv_df.get("fm_path_curvature_runtime"), errors="coerce").max())
            if "fm_path_curvature_runtime" in csv_df.columns
            else None
        ),
        "state_only_marginal_error_runtime_mean": (
            float(pd.to_numeric(csv_df.get("state_only_marginal_error_runtime"), errors="coerce").mean())
            if "state_only_marginal_error_runtime" in csv_df.columns
            else None
        ),
        "state_only_marginal_error_runtime_p95": (
            float(pd.to_numeric(csv_df.get("state_only_marginal_error_runtime"), errors="coerce").quantile(0.95))
            if "state_only_marginal_error_runtime" in csv_df.columns
            else None
        ),
        "state_only_marginal_error_runtime_max": (
            float(pd.to_numeric(csv_df.get("state_only_marginal_error_runtime"), errors="coerce").max())
            if "state_only_marginal_error_runtime" in csv_df.columns
            else None
        ),
        "metric_contract_version": DEPTH_BARRIER_CONTRACT_VERSION,
        "depth_reference_frame": str(args_cli.depth_reference_frame),
        "depth_surface_z": float(args_cli.depth_surface_z),
        "depth_upper_limit": float(depth_limits["depth_upper_limit"]),
        "depth_upper_safe": float(depth_limits["depth_upper_safe"]),
        "depth_lower_safe": float(depth_limits["depth_lower_safe"]),
        "depth_lower_limit": float(depth_limits["depth_lower_limit"]),
        "depth_tube_width": float(depth_limits["depth_tube_width"]),
        "depth_transition_width": float(depth_limits["depth_transition_width"]),
        "env_eval_mode": bool(getattr(raw_env.unwrapped.cfg, "eval_mode", False)),
        "goal_spawn_radius": float(getattr(raw_env.unwrapped.cfg, "goal_spawn_radius", float("nan"))),
        "init_guidance_rate": float(getattr(raw_env.unwrapped.cfg, "init_guidance_rate", float("nan"))),
        "starting_depth_raw": float(getattr(raw_env.unwrapped.cfg, "starting_depth", float("nan"))),
        "max_auv_z": float(getattr(raw_env.unwrapped.cfg, "max_auv_z", float("nan"))),
        "reset_random_spawn_enabled": bool(
            (not bool(getattr(raw_env.unwrapped.cfg, "eval_mode", False)))
            and float(getattr(raw_env.unwrapped.cfg, "goal_spawn_radius", 0.0)) > 0.0
        ),
        "first_true_z": first_true_z,
        "first_true_depth_v1": first_true_depth_v1,
        "first_des_depth_v1": first_des_depth_v1,
        "first_depth_raw_offset_from_starting": first_depth_raw_offset_from_starting,
        "first_depth_lower_margin": first_depth_lower_margin,
        "first_depth_upper_margin": first_depth_upper_margin,
        "first_depth_in_hard_tube": first_depth_in_hard_tube,
        "first_des_depth_in_safe_core": first_des_depth_in_safe_core,
        "true_depth_v1_mean": true_depth_v1_mean,
        "true_depth_v1_min": true_depth_v1_min,
        "true_depth_v1_max": true_depth_v1_max,
        "des_depth_v1_mean": des_depth_v1_mean,
        "des_depth_v1_min": des_depth_v1_min,
        "des_depth_v1_max": des_depth_v1_max,
        "legacy_final_mse": final_mse,
        "final_attitude_mse": final_attitude_mse,
        "mean_so3_attitude_error": mean_so3_attitude_error,
        "depth_violation_integral": v1_depth_barrier_summary.get("depth_violation_integral"),
        "depth_violation_time_fraction": v1_depth_barrier_summary.get("depth_violation_time_fraction"),
        "depth_upper_transition_integral": v1_depth_barrier_summary.get("depth_upper_transition_integral"),
        "depth_lower_transition_integral": v1_depth_barrier_summary.get("depth_lower_transition_integral"),
        "depth_barrier_penalty_mean": v1_depth_barrier_summary.get("depth_barrier_penalty_mean"),
        "depth_barrier_penalty_max": v1_depth_barrier_summary.get("depth_barrier_penalty_max"),
        "depth_barrier_penalty_integral": v1_depth_barrier_summary.get("depth_barrier_penalty_integral"),
        "actuator_saturation_time_fraction": v1_saturation_summary.get("actuator_saturation_time_fraction"),
        "actuator_saturation_p95": v1_saturation_summary.get("actuator_saturation_p95"),
        "actuator_saturation_mean": v1_saturation_summary.get("actuator_saturation_mean"),
        "actuator_saturation_max": v1_saturation_summary.get("actuator_saturation_max"),
        "attitude_control_authority_ratio": v1_saturation_summary.get("attitude_control_authority_ratio"),
        "target_drift_final": float(stdw_wrapper.target_drift),
        "total_steps": int(args_cli.total_steps),
        "final_mse": final_mse,
        "convergence_step": convergence_step,
        "stability_threshold_abs": float(args_cli.stability_threshold),
        "stability_threshold_rel": float(args_cli.stability_threshold_rel),
        "stability_threshold_effective": float(effective_stability_threshold),
        "baseline_compound_error_mean": baseline_err_mean,
        "slow_loop_triggers": int(slow_loop_triggers),
        "enable_trigger_gate": bool(args_cli.enable_trigger_gate),
        "trigger_threshold": float(args_cli.trigger_threshold),
        "gate_silenced_count": int(gate_silenced_count),
        "reset_count": int(reset_count),
        "nonfinite_guard_count": int(nonfinite_guard_count),
        "first_nonfinite_step": first_nonfinite_step,
        "plot_paths": {name: str(path) for name, path in diagnostic_plot_paths.items()},
        # Scenario / embodiment / fault metadata for sweep aggregation.
        "scenario": args_cli.scenario or "manual",
        "embodiment": args_cli.embodiment,
        "noise_std": float(args_cli.noise_std),
        "ang_vel_extra_std": float(getattr(args_cli, "ang_vel_extra_std", 0.0)),
        "fault_rate_per_second": args_cli.fault_rate_per_second,
        "fault_thrusters": args_cli.fault_thrusters,
        "final_mse_after_drift": final_mse_after_drift,
        "save_stdw_ckpt": bool(args_cli.save_stdw_ckpt),
        "stdw_ckpt_interval": int(args_cli.stdw_ckpt_interval),
        "stdw_ckpt_keep_last": int(args_cli.stdw_ckpt_keep_last),
        "export_deploy_jit": bool(args_cli.export_deploy_jit),
        "stdw_ckpt_dir": str(ckpt_dir),
        "saved_stdw_ckpts": saved_ckpts,
        **tracking_mse_summary,
    }
    summary.update(
        _phase56_curvature_relative_summary(
            csv_df,
            enabled=bool(args_cli.phase56_curvature_relative_logging),
            baseline_source=str(args_cli.phase56_curvature_baseline_source),
            baseline_window_label=str(args_cli.phase56_curvature_baseline_window_label),
            baseline_p95=float(args_cli.phase56_curvature_baseline_p95),
            baseline_p99=float(args_cli.phase56_curvature_baseline_p99),
            scope_caveat="observed_direct replay evidence only; not full selected-chain coverage",
            nonbinding_state_counts=phase56_curvature_nonbinding_state_counts,
        )
    )
    summary_path = stdw_run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    try:
        buffer.save(stdw_run_dir / "buffer.pt")
    except Exception as exc:
        print(f"[WARN] buffer.save failed: {exc}")

    # Mirror plots into artifact_dir for review.
    for name, plot_path in diagnostic_plot_paths.items():
        try:
            shutil.copy2(plot_path, artifact_dir / f"stdw_{name}_{timestamp}.png")
        except Exception:
            pass
    try:
        shutil.copy2(summary_path, artifact_dir / f"summary_{timestamp}.json")
    except Exception:
        pass
    # Mirror raw tracking CSV into artifact_dir so every sweep cell keeps the
    # original target/actual angles + compound error for later re-processing.
    try:
        shutil.copy2(csv_path, artifact_dir / f"stdw_output_{timestamp}.csv")
    except Exception:
        pass

    env.close()


if __name__ == "__main__":
    import traceback as _tb
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        print(f"## EVALUATION LOG ## FATAL exception in main(): {type(exc).__name__}: {exc}")
        _tb.print_exc()
        raise
    finally:
        try:
            simulation_app.close()
        except Exception:
            pass
