# Project State: EASYkoopman

**Updated:** 2026-06-10  
**Current focus:** Phase 1 - Baseline Data And Controller Boundary

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** 在不破坏 EasyUUV 原始仿真基线的前提下，建立一个可验证、可迭代的 Koopman+MPC 控制闭环。  
**Current phase:** Phase 1

## Current Understanding

- 当前 EasyUUV 目录是项目工作根。
- 当前目录尚未作为独立 Git 仓库初始化；远程目标是 `https://github.com/770122whrt/EASYkoopman.git`。
- 现有代码已经包含 Isaac Lab `DirectRLEnv`、RSL-RL workflow、8 推进器动力学和水动力模型。
- 第一阶段不实现 MPC 本体，只建立 baseline、controller boundary 和 data collection。

## Decisions

| Date | Decision | Reason |
|------|----------|--------|
| 2026-06-10 | 所有 GSD 文件写入 `EasyUUV/.planning` | 用户要求不要写到根目录 |
| 2026-06-10 | 第一版保留 Isaac Lab 环境 | README 和代码已使用 Isaac Lab，重写仿真框架会扩大风险 |
| 2026-06-10 | 第一阶段优先做控制器边界和数据采集 | Koopman+MPC 需要可验证数据和 legacy baseline |
| 2026-06-10 | 初次 GitHub 发布目标为 main 分支覆盖 | 用户指定 `770122whrt/EASYkoopman` main 覆盖 |

## Blockers

- 本机 Isaac Sim/Lab 版本待确认。
- 当前会话未运行 Isaac 仿真验证，因为需要 Isaac Lab 环境和 GUI/模拟器运行上下文。
- GitHub 远程认证状态待确认。

## Next Action

执行 Phase 1 计划：

1. 保护 legacy controller 行为。
2. 建立 controller mode 和数据记录结构。
3. 生成 baseline 日志。
4. 更新验证文档。
