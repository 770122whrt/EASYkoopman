# Project State: EASYkoopman

**Updated:** 2026-06-30
**Current focus:** Collect longer legacy logs for Koopman model training

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** 在不破坏 EasyUUV 原始仿真基线的前提下，建立一个可验证、可迭代的 Koopman+MPC 控制闭环。

## Current Understanding

- 当前 EasyUUV 目录是项目工作根目录。
- 远程目标仓库是 `https://github.com/770122whrt/EASYkoopman.git`。
- 服务器实际环境已经确认：Isaac Sim 5.0 + Isaac Lab 2.2.1。
- Phase 1 已经建立 legacy controller boundary、pre-thrust 8D PWM cache 和 Koopman JSONL logging helper。
- Phase 1.5 已经让 direct-controller smoke rollout 在服务器上跑通，并生成可验证 JSONL。
- 当前 smoke log 只有 2 samples，足够证明数据链路，不足以训练正式 Koopman 模型。
- Phase 2 离线代码已经完成：dataset、lifting、EDMD、model artifact、evaluation 和 CLI。
- EasyUUV USD assets 可以纳入 Git，以避免服务器代码和模型资产不同步。

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
| 2026-06-30 | Phase 2 以离线 EDMD 为核心 | 先做可保存、可评估的 Koopman model，再进入 Phase 3 MPC |
| 2026-06-30 | Phase 2 本地实现通过验证 | `python -m pytest -q` 显示 36 passed |

## Blockers And Risks

- 本地仍不能运行 Isaac；所有 Isaac rollout 继续在服务器 `/root/IsaacLab` 执行。
- 当前只有 2 条 smoke samples，不能用于正式训练。
- 服务器 Git clone/pull 可能继续遇到 TLS 超时；必要时使用 zip 或 git bundle 传输。
- Phase 2 必须保持 Isaac-free，避免把本地可运行的离线训练又绑回服务器。

## Next Action

采集长日志并训练正式模型:

1. 在服务器运行长 step/sine/irregular legacy-controller rollout。
2. 用 `workflows/validate_koopman_log.py` 验证每份 JSONL。
3. 用 `workflows/train_koopman.py` 训练真实 Koopman 模型。
4. 用 `workflows/evaluate_koopman.py` 生成 one-step 和 multi-step metrics。
5. 根据预测误差决定是否需要更多 excitation 数据，再进入 Phase 3 MPC。
