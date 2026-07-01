# Project State: EASYkoopman

**Updated:** 2026-06-30
**Current focus:** Phase 2.5 - Offline Koopman Model Qualification Gate

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
