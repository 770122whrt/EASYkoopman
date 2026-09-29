---
phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification
plan: "04"
subsystem: qualification-runtime
tags: [isaac-sim, isaac-lab, eight-configurations, provenance, pullback, fail-closed]

requires:
  - plan: 06-02
    provides: canonical eight-configuration catalog and topology truth
  - plan: 06-03
    provides: strict versioned qualification artifact and validator
provides:
  - deterministic one-configuration Isaac qualification runner
  - exact-eight merger and semantic pipeline gate
  - offline bundle/bootstrap/server/pullback evidence chain
  - actual eight-configuration server smoke artifact
  - Phase 6 server evidence handoff
affects: [phase-7, phase-8, phase-9]

key-files:
  created: [workflows/qualify_easyuuv_v2.py, workflows/merge_easyuuv_v2_qualification.py, scripts/phase6_server_bootstrap.sh, scripts/phase6_server_qualification.sh, scripts/phase6_pullback.ps1, docs/phase6_easyuuv_v2_qualification_runbook.md, source/results/koopman_phase6/qualification.json]
  modified: [easyuuv_nc/task_registration.py, easyuuv_nc/embodiments.py, easyuuv_nc/env/easyuuv_env.py, workflows/easyuuv_v2_qualification_artifact.py, workflows/validate_easyuuv_v2_qualification.py]

requirements-completed: [QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, QUAL-07, QUAL-08]
completed: 2026-08-11
---

# Phase 6 Plan 04: Real Isaac Qualification Summary

**八种 EasyUUV 2.0 构型已在真实 Isaac Sim 5.0 / Isaac Lab 2.2.1 服务器上完成分层 smoke，严格 artifact、哈希回传与本地复验全部通过。**

## 完成内容

- 实现单构型 runner：AppLauncher 后显式注册 Gym task，按固定 `+0.1/-0.1` 序列驱动 `[roll,pitch,yaw,depth]`，并从环境读取实际 virtual control 与 clipped motor telemetry。
- 实现 exact-eight merger：缺失、重复、额外构型、版本/源码/provenance 不一致或任意失败行都会阻断最终 artifact。
- 建立离线服务器交付链：clean tested HEAD → Git bundle/sidecar → SCP → 隔离 clone → eight-process qualification → merge/strict validate/hash → staged pullback → local strict validate → atomic promotion。
- 修复真实 Isaac Lab 2.2.1 接口差异，包括兼容 import、显式 task registration、新式 action/observation/state spaces，以及将共享 USD 作为 `RigidObject` 而不是 articulation 加载。
- 在实际服务器完成 `base` 64 steps 和其余七构型各 8 steps；全部环境创建、reset、step、telemetry、进程/log/artifact gates 通过。
- 将 64 个最终证据文件以独立提交 `7670f66` 记录并推送，未与 planning 收口混合。

## 关键提交边界

- `e48695c` → `a69783f`：runner/merger 的 RED→GREEN 基线。
- `2db585e` → `2fce253`：runtime provenance merge 绕过的 RED→GREEN。
- `eda4d66`：隔离服务器 runbook。
- `2a268c1` → `537cb96`：本地深度审查后逐项修复证据落盘、版本、清洁源码、离线安装、AppLauncher 顺序、Gym 注册、pipeline 与 pullback 问题。
- `5471c9f` → `e24f76a`：真实服务器暴露的 provenance、bundle、semantic gate、Isaac Lab spaces、USD articulation 与 pullback ignore 问题，均先有回归证据再修复。
- `7670f66`：只记录最终 `source/results/koopman_phase6` 服务器证据。

## 服务器 checkpoint 结果

- User action：2026-08-11 用户启动既有服务器；服务器地址/配置保持不变。
- Assistant action：通过 `agentic-AUV` 直接 SSH/SCP；未要求服务器访问 GitHub。
- Historical isolation：`/root/EASYkoopman` 未修改；新 checkout 使用 `/root/EASYkoopman-phase6-v2`。
- Tested code：`e24f76a0d5c047eeb16c6acf20fdd01bd20c264b`。
- Runtime：Isaac Sim `5.0`；Isaac Lab VERSION/release `2.2.1` / `v2.2.1`。
- Result：8/8 configurations pass；base 64 steps，其他 7 个各 8 steps。
- Safety telemetry：nonfinite `0`，dimension mismatch `0`，所有 action/motor extrema 在 `[-1,1]`。
- Strict gate：`server_pass`，configuration count `8`，warnings `[]`。
- Artifact SHA-256：`6cb83fcb63fc7bd33ffcfa678d09f3e128fcf6f6380ee3b948541814421a1a92`，服务器记录、本地计算和 sidecar 三者一致。

详细逐构型数值和 provenance 见 `06-SERVER-EVIDENCE.md`。

## 本地验证

- Phase 6 定向测试在最终服务器就绪修复后通过。
- 全量本地测试在服务器执行前最后候选上为 `335 passed`；planning/evidence 收口后再次执行的最终结果记录在 `06-VERIFICATION.md`。
- `compileall`、`pip check`、五个 Bash 脚本解析、两个 PowerShell 脚本解析与 `git diff --check` 均通过。
- `git diff v1.0 -- .planning/milestones .planning/reports koopman/model.py koopman/mpc.py` 为空，v1.0 冻结证据和 Koopman/MPC 语义未被 Phase 6 改写。

## 偏差与修复

真实服务器暴露了四类本地 mock 难以发现的问题：

1. `git bundle verify` 必须在 Git repository context 中运行；bootstrap 改为临时 bare repo 验证。
2. 服务器 IsaacLab checkout 是官方 `v2.2.1` 之后的已知 commit，并带两个既有 proxy rewrite；证据模型改为精确记录 release、HEAD、parent、dirty-file set 和 patch hash，而不是伪装成完全 clean release。
3. Isaac Lab 2.2.1 需要显式 spaces，且共享 USD 实际是 rigid-body 根而不是 articulation 根；两项均通过真实失败日志定位并修复。
4. 服务器 artifact 仅凭进程退出码不够可靠；pipeline 增加 row existence/config/evidence/status semantic gate，并让 row 在 Kit shutdown 前原子 flush。

这些偏差均产生新的本地回归合同、完整重测、全新 bundle 和八进程重跑；没有编辑服务器结果来“修成通过”。

## 明确边界

Phase 6 的通过意味着“八构型 simulator 接入与受控 telemetry 资格门成立”，不意味着“Koopman 已在八构型上表现良好”。本阶段的动作序列只是小幅确定性 smoke excitation；没有训练 Koopman，没有运行 Koopman-MPC，没有做 OOD、环境变化或 Agent 比较。Phase 7 必须先定义统一 4D virtual-control/data schema，之后才有资格讨论 Koopman 效果。

## Self-check

- [x] Exactly eight public configurations; no `heavy_duty` row.
- [x] Actual server evidence; no local/catalog artifact substitution.
- [x] Base 64 steps; seven other configurations 8 steps each.
- [x] Actual telemetry finite, bounded and dimension-consistent.
- [x] Source/runtime provenance and artifact hashes independently bound.
- [x] Server evidence and planning closure use separate commits.
- [x] v1.0 archives and Koopman model/MPC semantics remain unchanged.
- [x] QUAL-01..08 have concrete evidence.

Result: **PASSED**.
