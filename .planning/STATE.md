---

gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-Configuration Koopman Transfer and Environment-Aware Control
status: in_progress
last_updated: "2026-09-29"
last_activity: 2026-09-29 -- user fixed two steps: disturbance then physics-Koopman combination; physical baseline frozen without disturbance-data recalibration; commit and push requested
progress:
  total_phases: 11
  completed_phases: 7
  total_plans: 36
  completed_plans: 33
  percent: 92
---

**2026-09-29当前入口：** 已确认完整提升状态自行传播、允许因果近期观测且模型参数冻结。用户已确定两步：加入扰动，再验证物理与Koopman结合。物理对照冻结、不学习新增扰动数据；本轮更新并提交推送，未启动服务器实验。下一步与Git恢复边界见[本轮交接](checkpoints/phase9-lifted-generalization-handoff-2026-09-29.md)。Phase9/09-04保持开放；以下旧日期段落保留为历史结果，不能作为新实验运行授权。

**当前入口（结果截至2026-09-27，2026-09-28补充中文解释）：** 已完成五种模型的预测比较与单构型诊断。数据校准的物理模型整体最好；限制自由度的学习残差接近物理预测；两种“非线性特征＋矩阵传播”模型尚未合格。同一基础构型换成未参与训练的扫频输入也失败，因此不能只归因于跨构型。六次连续控制优化中一次达到可接受精度、五次超时，新两秒闭环尚未运行。模型中文名称、正则参数λ、论文关系及完整数字见[统一报告与八构型表](../docs/phase9_model_comparison_v84_report.md)。本轮先解释与修正文档，没有新实验；下方旧日期内容为历史证据。

**已完成v82报告（2026-09-26，历史Goal结果）：** 已完成10条2秒真实闭环、18个非等价学习模型及八折留构型预测。uuv4两学习候选相对同MPC辨识物理的综合误差降低11.7%/9.8%；base高3.0%/17.9%，仅部分完整目标改善。已观察局部控制收益，未证明普遍模型优势或未见构型闭环泛化。10条原Linux验收通过，9条本地完整复核，uuv4学习0.001在Windows因果预演未复现、另经原运行时严格重验通过；失败保留。下一步先修求解质量和预演平台分支敏感性，再冻结新任务验证。服务器无本任务遗留进程，可关闭。 [最终报告](../docs/phase9_koopman_mpc_v82_report.md)；[执行范围](../docs/phase9_goal_v80_plan.md)。下方旧日期的运行状态仅为历史。

**当前（2026-09-26）：** 2026-09-26已完成两篇论文与控制/模型/验证三端交叉审核：主线合理；修复短计划广播验收漏洞，新增因果参考独立复核和preview开关。本地/服务器各109项通过。服务器4次真实离线求解均返回可行且通过单决策审核，base/uuv4预演开启预测成本下降57.84%/63.95%，开启臂均达迭代上限且更慢；不是闭环收益。CPU/GPU PWM差异已复现，uuv6旧实际门失败保留。零新物理/拟合；任务已退出、证据回传。先补完整新版采集/轨迹验收及数值余量，再2秒配对；之后另测非等价学习模型。 [报告](../docs/phase9_methodology_crosscheck_2026-09-26.md)。

**以下为此前阶段记录，当前执行入口以上段为准。**

**2026-09-25当前v79本地阶段：** 因果反馈预演、完整备选代价重算、模型身份分离及实际PWM余量检查已实现。36项预演可行，零新NLP/物理/拟合；旧投影与辨识物理等价。新完整提升探针不准入。uuv6实际PWM门存在小幅偏差，服务器恢复后先复核并补新验收，再做2秒控制单因素对照；学习动力学模型另行实现，不混合归因。[v79报告](../docs/phase9_control_model_separation_v79.md)。用户要求先本地，不连接关闭的服务器。

**当前v78已交付：** v78四构型统一设置2秒验证已交付。8个MPC单元中8个完整验收；投影分支1/4个构型的综合误差低于反馈，名义物理分支1/4个。模型冻结、零训练；本轮只作短任务描述性比较，Phase9保持开放。 [v78报告](../docs/phase9_common_profile_v78_report.md)。

**历史v77交付状态（2026-09-24）：** v77有界求解与控制实验已交付。r4首组四构型×两模型8例均完整验收；原repair设置仅base改善0.67%，其他三个构型仍负收益。uuv4提高深度权重并延长时域后，相对反馈改善12.15%，是短任务局部收益，不是统一跨构型或独特Koopman收益证明。模型冻结、零训练，Phase9保持开放。 [v77报告](../docs/phase9_reliable_control_v77_report.md)。

**当前范围（2026-09-24）：** 用户明确授权连续优化、离线归因与小范围匹配闭环；同一MPC换模型，另设反馈对照。控制频率性能后置，模型冻结、零训练。首组base/uuv4/long_body/uuv6，后续四构型与Agent仍条件开放；旧v73不重启、不改写。

# Project State: EASYkoopman

**Updated:** 2026-09-29
**Current focus:** 用户已确定加扰动、物理与Koopman结合两步；物理基线不重新校准，完整提升与冻结参数历史接口要求保持。具体交接见上方链接。未新增训练、求解或闭环，模型与求解缺口仍保留。
**Active milestone:** `v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control`
**Branch:** `no-selection` (verified at this planning update; recheck before execution)

**Research direction:** User confirmed Koopman-UUV / Agentic-AUV as the main objective; senior advice plus evidence-led agent judgment guide the route. Routine details are delegated. Linear/per-config/persistence remain comparators, not automatic replacement goals.

## Project Reference

See `.planning/PROJECT.md`.

**Core value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Current Position

v82旧闭环结果与v84/v85负结果保留，详见[统一报告](../docs/phase9_model_comparison_v84_report.md)。当前讨论与下一项工作以[2026-09-29交接](checkpoints/phase9-lifted-generalization-handoff-2026-09-29.md)为准，未新增2秒闭环。

## Milestone Goal

Qualify the eight supported EasyUUV 2.0 configurations, establish a topology-independent Koopman control/data contract, then evaluate cross-configuration transfer, guarded environment adaptation and a bounded Agent Supervisor.

## Inherited v1.0 Baseline

v1.0 remains frozen at tag `v1.0`, covering Phase 1 through Phase 5.4. Its accepted closeout records are:

- `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `.planning/MILESTONES.md`
- `.planning/RETROSPECTIVE.md`

Verified at v1.0 close:

```text
python -m pytest -q --basetemp .pytest-milestone-v1
175 passed

python -m compileall __init__.py easyuuv_env.py koopman workflows tests
passed
```

Server evidence accumulated during v1.0 includes:

- Isaac Sim 5.0 + Isaac Lab 2.2.1 direct-controller rollout;
- validated step/sine/irregular Koopman logs;
- Phase 2.5 direct-state model gate pass;
- Phase 3 bounded Koopman-MPC smoke;
- controller-only three-backend matched evaluation;
- Koopman-MPC-conditioned PPO checkpoint smoke;
- Phase 5.1 stable-training candidate;
- Phase 5.2 one-factor, Phase 5.3 cross-combination and Phase 5.4 Pareto experiments.

Frozen conclusions carried into v2.0:

- The single-configuration end-to-end control/retraining/evaluation chain runs.
- `direct_state` is the engineering Koopman backend for v1.0.
- `paper_lifted_edmd` is a research comparison and is not the default controller.
- Legacy/S-Surface remains the strongest nominal baseline.
- Phase 5.4 completed 11/11 sentinels and 11/11 matched candidates but selected no profile.
- Latency was not the primary Phase 5.4 bottleneck.
- Adapter/reference semantics and `no_cost_improvement` fallback are stronger hypotheses than further broad reward/MPC micro-tuning.
- No online Koopman learning or LLM runtime is present.

## Locked v2.0 Decisions

| Decision | State |
|---|---|
| Phase numbering | Continue at Phase 6; do not restore Phase 5.5/5.6. |
| New simulator source | Import `easyuuv_v2-main/` as an isolated received snapshot before integration changes. |
| Supported configurations | `base`, `long_body`, `heavy_moderate`, `asymmetric`, `uuv6`, `uuv6_angled`, `uuv4`, `uuv4_angled`. |
| Cross-configuration control | `virtual_control_4 = [roll, pitch, yaw, depth]` before TAM allocation. |
| Underactuation | `uuv4*` yaw is explicitly unavailable and excluded from feasible yaw tracking. |
| Online adaptation | RLS/KF only behind bounds, non-finite rejection, frozen prior and rollback. |
| Agent boundary | Low-frequency allow-listed supervisor; no direct PWM or real-time `env.step()` loop. |
| Evidence | Local contract tests and server Isaac evidence remain separate and level-labelled. |
| Promotion | `no_selection` is a valid outcome when no candidate passes every gate. |
| Phase 8.1 D-23 | Approved only for role `083d5eae...9417`, analysis `7a790b43...e18c` and experiment `phase8.1-main-identification-v1`; identity assurance remains none. |
| Phase 8.2 isolation | Server collection, pullback, formal LOCO and closeout live only in `source/results/koopman_phase8_2`, never in frozen Phase 8/8.1 result roots. |
| Phase 8.2 terminal | `NO_SELECTION` with `VERIFIED` closeout; fresh-root isolation and freeze semantics enforced; evidence roots immutable. |

## Git Delivery Boundaries

1. New EasyUUV 2.0 simulator snapshot.
2. v1.0 server experiment evidence plus an explicit manifest.
3. v2.0 PROJECT, REQUIREMENTS, ROADMAP, STATE, Phase 6 SPEC/PLAN and supporting design documents.

All three boundaries are visible on `origin/v2.0-multi-configuration`: simulator snapshot `7ba2499`, v1 evidence `7147379`, and planning head `c8b9c70`. Phase execution commits remain later local commits; no remote force-push was used.

## Planning Result

Historical planning setup (superseded by Current focus): [advice analysis](../docs/phase8_3_senior_advice_analysis.md), [8.3 context](phases/08.3-control-identification-forensics/08.3-CONTEXT.md) and three serial plans are ready for future execution; [8.4 context](phases/08.4-conditional-identification-experiment/08.4-CONTEXT.md) is conditional. No new evidence or scientific requirement has been marked complete. KIDO-02..05 labels were corrected from existing8.2 verification. The following bullets are a chronological historical record; older pending/absent-artifact statements describe their time of writing, not current status.

- Phase 6 SPEC ambiguity gate passed at `0.08` with QUAL-01..08 locked.
- Research and pattern mapping are complete.
- Four execution plans cover 8/8 QUAL requirements and 14/14 locked D-ID decisions.
- Wave 1 establishes package/provenance; Wave 2 runs catalog and validator TDD in parallel; Wave 3 blocks on actual eight-configuration Isaac evidence.
- Plan 06-01 completed with canonical `easyuuv_nc` packaging, package-confined USD lookup, a local `.venv` workflow and 21 passing package/v1 source-contract tests.
- Plan 06-02 completed with one exact eight-name catalog, an Isaac-free 8/6/4-thruster TAM report, explicit `uuv4*` yaw underactuation and snapshot-backed zero-drift proof.
- Plan 06-03 completed with a strict versioned artifact schema, exact-set/topology/safety/evidence gates and a deterministic CLI; independent audit added fixed-baseline, strict-mask-type and ordered-extrema gates, bringing the mutation suite to 55 passes.
- Plan 06-04 completed the deterministic Isaac runner, exact-eight merger, offline bundle/bootstrap, semantic process/log/row gates, strict provenance validator and staged pullback chain.
- The tested source commit `e24f76a` ran on the isolated server path `/root/EASYkoopman-phase6-v2`; `base` completed 64 steps and the other seven public configurations completed 8 steps each.
- The actual Isaac Sim 5.0 / Isaac Lab 2.2.1 artifact passed as `server_isaac_smoke` with 8/8 configurations, zero non-finite values, zero dimension mismatches and SHA-256 `6cb83fcb63fc7bd33ffcfa678d09f3e128fcf6f6380ee3b948541814421a1a92`.
- The 64-file server evidence package is isolated in commit `7670f66`; Phase 6 SUMMARY, SERVER-EVIDENCE and VERIFICATION provide the planning handoff.
- Phase 6 qualifies simulator/configuration behavior only. Koopman transfer, MPC integration, environment adaptation and Agent effectiveness remain Phase 7–12 work.
- Phase 7 SPEC ambiguity is `0.14`; it locks schema v2 field semantics, additive v1 isolation, actual post-actuator wrench, oracle/estimated context separation and a three-topology server completion gate.
- Phase 7 research and pattern mapping identify the exact control/dynamics capture points: explicit catalog-derived yaw mask before TAM, actual thruster wrench before environmental forces, and same-step fluid/efficiency caches.
- Four plans cover CONT-01..05 and D-01..16 with dependency graph `07-01 -> {07-02,07-03} -> 07-04`.
- Independent plan checking converged from five blocking findings to zero remaining issues. It corrected the per-episode fixture boundary, real Phase 6 script path, aggregate validator, executable full local preflight and resolved research questions.
- Phase 7 planning does not mark any CONT requirement complete and does not create or claim server evidence. Existing v1 `U=PWM_8` model/MPC defaults remain frozen.
- Plan 07-01 completed strict schema v2 transition/context validation, contiguous episode JSONL/manifest/hash and a pure-Python validator CLI through two explicit RED→GREEN cycles (`aba86e6`→`0bb631c`, `788f451`→`89491fa`).
- Independent Wave 1 rerun passed 179 tests with `.pytest-tmp/phase7-wave1-root`; the first unisolated rerun exposed only a Windows `%TEMP%` permission error before project code, which the planned repository-local basetemp resolved.
- Plan 07-02 added catalog-masked post-PID/pre-TAM virtual control, post-actuator thruster-only wrench, same-call fluid/efficiency telemetry and a one-step/one-token strict Bridge; independent serial rerun passed 208 tests and both mandatory key links.
- Plan 07-03 added immutable `U=virtual_control_4` DatasetV2 plus named diagnostics and a non-promoting v1 compatibility view; independent rerun passed 123 tests while frozen v1 model/MPC defaults remained 8D.
- Plan 07-04 added the exact-three collector/merger/validator, full local preflight, offline bundle/bootstrap and staged pullback chain; final pre-transfer gates passed 222 Phase 7 tests and 559 full-suite tests with one Windows-only symlink skip.
- Tested source `a36689a` ran on the unchanged Isaac server in isolated `/root/EASYkoopman-phase7-v2`; `base`, `uuv6` and `uuv4` each produced 8 contiguous strict schema-v2 transitions.
- All three native/tee/semantic gates passed. `uuv4` recorded two nonzero raw-yaw probes and zero virtual-yaw leaks, confirming the catalog mask before TAM in the real runtime chain.
- The aggregate passed server and pullback validators with `warnings=[]`, source/runtime provenance matched, SHA-256 `2f07a6835f0b32fe0277fd819394580f261b6028dc3d07520e70b124e0758463`, and all 44 server-authored files passed the self-excluding relative-path inventory validator on server and pullback.
- Server evidence is isolated in commit `1c0a6ca`; `07-SERVER-EVIDENCE.md`, `07-04-SUMMARY.md` and `07-VERIFICATION.md` close CONT-01..05 without claiming Koopman prediction, OOD transfer or MPC effectiveness.
- Phase 8 SPEC now distinguishes persistence/simple-linear baselines, per-configuration/pooled/conditional regimes and the non-promoting expert role; its ambiguity score is `0.10`.
- An independent contract audit corrected transductive pilot leakage: pilot is collection-health-only, while every model-affecting decision is pre-registered or fold-local over exactly seven source configurations.
- Five plans cover KID-01..05 and D-01..23 in dependency order `08-01 -> 08-02 -> 08-03 -> 08-04 -> 08-05`, with one explicit D-23 user protocol approval before main-server collection.
- Phase 8 evidence uses external `qualification_level` envelopes without extending or relabelling the frozen Phase 7 transition `evidence_level` enum.
- Evaluation and terminal selection/no-selection use separate immutable roots; a selected final refit reruns the registered inner algorithm on all eight fit+validation roles only, while refit failure atomically yields `no_selection` with no model path.
- The approved plan set initially marked no KID requirement complete and created no success artifact. Phase 8 will close only after an independent goal-backward `08-VERIFICATION.md` passes KID-01..05.
- Plan 08-01 completed the additive Phase 8 evidence/protocol layer and fail-closed local/server/pullback chain without changing the frozen Phase 7 transition evidence enum.
- Real Isaac Sim 5.0 / Isaac Lab 2.2.1 pilot evidence contains exactly eight configurations, two episodes per configuration and 128 transitions per episode: 16 episodes, 16 manifests, 16 logs and 2048 strict rows.
- The pulled envelope passed both operational-policy and external-evidence validators with `warnings=[]`; resumed closeout passed 53 Phase 8 server-contract tests and the full suite as `638 passed, 1 skipped`.
- This is collection-health evidence only. KID-01..05, model quality, LOCO OOD transfer, selection and Koopman-MPC effectiveness remain unproven.
- Plan 08-02 added a local-contract-only immutable multi-episode inventory, exactly eight seven-source LOCO fold manifests, distinct non-promoting expert views and dynamic opened-byte leakage audits.
- Physical conditioning is identity-free and fold-local: each normalizer binds the exact seven source configurations, source episode hashes and feature schema hash; no global or held-out statistics are accepted.
- Independent closeout passed 55 focused tests, 210 Phase 8/schema/pilot tests and the full repository suite as `675 passed, 1 skipped`; both declared key links and protected paths passed.
- The 8x12 main role protocol remains `pending_d23`. No real main dataset or fitted model exists, so KID-01..05 remain incomplete.
- Plan 08-03 added one additive `ControlledEDMDV2` backend, state_11/control_4 persistence and simple-linear baselines, exact identity/kinematic observable schemas and fold-fitted platform-affine Kronecker conditioning.
- Recursive evaluation is episode-local at one-step/5/20/60/full horizons; official attitude is sign-invariant normalized SO(3) geodesic radians, with per-configuration, equal-macro and worst-configuration aggregates.
- Every synthetic fold decision evaluates the frozen 108-candidate local grid from exactly seven source configurations, records every opened episode/statistic and seals before held-out test access; only pooled/conditional result types are eligible.
- Independent closeout passed 396 broad tests plus one existing skip and the final full suite as `733 passed, 1 skipped`; compileall, standalone diff-check, key links, protected paths and forbidden-root absence passed.
- Plan 08-03 is `local_contract` only. Its policy fixture is not D-23 approval, no real main/evaluation/selection root exists and KID-01..05 remain incomplete.
- Plan 08-04 froze the explicitly approved D-23 role/action and analysis-policy hashes, then ran the exact protocol from tested source `a7e8198` in isolated `/root/EASYkoopman-phase8-main-v2` on the unchanged Isaac server.
- The successful server chain completed 8/8 native, tee and semantic gates and produced exactly 96 episode JSONL, 96 manifests, 96 logs, zero `.part` files and 49,152 transitions: each configuration has six fit, three validation and three test episodes of 512 transitions.
- The post-collection inventory, exact-eight LOCO split and external envelope were built only after the exact set completed. Server and local validators returned `phase8_external_evidence_valid`, 293 referenced files and `warnings=[]`; envelope SHA-256 is `46d02531457123f2a1dfda3b16159b359a6caff2d90b14283094a349647a1b04`.
- Random-staging pullback validated all 294 canonical files, exact protocol/source/runtime hashes and all process statuses before atomic promotion. Evidence is isolated in commit `98dbd76`, and Git text conversion is disabled only for that immutable dataset subtree.
- Three failed server attempts were preserved and never promoted or appended: missing non-interactive Conda activation, native 178-step timeout, and postprocessing hash contamination. The successful attempt used a fresh bundle/checkout/result root and completed with `bootstrap.exit=0`.
- Plan 08-04 proves exact-eight dataset and LOCO-split readiness only. No model has been fitted or selected and no held-out prediction, OOD transfer, MPC, environment-adaptation or Agentic claim is supported. KID-01 data and KID-02/03/05 prerequisites are ready, but formal KID completion remains pending 08-05 and independent verification.
- Plan 08-05 completed all eight source-only LOCO folds. Every primary candidate/model was frozen before held-out access with zero test opens at freeze and zero post-test mutations; the evaluation envelope validates 106 referenced files with `warnings=[]`.
- Pooled Koopman was identical to simple linear and failed the frozen improvement/bootstrap gates. Conditional Koopman was ineligible after reason-coded quaternion-projection failures on `heavy_moderate`, `uuv4` and `uuv4_angled`.
- The atomic terminal envelope is a pathless `no_selection`; it validates with `warnings=[]`. Independent verification reran the canonical envelopes, structural audit and 64 relevant tests, then passed KID-01..05 as `PASS_VALID_FROZEN_NO_SELECTION`.
- Phase 8 is scientifically complete but no Phase 9 handoff model exists. This result supports held-out prediction evaluation and rejection only, not Koopman-MPC, environment transfer, Agentic, Sim2Real or hardware claims.
- Phase 8.1 completed its four local-only repair plans: corrected first-substep thruster dynamics, added isolated schema/model/evaluation v2.1, implemented fail-closed formal entrypoints and produced two pending-D-23 protocol proposals. The historical pre-approval review remains preserved.
- Phase 8.1 local validation passed 214 targeted tests and 435 relevant simulator/embodiment/runtime/v2 compatibility regressions. A later scoped semantic fix passed 5 targeted tests and 201 relevant regressions at source commit `5fd7a995e2fc1abfcc85b8921ab98096dafc3ee7`.
- The user approved the exact Phase 8.1 role hash `083d5eae3729e9939287345ab258dbfe4b4c8ca71ab769c2fd8616431a649417` and analysis hash `7a790b43d0f1581b8995ccdcbd9b6d259cb09bc8fe2268201400243d05f1e18c`. `protocols/phase8_1/d23_approval.json` machine-validates this decision binding and explicitly provides no human identity authentication.
- Phase 8.2 now owns a separate four-plan chain: local preflight/bundle, fresh server collection/pullback, formal eight-fold LOCO/outer decision and independent closeout. Its new operational contract tests pass locally, but no server or formal evidence has been created.
- Plan 08.2-01 completed the versioned preflight, bundle/bootstrap/collection/pullback/formal/closeout scripts and runbook. The checked-in preflight passed canonical approval, 32 targeted tests, 200 relevant regressions, compileall, script parsing, protected-history, clean-tree and absent-root gates; bundle verify plus isolated offline clone passed before any SSH.
- The first Plan 08.2-02 `v1` server bootstrap cloned the verified source but stopped before collection because the bootstrap reassigned its own readonly `RESULT_ROOT` variable. No episode, model, held-out test or formal result was created. The failed `/root/EASYkoopman-phase8-2-v1` attempt is preserved; the scoped repair uses fresh `v2` checkout/result roots and has 15 passing operational contract tests.
- Plan 08.2-02 collected the fresh v2.1 exact-eight dataset on the unchanged Isaac server from tested source `4f3b4cb` in isolated `/root/EASYkoopman-phase8-2-v2` (checkout) and `/root/EASYkoopman-phase8-2-results-v2` (results): 8 configurations x 12 episodes, 96 JSONL/manifest/log triplets, zero `.part`, 49,152 strict transitions. The operational `v1` failure (readonly variable reassignment before collection) is preserved and never promoted. Staged pullback validated all gates before atomic promotion of `dataset/` and `collection_status/`.
- Plan 08.2-03 executed the frozen formal eight-fold LOCO as eight independent Python processes with per-fold pre-test freeze and atomic publication, then assembled canonical `evaluation/` and published the terminal `NO_SELECTION` envelope through the checked-in formal chain; all eight folds succeeded. Pooled Koopman remained numerically identical to simple linear (24/24 evaluations) and both comprehensively lost to the persistence baseline; conditional Koopman failed closed 8/8 with reason `source_candidate_unavailable`. The terminal artifact is pathless; final refit was not invoked. Evaluation and selection evidence is isolated in commit `ce622c0`.
- Plan 08.2-04 independently revalidated canonical D-23, the dataset/evaluation/selection envelopes, the exact eight-fold set, zero leakage/freeze evidence and the exact evidence/claim boundary, producing `source/results/koopman_phase8_2/closeout/` with status `VERIFIED`, `terminal_decision=NO_SELECTION`, `model_handoff=false` and `fold_count=8`. Closeout gate alignment is isolated in commit `384caf1` and closeout evidence in `ab3c867`.

## Next Action

Read [v38本地就绪报告](../docs/phase8_4_v38_tolerance_repair.md) and [正式运行手册](../docs/phase8_4_projected_formal_v38_runbook.md). 本地任务1已完成；提请一次绑定freeze85fda36f…e9b6d7的新D-23。批准且服务器开启后，只运行新v38 preflight→validation→独立复核/GO→test；不重跑已冻结实验，不复用旧test，不重新拟合。当前无新正式批准、数据或Phase9 handoff。
