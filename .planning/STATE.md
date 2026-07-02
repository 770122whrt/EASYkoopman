# Project State: EASYkoopman

**Updated:** 2026-07-02
**Current focus:** Phase 4.5 - PPO/RL Reference Adapter Integration

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** 在不破坏 EasyUUV 原始仿真基线的前提下，建立一个可验证、可迭代的 Koopman+MPC 控制闭环。

## Current Understanding

- 当前 EasyUUV 目录是项目工作根目录。
- 远程目标仓库是 `https://github.com/770122whrt/EASYkoopman.git`。
- 服务器实际环境已经确认：Isaac Sim 5.0 + Isaac Lab 2.2.1。
- Phase 1 已经建立 legacy controller boundary、pre-thrust 8D PWM cache 和 Koopman JSONL logging helper。
- Phase 1.5 已经让 direct-controller smoke rollout 在服务器上跑通，并生成可验证 JSONL。
- Phase 2 离线代码已经完成：dataset、lifting、EDMD、model artifact、evaluation 和 CLI。
- 用户已经用 1400 samples 的 step log 完成一次训练和评估，结果证明链路可用，但仍是同分布/同日志评估。
- 进入 MPC 前需要 Phase 2.5：用 log-level train/validation/test split、多轨迹日志、candidate sweep、baseline comparison 和 rollout divergence 检查来筛选可信模型。
- `docs/phase2_5_koopman_model_gate_recommendations.md` 明确指出当前 direct-state predictor 只是工程 baseline，Phase 2.5 必须新增 paper-style lifted-space EDMD 候选以贴近 Koopman-Sim2Real。
- EasyUUV USD assets 已纳入 Git，以避免服务器代码和模型资产不同步。

## Decisions

| Date | Decision | Reason |
|---|---|---|
| 2026-06-10 | 所有 GSD 文件写入 `EasyUUV/.planning` | 用户要求不要写到根目录 |
| 2026-06-10 | 第一版保留 Isaac Lab 环境 | README 和代码已经使用 Isaac Lab，重写仿真框架会扩大风险 |
| 2026-06-10 | Phase 1 优先做 controller boundary 和 data collection | Koopman+MPC 需要可验证数据和 legacy baseline |
| 2026-06-10 | GitHub 发布目标为 `770122whrt/EASYkoopman` | 用户指定仓库，当前工作在 `isaaclab2-migration` 分支 |
| 2026-06-30 | 插入 Phase 1.5 做 Isaac Lab 2.x 兼容迁移 | 服务器实际环境是 Isaac Sim 5.0 + Isaac Lab 2.2.1 |
| 2026-06-30 | Phase 1.5 server smoke gate 通过 | `validate_koopman_log.py` 接受服务器生成的 JSONL |
| 2026-06-30 | USD assets 可纳入 Git | 两个 USD 文件低于 GitHub 单文件限制，且服务器必须拥有这些资产 |
| 2026-06-30 | Phase 2 以离线 EDMD 为核心 | 先做可保存、可评估的 Koopman model，再进入模型质量 gate |
| 2026-06-30 | 插入 Phase 2.5 做 Koopman prediction quality gate | 防止在模型只拟合训练数据时过早接 MPC |
| 2026-07-01 | Phase 2.5 升级为 Offline Koopman Model Qualification Gate | recommendations 文档要求 paper-style lifted EDMD、baseline comparison、normalization、gate report 和 held-out test |
| 2026-06-30 | 多环境数据不是第一优先级 | 当前 logger 主要记录单 env；先用多轨迹、多次运行和不同初始条件覆盖数据多样性 |

## Blockers And Risks

- 本地仍不能运行 Isaac；所有 Isaac rollout 继续在服务器 `/root/IsaacLab` 执行。
- 目前只有 step long log 的一次结果；还缺 sine 和 irregular 长日志。
- 服务器 Git clone/pull 可能继续遇到 TLS 超时；必要时使用 zip 或 git bundle 传输。
- 如果只用训练集误差选模型，MPC 闭环可能因为模型泛化失败而不稳定。
- 如果 selected model 没有优于 persistence/simple linear baseline，Phase 3 不应使用它。
- 如果 held-out rollout 出现 NaN/Inf、物理 envelope 越界或 multi-step divergence，Phase 3 不应开始。
- Phase 2.5 必须保持 Isaac-free，除非发现日志采集脚本本身阻塞数据生成。

## Next Action

执行 Phase 2.5:

1. 增加 log-level train/validation/test split manifest，禁止 row-level split。
2. 新增 paper-style lifted-space EDMD candidate，同时保留 direct-state predictor baseline。
3. 增加 persistence 和 simple linear baselines。
4. 增加 normalization-aware ridge/lifting candidate sweep。
5. 增加 multi-horizon held-out evaluation 和 rollout divergence 指标。
6. 增加 selected model manifest 和 gate report，作为 Phase 3 MPC 的输入 gate。
7. 在服务器采集并验证 step、sine、irregular 长日志。

## 2026-07-01 Phase 2.5 Local Implementation Note

Phase 2.5 local code is now implemented on `isaaclab2-migration`.

Implemented:

- log-level split manifest and data-insufficient validation;
- paper-style lifted-space EDMD candidate;
- direct-state candidate retained as engineering baseline;
- persistence and simple linear baselines;
- optional standard normalization artifacts;
- multi-horizon validation metrics and divergence flags;
- candidate sweep output;
- selected model manifest generation;
- gate report generation;
- server runbook at `docs/phase2_5_koopman_gate_runbook.md`.

Current next action:

1. Package/upload this branch to the Isaac server.
2. Collect or provide validated `step`, `sine` and `irregular` long JSONL logs.
3. Run `split_koopman_logs.py`, `sweep_koopman_models.py`, `select_koopman_model.py` and `write_koopman_gate_report.py`.
4. Enter Phase 3 only if `selected_model_manifest.json` reports `gate_status = pass`.

## 2026-07-01 Phase 2.5 Server Gate And Phase 3 Planning Note

Phase 2.5 has now been re-run on the `agentic-AUV` server with validated step, sine and irregular long logs.

Verified server artifacts copied back locally:

- `source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json`
- `source/results/koopman_phase2_5_verify_20260701_231802/gate_report.md`
- `source/results/koopman_phase1/smoke_reverify_20260701_231917.jsonl`

Gate result:

```text
gate_status = pass
selected_candidate_id = direct_state_selected_quadratic_ridge_0p0001_norm_off
model_class = direct_state
control_dim = 8
dt = 0.016666666666666607
test multi_step_rmse@20 = 0.5243264020346085
```

Phase 3 planning is created in:

- `.planning/phases/03-koopman-mpc-controller-integration/03-SPEC.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-CONTEXT.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-RESEARCH.md`
- `.planning/phases/03-koopman-mpc-controller-integration/03-PLAN.md`

Current Phase 3 decision:

1. Use the selected model manifest as the runtime contract.
2. Optimize 8D PWM first, because the selected model was trained with `pwm_8d`.
3. Treat the current selected `direct_state` model as the first engineering backend, not as a full paper-style lifted EDMD controller.
4. Add a Phase 3 backend check comparing selected `direct_state` with the best passing `paper_lifted_edmd` candidate before Isaac smoke.
5. Keep the first MPC solver a pure NumPy first-pass receding-horizon optimizer, short-horizon and fallback-safe.
6. Preserve existing EasyUUV thruster and hydrodynamic logic.
7. Keep the adapter state/reference based so future PPO/RL outputs can become references instead of bypassing the controller boundary.
8. Use `workflows/play_controller.py` for the first server Isaac smoke; PPO remains deferred because no checkpoint exists on the server.

Phase 3 success statements must distinguish:

```text
engineering integration layer:
  selected direct_state backend + 8D PWM MPC + fallback-safe Isaac smoke

paper-aligned algorithm layer:
  paper_lifted_edmd backend + MPC comparison + Phase 4 experiments
```

The Phase 3 summary must report `backend_used`, `backend_reason`, `fallback_rate`, `latency_budget_met` and known limitations.

## 2026-07-02 Phase 3 Completion Note

Phase 3 is complete on `isaaclab2-migration`.

Implemented:

- manifest-first Koopman runtime loader;
- pure NumPy bounded 8D PWM MPC solver;
- fallback-safe Koopman MPC controller adapter;
- `koopman_mpc` branch in `easyuuv_env.py`;
- `play_controller.py` Koopman MPC CLI flags and diagnostic logging;
- offline backend check and offline MPC smoke workflows;
- tests covering runtime loading, MPC costs/solver, controller fallback and workflow contracts.

Verified:

```text
local pytest: 63 passed
local compileall: passed
git diff --check: passed
server pytest: 63 passed
server compileall: passed
Isaac smoke: completed one-env step rollout with koopman_mpc/Ssurface
fallback_rate: 0.0
latency_budget_met: true for both smoke samples
backend_used: direct_state
```

Current Phase 3 boundary:

```text
Completed claim:
  fallback-safe Koopman-MPC engineering integration.

Not yet claimed:
  final control superiority over legacy, long-horizon stability, or full paper-style lifted EDMD equivalence.
```

Previous next action was Phase 4:

1. Run matched legacy and Koopman MPC trajectories on the server.
2. Cover step, sine and irregular trajectories.
3. Export comparable logs.
4. Compute tracking, depth, attitude, control energy, PWM smoothness, fallback and latency metrics.
5. Decide whether `direct_state` remains primary or `paper_lifted_edmd` should be promoted for closed-loop experiments.

## 2026-07-02 Phase 3.5 Planning Note

The immediate next phase is now Phase 3.5, inserted before Phase 4.

Reason:

```text
Phase 3 proved fallback-safe Koopman-MPC integration using direct_state.
The remaining paper-aligned gap is paper-style lifted EDMD.
```

Phase 3.5 will:

- create or select a separate `paper_lifted_edmd` comparison manifest;
- preserve the existing Phase 2.5 direct-state manifest as the engineering baseline;
- evaluate direct-state and paper-lifted prediction metrics side by side;
- run offline MPC replay with identical solver settings for both backends;
- use the Isaac server for repeated paper-lifted smoke/data runs;
- hand Phase 4 either a three-way evaluation plan or a documented paper-lifted failure analysis.

Created planning artifacts:

- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-SPEC.md`
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-CONTEXT.md`
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-RESEARCH.md`
- `.planning/phases/03.5-paper-style-lifted-edmd-backend-qualification/03.5-PLAN.md`

Current next action:

```text
Implement Phase 3.5 Wave 1:
  select the best passing paper_lifted_edmd candidate,
  write paper_lifted_manifest.json,
  and verify it reloads through koopman.runtime.
```

## 2026-07-02 Phase 4 Planning Note

Phase 4 planning is now created in:

- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-SPEC.md`
- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-CONTEXT.md`
- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-RESEARCH.md`
- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-PLAN.md`

Current Phase 4 decision:

1. Keep Phase 4 as controller-only evaluation before PPO.
2. Use `workflows/play_controller.py` for matched legacy, direct-state Koopman+MPC and paper-lifted Koopman+MPC runs.
3. Use JSONL logs as the common evaluation substrate.
4. Add local Isaac-free metrics aggregation for tracking error, depth error, control effort, PWM smoothness, fallback rate and solver latency.
5. Document the server Isaac command matrix and artifact pullback procedure.
6. Hand Phase 4.5 a clean PPO/RL baseline rather than reconnecting PPO inside Phase 4.

Previous Phase 4 implementation status before server evaluation:

```text
Completed locally:
  Wave 1 metrics aggregation workflow.
  Wave 2 server runbook.
```

Previous Phase 4 next action, now completed:

```text
Run Phase 4 server Isaac matrix:
  legacy, direct_state Koopman+MPC and paper_lifted Koopman+MPC
  across step, sine and irregular trajectories,
  then pull JSONL logs back for local metrics summary.
```

## 2026-07-02 Phase 4 Completion Note

Phase 4 is complete on `isaaclab2-migration`.

Implemented and verified:

- Phase 4 controller-only metrics workflow.
- Phase 4 Isaac server runbook.
- Matched server evaluation matrix across `legacy`, `direct_state` Koopman+MPC and `paper_lifted_edmd` Koopman+MPC.
- Three trajectories: `step`, `sine` and `irregular`.
- 9/9 logs validated with 1400 samples each.
- Metrics summary generated and artifacts pulled back under `source/results/koopman_phase4/`.
- Phase 4 summary, verification and Phase 4.5 PPO handoff documents written.

Main result:

```text
legacy/Ssurface remains the strongest controller-only baseline.
direct_state Koopman+MPC is runnable with bounded PWM but still has fallback/latency issues.
paper_lifted_edmd is useful as a paper-style comparison backend, but current depth RMSE makes it unsuitable as the default Phase 4.5 low-level controller.
```

Current next action:

```text
Start Phase 4.5:
  discover whether a PPO checkpoint exists on the Isaac server,
  implement a PPO/RL reference adapter that cannot bypass Koopman+MPC,
  run stub-policy smoke first,
  then run checkpoint inference or short PPO training smoke depending on server artifacts.
```
