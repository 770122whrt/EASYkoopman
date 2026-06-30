# Project State: EASYkoopman

**Updated:** 2026-06-30  
**Current focus:** Phase 1.5 - Isaac Lab 2.x Compatibility Migration

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** 在不破坏 EasyUUV 原始仿真基线的前提下，建立一个可验证、可迭代的 Koopman+MPC 控制闭环。  
**Current phase:** Phase 1.5

## Current Understanding

- 当前 EasyUUV 目录是项目工作根。
- 远程目标是 `https://github.com/770122whrt/EASYkoopman.git`。
- Phase 1 已经建立 legacy controller boundary、controller mode 和 Koopman JSONL logging helper。
- 服务器实际环境已经确认是 Isaac Sim 5.0 + Isaac Lab 2.2.1。
- 旧代码仍大量使用 Isaac Lab 1.x 的 `omni.isaac.lab.*` namespace，因此 Phase 2 EDMD 前必须先让 direct controller 在服务器跑通。

## Decisions

| Date | Decision | Reason |
|------|----------|--------|
| 2026-06-10 | 所有 GSD 文件写入 `EasyUUV/.planning` | 用户要求不要写到根目录 |
| 2026-06-10 | 第一版保留 Isaac Lab 环境 | README 和代码已经使用 Isaac Lab，重写仿真框架会扩大风险 |
| 2026-06-10 | Phase 1 优先做 controller boundary 和 data collection | Koopman+MPC 需要可验证数据和 legacy baseline |
| 2026-06-10 | GitHub 发布目标为 `770122whrt/EASYkoopman` main | 用户指定 main 分支覆盖，后续开发再开 branch |
| 2026-06-30 | 插入 Phase 1.5 做 Isaac Lab 2.x 兼容迁移 | 服务器实际环境是 Isaac Sim 5.0 + Isaac Lab 2.2.1，旧 namespace 不能直接运行 |

## Blockers

- 本地仍不能运行 Isaac，需要在服务器 `/root/IsaacLab` 做最终 headless rollout。
- 当前主线代码仍有 Isaac Lab 1.x namespace，需要 Phase 1.5 迁移。
- 服务器需要拉取 `isaaclab2-migration` 分支并验证 direct controller rollout。

## Next Action

执行 Phase 1.5：

1. 写入 Isaac Lab 2.x 兼容 spec/plan。
2. 添加 source-contract 测试。
3. 迁移 direct controller 路径到 Isaac Lab 2.x。
4. 推送分支后在服务器用 `isaaclab.sh` 生成第一份 Koopman JSONL。
