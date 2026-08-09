# Project State: EASYkoopman

**Updated:** 2026-08-09
**Current focus:** Phase 5.5 interface semantics and fallback diagnosis

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
| 2026-07-03 | Koopman-MPC 需要自己的 PPO checkpoint | 旧 PPO checkpoint 是 legacy controller 下的策略，低层控制器变更后 MDP 已经变化 |
| 2026-07-03 | 不手写 PPO 算法，复用 RSL-RL PPO | 需要改变训练闭环和证据记录，不需要重写成熟 PPO 实现 |
| 2026-07-03 | Phase 5 改为 Koopman-MPC PPO retraining，LLM 后移 | 先训练新控制链路下的 PPO，再让 LLM 做低频规划或调参 |
| 2026-07-04 | Phase 5 adapter 必须位于 RSL-RL `env.step(action_4d)` 路径 | `OnPolicyRunner.learn()` 拥有 rollout loop，外层脚本调用 adapter 不能证明训练闭环成立 |
| 2026-07-04 | Phase 5 增加 checkpoint provenance gate | 防止 Phase 4.6 legacy checkpoint 被误标为 `retrained_ppo_koopman_mpc` |
| 2026-07-04 | Phase 5 限定为短训闭环 smoke | reward redesign、长训练、超参搜索和性能排名后移到 Phase 5.x |

## Blockers And Risks

- 本地仍不能运行 Isaac；所有 Isaac rollout 继续在服务器 `/root/IsaacLab` 执行。
- 目前只有 step long log 的一次结果；还缺 sine 和 irregular 长日志。
- 服务器 Git clone/pull 可能继续遇到 TLS 超时；必要时使用 zip 或 git bundle 传输。
- 如果只用训练集误差选模型，MPC 闭环可能因为模型泛化失败而不稳定。
- 如果 selected model 没有优于 persistence/simple linear baseline，Phase 3 不应使用它。
- 如果 held-out rollout 出现 NaN/Inf、物理 envelope 越界或 multi-step divergence，Phase 3 不应开始。
- Phase 2.5 必须保持 Isaac-free，除非发现日志采集脚本本身阻塞数据生成。

## Next Action

执行 Phase 5.5 新主线：

1. 冻结 Phase 5.4 的 `NO_SELECTION` 结论和代表性 PPO checkpoints。
2. 增加 adapter reference-delta 与 MPC cost-improvement 诊断字段。
3. 在固定 checkpoint 下执行 bounded adapter-scale sweep，避免训练随机性污染归因。
4. 区分 `timeout`、`no_cost_improvement`、prediction mismatch 和 actuator-bound fallback。
5. 根据证据决定保留 `heuristic_reference_delta_v0`，还是进入 Phase 5.6 `native_reference_delta_v1`。
6. LLM 后置为 Phase 9 可选 supervisor，不进入实时控制。

## 2026-08-09 Phase 5.4 Closeout And Roadmap Realignment

Verified completed work:

- Phase 5.4 ran 11/11 sentinels and 11/11 candidates on `agentic-AUV`.
- Every candidate completed matched step/sine/irregular evaluation.
- Final result was `selection_status=no_selection`; no reward/MPC-only profile passed the promotion gates.
- Mean/max latency stayed inside the declared gates for the formal candidates, so latency is not the primary current bottleneck.
- The strongest remaining hypotheses are PPO-to-reference semantics and `no_cost_improvement` fallback behavior.

Frozen decisions:

- Do not continue broad reward/MPC micro-tuning without new diagnostic evidence.
- Phase 5.5 diagnoses the current adapter and fallback contract before Phase 5.6 changes action semantics.
- Cross-platform evaluation precedes online Koopman adaptation.
- LLM is a post-core, low-frequency supervisor and cannot command PPO actions or PWM.

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

Historical Phase 2.5 next action (completed):

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

## 2026-07-03 Phase 4.5 Planning Note

Phase 4.5 planning is now created in:

- `.planning/phases/04.5-ppo-rl-reference-adapter-integration/04.5-SPEC.md`
- `.planning/phases/04.5-ppo-rl-reference-adapter-integration/04.5-PLAN.md`

Locked Phase 4.5 decisions:

1. PPO currently consumes 9D observation and emits 4D action/correction.
2. Koopman+MPC consumes 11D state plus 5D reference and emits 8D PWM.
3. A PPO-to-Koopman adapter is required; directly switching `play_eval.py` to `controller_mode=koopman_mpc` is not a valid integration.
4. The first adapter mode is exactly `heuristic_reference_delta_v0`: it treats PPO's legacy 4D action as a bounded reference delta under an explicit heuristic assumption.
5. `direct_state` Koopman+MPC is the default low-level backend for Phase 4.5.
6. `paper_lifted_edmd` remains research-only until the Phase 4 depth mismatch is diagnosed.
7. The first server gate is `stub policy -> adapter -> direct_state Koopman+MPC -> 8D PWM`; checkpoint inference is attempted only if a PPO checkpoint exists.
8. Checkpoint inference is only a guarded smoke unless logs include `ppo_evidence_level`, `action_semantics`, `adapter_quat_convention`, `base_reference_goal_match_max_error` and controller-swap distribution-shift notes.

Current next action:

```text
Execute Phase 4.5 Wave 1:
  implement heuristic_reference_delta_v0 with action-semantics diagnostics,
  verify base-reference/goal matching and per-step Koopman reference refresh,
  then add the stub-policy PPO+Koopman workflow before touching real checkpoints.
```

## 2026-07-03 Phase 4.5 Local Implementation Note

Phase 4.5 local implementation is now written on `isaaclab2-migration`.

Implemented:

- `heuristic_reference_delta_v0` policy adapter;
- PPO/Koopman JSONL validator;
- PPO checkpoint discovery CLI;
- guarded `play_ppo_koopman.py` workflow;
- source-contract tests for AppLauncher order, adapter mode, evidence levels, per-step reference refresh and direct-state manifest gate.

Verified locally:

```text
Phase 4.5 tests: 21 passed
Full pytest: 91 passed
compileall: passed
git diff --check: passed
```

Current next action:

```text
Package/upload this branch to the Isaac server, then run the stub-only smoke:
  workflows/play_ppo_koopman.py --policy_mode stub --controller_mode koopman_mpc

Only after that succeeds:
  run discover_ppo_checkpoints.py --json,
  then attempt checkpoint_smoke if a PPO checkpoint exists.
```

## 2026-07-03 Phase 4.5 Server Verification Note

Phase 4.5 has now been validated on `agentic-AUV` with code synced from local commit `97025ed`.

Additional local fix before final sync:

```text
fix(04.5): preflight checkpoint mode before Isaac startup
```

Reason:

```text
When no checkpoint existed, the old checkpoint mode started Isaac before discovering the missing checkpoint.
The fixed workflow now exits before AppLauncher creates the Isaac app.
```

Verified after fix:

```text
server pytest: 92 passed
server compileall: passed
stub_only Isaac smoke: completed
PPO/Koopman validator: OK, 350 samples
checkpoint discovery: checkpoint_found=false, count=0
missing checkpoint preflight: exit code 2 in 0 seconds, clear message
```

Stub smoke artifact:

```text
/root/EASYkoopman/source/results/koopman_phase4_5/stub_step_97025ed.jsonl
```

Stub smoke metrics:

```text
adapter_mode: heuristic_reference_delta_v0
ppo_evidence_level: stub_only
backend_used: direct_state
pwm_min: -1.0
pwm_max: 1.0
policy_action_clip_rate_max: 0.0
base_reference_goal_match_max_error_max: 0.0
fallback_rate: 0.28
latency_ms_mean: 11.87197584392769
latency_ms_max: 12.386091984808445
```

Current boundary:

```text
Phase 4.5 proves the adapter/control chain can run in Isaac with stub policy.
It does not prove PPO performance because no PPO checkpoint exists on the server.
Fallback and latency remain known direct_state Koopman+MPC limitations for the next optimization phase.
```

## 2026-07-03 Phase 4.6 Planning Note

Phase 4.6 planning is now created in:

- `.planning/phases/04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate/04.6-SPEC.md`
- `.planning/phases/04.6-ppo-training-entrypoint-and-checkpoint-evidence-gate/04.6-PLAN.md`
- `docs/phase4_6_ppo_training_checkpoint_gate.md`

Locked Phase 4.6 decisions:

1. Phase 4.6 is a PPO training/checkpoint evidence gate, not a PPO performance phase.
2. PPO observation remains 9D and PPO action remains 4D.
3. `--max_iterations 1` is only a training entrypoint smoke because current `save_interval=50` may not write a checkpoint.
4. Checkpoint generation must use `save_interval=1`, explicit final save or enough iterations to trigger saving.
5. `legacy_ppo_baseline` is a `result_bucket`, not a `ppo_evidence_level`; current evidence levels remain `stub_only`, `checkpoint_smoke`, `training_entrypoint_only` and `retrained_policy_smoke`.
6. Old checkpoints routed through Koopman+MPC are labeled `old_checkpoint_adapter_smoke`, not semantically migrated policies.
7. A true Koopman-MPC retraining claim requires `policy_output_4d -> heuristic_reference_delta_v0 -> _koopman_reference_5d refresh -> env.step(policy_output_4d)` inside training; this is Phase 5's main implementation target.
8. Reward defaults to `reward_profile=legacy_easyuuv_v0`; reward changes are out of Phase 4.6 unless versioned separately.
9. Checkpoint discovery must output `selected_checkpoint` and `selected_rule`.
10. Legacy PPO baseline requires a summary sidecar if the legacy JSONL does not contain all evidence fields.
11. Results must be separated into `legacy_ppo_baseline`, `old_checkpoint_adapter_smoke` and the Phase 5 target bucket `retrained_ppo_koopman_mpc`.
12. No Phase 4.6 summary may claim PPO convergence, superiority or completion of Koopman-MPC-specific PPO training.

Current next action:

```text
Execute Phase 4.6 Wave 1:
  migrate workflows/train.py to Isaac Lab 2.2.1 compatibility,
  run a one-env one-iteration PPO training entrypoint smoke on agentic-AUV,
  then run a separate checkpoint generation smoke with an explicit save policy.

After Phase 4.6:
  execute Phase 5 to train the Koopman-MPC-specific PPO checkpoint.
```

## 2026-07-03 Phase 5 PPO Strategy Planning Note

Phase 5 planning is now created in:

- `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`
- `.planning/phases/05-koopman-mpc-ppo-retraining/05-PLAN.md`
- `docs/phase5_koopman_mpc_ppo_training_strategy.md`

Locked Phase 5 decisions:

1. Koopman-MPC needs its own PPO checkpoint trained under the new low-level control path.
2. Same USD asset does not mean the old PPO checkpoint remains valid, because the controller-induced transition dynamics changed.
3. RSL-RL remains the PPO implementation. We are not hand-writing PPO.
4. First pass keeps EasyUUV PPO observation at 9D and action at 4D.
5. First pass keeps `reward_profile=legacy_easyuuv_v0`.
6. First pass uses `direct_state` Koopman+MPC, not `paper_lifted_edmd`.
7. The training path must refresh the 5D Koopman reference through `heuristic_reference_delta_v0` before every environment step.
8. `controller_mode=koopman_mpc` alone is not a valid PPO retraining integration.
9. Initial evidence level is `ppo_evidence_level=retrained_policy_smoke`.
10. Phase 5 may prove a retrained checkpoint can be generated and loaded, but it must not claim convergence or superiority without later long evaluation.

Phase order is now:

```text
Phase 4.6:
  restore PPO/RSL-RL checkpoint evidence

Phase 5:
  train Koopman-MPC-specific PPO

Phase 6:
  add low-frequency LLM planning/tuning
```

## 2026-07-04 Phase 4.6 Local Implementation Note

Phase 4.6 local implementation is now written on `isaaclab2-migration`.

Implemented locally:

- Isaac Lab 2 compatible `workflows/train.py`;
- `--save_interval` checkpoint smoke override;
- Phase 4.6 training summary writer;
- deterministic checkpoint discovery with `selected_checkpoint` and `selected_rule`;
- Isaac Lab 2 compatible `workflows/play_eval.py` legacy PPO baseline path;
- Phase 4.6 legacy PPO sidecar summary;
- Isaac Lab 2 compatible `workflows/gen_policy.py`;
- old-checkpoint adapter metadata in `workflows/play_ppo_koopman.py`;
- local source-contract tests in `tests/test_phase46_source_contract.py`.

Verified locally:

```text
targeted Phase 4.6 tests: passed
compileall: passed
full pytest: 100 passed
git diff --check: passed with CRLF warnings only
```

Server verification completed on `agentic-AUV`:

```text
server pytest: 102 passed
server compileall: passed
training entrypoint smoke: passed
checkpoint generation smoke: passed
checkpoint discovery: checkpoint_found=true
selected_checkpoint: /root/IsaacLab/logs/rsl_rl/easyuuv/2026-07-04_12-01-58/model_0.pt
legacy PPO baseline smoke: 2 validated samples
old-checkpoint adapter smoke: 2 validated samples
```

Server fixes made during verification:

```text
parse_env_cfg now uses the Isaac Lab 2.2 device= signature.
play_eval.py now skips policy export unless --export_policy is passed.
```

Current next action:

```text
Start Phase 5:
  train the Koopman-MPC-specific PPO checkpoint with heuristic_reference_delta_v0
  inside the training loop before env.step(action_4d).
```

## 2026-07-04 Phase 5 Detailed Planning Update

Phase 5 detailed planning has been tightened after a control/RL review.

Updated artifacts:

- `.planning/phases/05-koopman-mpc-ppo-retraining/05-SPEC.md`
- `.planning/phases/05-koopman-mpc-ppo-retraining/05-PLAN.md`
- `docs/phase5_koopman_mpc_ppo_training_strategy.md`
- `.planning/ROADMAP.md`

Hard gates added:

1. Adapter refresh must be on the RSL-RL rollout `env.step(action_4d)` path. A wrapper or env hook is acceptable; a script-level call outside `OnPolicyRunner.learn()` is not.
2. `retrained_policy_smoke` requires checkpoint provenance. The checkpoint must come from a Phase 5 training summary with `result_bucket=retrained_ppo_koopman_mpc`, `controller_path=koopman_mpc/direct_state`, `adapter_mode=heuristic_reference_delta_v0` and `checkpoint_provenance=phase5_train_koopman_mpc`.
3. Phase 5 is smoke-only. The first reward remains `legacy_easyuuv_v0`; long training, reward redesign, hyperparameter search and performance ranking move to Phase 5.x.

Implementation direction:

```text
gym.make(...)
  -> Phase5KoopmanReferenceWrapper.step(action_4d)
       -> adapt_policy_reference(...)
       -> refresh _koopman_reference_5d
       -> underlying env.step(action_4d)
  -> RslRlVecEnvWrapper(...)
  -> OnPolicyRunner.learn(...)
```

Fallback direction if the Gym wrapper breaks Isaac Lab expectations:

```text
EasyUUVEnv._pre_physics_step(...)
  -> explicit Phase 5 adapter hook
  -> refresh _koopman_reference_5d
  -> existing Koopman-MPC controller path
```

Current next action:

```text
Implement Phase 5 Wave 1:
  add adapter-in-training-loop source contract tests,
  then implement the smallest RSL-RL-compatible wrapper or env hook.
```

## 2026-07-04 Phase 5 Local Repair Note

Phase 5 review must-fixes have been repaired locally.

Implemented:

- `Phase5KoopmanReferenceWrapper` in `koopman/ppo_training_adapter.py`.
- Phase 5 training entrypoint in `workflows/train_ppo_koopman.py`.
- Phase 5 checkpoint provenance validator in `workflows/validate_phase5_checkpoint_provenance.py`.
- `play_ppo_koopman.py` provenance preflight for `retrained_policy_smoke`.
- `validate_ppo_koopman_log.py` provenance requirements for retrained-policy logs.
- Phase 5 source-contract and provenance tests.

Local verification:

```text
python -m pytest -q -> 110 passed
python -m compileall __init__.py easyuuv_env.py koopman workflows tests -> passed
git diff --check -> passed with CRLF warnings only
```

Current next action:

```text
Upload/sync to agentic-AUV and run Phase 5 server smoke:
  train_ppo_koopman.py with --num_envs 1,
  validate_phase5_checkpoint_provenance.py,
  play_ppo_koopman.py with --ppo_evidence_level retrained_policy_smoke.
```

## 2026-07-04 Phase 5 Server Completion Note

Phase 5 has passed the server smoke gate on `agentic-AUV`.

Server artifacts:

- `/root/EASYkoopman/source/results/koopman_phase5/training_smoke_summary.json`
- `/root/EASYkoopman/source/results/koopman_phase5/retrained_ppo_koopman_step.jsonl`
- `/root/EASYkoopman/source/results/koopman_phase5/server_smoke_summary.json`
- `/root/IsaacLab/logs/rsl_rl/easyuuv_koopman_mpc/2026-07-04_23-23-45/model_0.pt`

Local copies:

- `source/results/koopman_phase5/training_smoke_summary.json`
- `source/results/koopman_phase5/retrained_ppo_koopman_step.jsonl`
- `source/results/koopman_phase5/server_smoke_summary.json`

Verification:

```text
server pytest: 110 passed
server compileall: passed
training smoke: passed
checkpoint provenance validator: passed
retrained checkpoint eval smoke: passed
PPO/Koopman log validator: OK, 2 samples
```

Key metrics:

```text
adapter_refresh_count: 24
adapter_refresh_before_env_step: true
checkpoint_provenance_valid: true
fallback_rate: 0.0
latency_ms_mean: 11.496730614453554
latency_ms_max: 11.539035476744175
pwm_bounds: [0.6499999761581421, 1.0]
policy_action_clip_rate_max during eval: 0.0
```

Current boundary:

```text
Phase 5 proves early retrained-policy smoke evidence only.
It does not prove PPO convergence, performance superiority, deployability or final reward design.
```

Historical next action at Phase 5 closeout (superseded by the 2026-08-09 state at the top of this file):

```text
Open Phase 5.x for stable training and bounded reward/controller diagnosis.
The alternative of moving directly to LLM was not selected.
```

## 2026-07-04 Phase 5.1 Stable-Training Planning Note

The user selected the stable-training-first path:

```text
First prove stable PPO training under Koopman-MPC.
After stability is proven, inspect and improve each bottleneck separately.
```

Created planning artifacts:

- `.planning/phases/05.1-koopman-mpc-ppo-stability-training/05.1-CONTEXT.md`
- `.planning/phases/05.1-koopman-mpc-ppo-stability-training/05.1-SPEC.md`
- `.planning/phases/05.1-koopman-mpc-ppo-stability-training/05.1-PLAN.md`
- `docs/phase5_1_koopman_mpc_ppo_stability_training.md`

Locked Phase 5.1 decisions:

1. Phase 5.1 is a stability gate, not a performance-ranking phase.
2. The first stability proof keeps RSL-RL PPO, 9D observation, 4D action, `heuristic_reference_delta_v0` and `direct_state` Koopman+MPC.
3. The first stability proof keeps `reward_profile=legacy_easyuuv_v0`; reward redesign starts only after stable training evidence exists.
4. The server ladder is `50-iteration sentinel -> 200-iteration stability candidate -> matched step/sine/irregular evaluation`.
5. Stability summaries must record checkpoint provenance, non-finite counts, action clipping, fallback rate, solver latency and PWM bounds.
6. Warning thresholds route follow-up work; they do not automatically prove failure.
7. LLM remains deferred after PPO stability and bounded control evidence. The canonical roadmap now places it at optional Phase 9, after interface diagnosis, cross-platform evaluation, online adaptation and core matched experiments.

Current next action:

```text
Implement Phase 5.1 local stability summary and validator,
then run the server sentinel and stability candidate on agentic-AUV.
```

## 2026-07-05 Phase 5.1 Gap Review Incorporation Note

The gap review in `docs/phase5_1_stability_plan_gap_review_for_agents.md` was incorporated into Phase 5.1 documentation.

Review conclusion:

```text
PASS_WITH_MUST_FIXES_BEFORE_EXECUTION
```

The plan direction remains correct, but server execution is blocked until the following code contracts exist:

1. `stability_sentinel`, `stability_candidate` and `matched_stability_eval` are accepted by evidence-level validation and CLI choices.
2. Phase 5.1 provenance labels exist: `phase5_1_stability_sentinel` and `phase5_1_stability_candidate`.
3. Phase 5 smoke checkpoints cannot be relabeled as Phase 5.1 stability checkpoints.
4. Training-health summaries separate training-loop metrics from matched-evaluation metrics.
5. Stability validation hard-fails missing checkpoints, NaN/Inf, PWM bounds violations and missing adapter refresh.
6. A selected checkpoint manifest is written to `source/results/koopman_phase5_1/selected_ppo_checkpoint_manifest.json`.
7. `matched_stability_eval` requires a validated Phase 5.1 stability-candidate checkpoint before Isaac startup.

Current next action:

```text
Implement the Phase 5.1 P0 documentation-defined code gates locally before any server sentinel run.
```

## 2026-07-05 Phase 5.1 Server Completion And Phase 5.2 Planning Note

Phase 5.1 has now passed the stability-candidate evidence gate on `agentic-AUV`.

Server and local evidence:

- sentinel training completed with `checkpoint_provenance=phase5_1_stability_sentinel`;
- 200-iteration stability candidate completed with `checkpoint_provenance=phase5_1_stability_candidate`;
- selected checkpoint: `/root/IsaacLab/logs/rsl_rl/easyuuv_koopman_mpc/2026-07-05_00-28-00/model_199.pt`;
- matched step, sine and irregular evaluation logs validated;
- selected manifest: `source/results/koopman_phase5_1/selected_ppo_checkpoint_manifest.json`;
- matched summary: `source/results/koopman_phase5_1/matched_eval_summary.json`.

Phase 5.1 result boundary:

```text
We have stable-training candidate evidence.
We do not yet have PPO convergence, deployability or broad superiority evidence.
```

Observed bottlenecks:

```text
PWM saturation:
  step=0.2757, sine=0.4664, irregular=0.3746

fallback:
  step=0.1343, sine=0.0314, irregular=0.0971

action clipping:
  sine has the highest mean clip rate at 0.2364
```

Phase 5.2 planning artifacts were drafted for review:

- `.planning/phases/05.2-reward-adapter-mpc-health-optimization/05.2-SPEC.md`
- `.planning/phases/05.2-reward-adapter-mpc-health-optimization/05.2-PLAN.md`
- `docs/phase5_2_reward_adapter_mpc_health_optimization.md`

Locked direction for review:

```text
Do one-factor health optimization before longer training:
  baseline re-run
  reward_v1_only
  adapter_soft_v1_only
  mpc_health_v1_only

Do not combine reward, adapter and MPC changes until single-axis results are reviewed.
```

Current next action:

```text
User reviews Phase 5.2 reward weights, adapter scales, MPC health profile,
promotion threshold and whether combined profile is allowed in Phase 5.2.
After approval, implement Phase 5.2 local code and then run server ablation.
```

## 2026-07-05 Phase 5.2 Review Incorporation Note

The review in `docs/phase5_2_reward_adapter_mpc_health_optimization_review.md` has been incorporated into the Phase 5.2 SPEC/PLAN.

Updated decisions:

```text
baseline_rerun:
  mandatory

reward_v1_only:
  w_fallback = 0.30
  w_pwm_sat = 0.20
  latency penalty thresholded above latency_ref_ms

adapter_soft_v1_only:
  rpy_delta_scale = 0.30
  depth_delta_scale = 0.40

adapter_scale_soft_v2:
  rpy_delta_scale = 0.25
  depth_delta_scale = 0.30
  reserved as stronger backup, not initial matrix

mpc_health_v1_only:
  mpc_delta_pwm_limit = 0.35
  mpc_control_weight = 0.03
  mpc_smoothness_weight = 0.10

mpc_delta_limit_probe_v1:
  mpc_delta_pwm_limit = 0.25
  optional probe after weights-only MPC review

combined profile:
  deferred to Phase 5.2b or Phase 5.3
```

Candidate promotion now requires:

```text
20 percent relative improvement
plus minimum absolute improvement
plus fallback/depth/attitude regression guards
plus complete matched step/sine/irregular evaluation
```

Current next action:

```text
Implement Phase 5.2 local code according to the review-incorporated SPEC/PLAN,
then sync to agentic-AUV for baseline_rerun and one-factor ablation.
```
