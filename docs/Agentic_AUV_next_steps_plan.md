# Agentic-AUV v2.0 下一步执行计划

**更新日期：** 2026-08-09

**活动里程碑：** v2.0 Multi-Configuration Koopman Transfer and Environment-Aware Control

**当前阶段：** Phase 6 — EasyUUV 2.0 Intake and Multi-Configuration Qualification

**主线目标：** 多构型迁移、环境感知/在线更新、受限 Agent Supervisor

## 0. 文档定位与权威来源

这份文档用自然语言解释“代码现在有什么、还缺什么、为什么按这个顺序做”。阶段编号和验收状态以以下文件为准：

- `.planning/ROADMAP.md`：v2.0 Phase 6–12 的唯一阶段顺序；
- `.planning/REQUIREMENTS.md`：36 个 v2.0 需求及阶段映射；
- `.planning/STATE.md`：当前执行位置；
- `.planning/phases/06-easyuuv-2-0-intake-and-multi-configuration-qualification/06-SPEC.md`：Phase 6 要交付什么；
- 同目录 `06-01-PLAN.md` 至 `06-04-PLAN.md`：Phase 6 怎样实施和验证。

旧版文档中的 Phase 5.5/5.6 和“Phase 6 直接训练跨平台 Koopman”的编号已经失效。其有价值的诊断内容没有被否定，而是被重新吸收到 Phase 7–12；Git 历史仍保留旧版本。

## 1. 现在到底拥有哪几种机器人

新版 EasyUUV 代码公开支持八个构型：

| 构型 | 推进器数 | 4D 控制 mask `[roll,pitch,yaw,depth]` | declared rank | 含义 |
|---|---:|---|---:|---|
| `base` | 8 | `[1,1,1,1]` | 4 | 基准参数构型 |
| `long_body` | 8 | `[1,1,1,1]` | 4 | 长体动力学参数变化 |
| `heavy_moderate` | 8 | `[1,1,1,1]` | 4 | 质量/惯量参数变化 |
| `asymmetric` | 8 | `[1,1,1,1]` | 4 | 非对称动力学参数变化 |
| `uuv6` | 6 | `[1,1,1,1]` | 4 | 六推进器拓扑 |
| `uuv6_angled` | 6 | `[1,1,1,1]` | 4 | 倾斜六推进器拓扑 |
| `uuv4` | 4 | `[1,1,0,1]` | 3 | 四推进器，yaw 欠驱动 |
| `uuv4_angled` | 4 | `[1,1,0,1]` | 3 | 倾斜四推进器，yaw 欠驱动 |

因此，答案是“能拿到八种可测试构型”，但现在不能说成“八套外观不同的机器人”。它们共享同一个 `data/embodiment/embodiment.usd`，差异主要来自质量、惯量、浮力等参数和 4/6/8 推进器布局。内部还有 `heavy_duty` preset，但它不在公共 CLI 支持集合中，也不计入 Phase 6 通过率。

## 2. 当前代码已经有什么、还缺什么

收到的 `easyuuv_v2-main/` 已经包含：

- 八个公共构型及一个内部 preset；
- 4/6/8 推进器布局；
- TAM、伪逆/WLS 分配和 controllable-DOF 声明；
- `train.py`、`adapt.py` 等 Isaac 工作流；
- 共享 USD 资产和四个 gym task ID。

它目前缺少的不是“构型本身”，而是一个可以被本项目安全使用和审计的集成合同：

- 物理目录名是 `easyuuv_v2-main`，源码声明的包名却是 `easyuuv_nc`；
- 没有 `pyproject.toml`、`setup.py` 或 `setup.cfg`，服务器安装方式不唯一；
- 构型名称在多个文件重复，尚无单一机器可读 catalog；
- 尚无统一的拓扑/rank/控制边界资格报告；
- 尚无八构型 Isaac smoke artifact 和严格 validator；
- 现有 Koopman 仍是 v1.0 单构型合同：`state=11`、`reference=5`、`control=PWM_8`。

Phase 6 先解决前五项。最后一项不能通过简单改一个输入维度解决，必须在 Phase 7–9 逐层迁移。

## 3. Koopman 结合难度如何理解

整体难度是中高，但可以被拆成三个清楚的接口问题：

1. **数据语义问题（Phase 7）**：不同构型有 4/6/8 个实际 PWM，不能把变长 PWM 直接塞给同一个 Koopman 模型。统一模型输入应改为固定 4D virtual control `[roll,pitch,yaw,depth]`，实际 PWM 作为诊断/执行结果保留。
2. **模型迁移问题（Phase 8）**：要比较单构型、pooled、conditional Koopman，并使用按 configuration/episode 隔离的 held-out split，防止数据泄漏后虚假宣称迁移成功。
3. **闭环执行问题（Phase 9）**：MPC 在固定 4D 空间求解，再由当前构型的 TAM 分配到 4/6/8 个推进器；`uuv4*` 的 yaw 必须在优化和评分入口被 mask。

所以“把新版机器人导入旧 Koopman 后测试”不是一次性拼接。正确路径是：先证明八个环境真的可运行，再定义跨构型数据/控制接口，再训练模型，最后接 MPC。这样任何失败都能定位在环境、数据、模型或控制分配中的一个层次。

## 4. v2.0 canonical roadmap

| Phase | 主要问题 | 核心输出 | 进入下一阶段的门 |
|---|---|---|---|
| 6 | 八构型是否真实、可安装、可控且可审计 | package contract、catalog、TAM/rank report、server artifact | 八构型严格资格验证通过 |
| 7 | 4/6/8 推进器如何共享数据/控制语义 | schema v2、4D virtual-control Koopman Bridge、v1 adapter | schema/adapter 验证通过 |
| 8 | 一个 Koopman 是否能跨构型预测 | per-config/pooled/conditional 模型、held-out OOD gate | 至少一个模型通过预测门，否则 `no_selection` |
| 9 | Koopman-MPC 如何跨构型闭环 | 4D MPC、TAM 分配、underactuation mask、fallback | matched closed-loop 资格通过 |
| 10 | 环境变化时怎样感知并安全更新 | oracle/estimated context、RLS/KF、bounds、rollback | 收益门和全部安全 sentinel 同时通过 |
| 11 | Agentic 效果如何进入系统 | 低频 allow-listed supervisor、决策审计、三方消融 | Agent 不越过低层控制边界且有可验证增益 |
| 12 | 如何形成最终研究证据 | nominal/OOD/shift/combined matched evaluation | 全部门通过或明确 `no_selection` |

Agent 的作用因此被限定为低频监督：选择已准入模型、决定是否启用在线更新、在安全范围内调整 reference/MPC profile、触发 fallback。它不能直接生成 PWM，也不进入实时 `env.step()` 循环。

## 5. Phase 6 已规划的四份执行计划

### Wave 1 — `06-01-PLAN.md`

先证明收到的源码快照已经作为独立提交存在，再将跟踪目录规范化为 `easyuuv_nc`；添加 `pyproject.toml`、包内资产解析和 Isaac-free package tests。若快照提交不纯净、目标路径不安全或会改写 v1 证据，计划立即阻塞。

### Wave 2 — `06-02-PLAN.md` 与 `06-03-PLAN.md`

两份 TDD 计划可以并行：

- `06-02` 用 RED → GREEN → REFACTOR 建立唯一构型 catalog、纯 TAM/rank API，并让环境与两个 CLI 共用它；
- `06-03` 用同样的 TDD 顺序建立严格 artifact schema/validator，拒绝缺失/重复构型、假 server evidence、NaN/Inf、越界和推进器维度错误。

二者修改不同文件；validator 通过依赖注入/延迟 import 避免并行冲突。

### Wave 3 — `06-04-PLAN.md`

实现单构型 Isaac runner 和八结果合并器，完成全量本地回归与 runbook，然后停在人工服务器检查点。服务器需运行 `base >= 64` physics steps，其余七种各 `>= 8` steps，并拉回严格验证通过的 `qualification.json`。

本地 fixture 或 catalog-only 文件不能替代服务器证据。只要一个构型缺失、失败或输出越界，Phase 6 就保持未完成。

## 6. 提交与推送必须怎样分开

交付历史分为三个既定边界，后续 Phase 6 集成再按计划原子提交：

1. **Simulator snapshot push**：只包含收到的 `easyuuv_v2-main/` 原始树，不包含重命名、测试或规划修改。
2. **v1 source evidence push**：只包含 `source/results/` 和 `docs/v1.0_source_results_manifest.md`，明确它是 v1.0 服务器实验归档，不把它包装成 v2 结果。
3. **v2 planning push**：只包含 PROJECT/REQUIREMENTS/ROADMAP/STATE、Phase 6 SPEC/CONTEXT/RESEARCH/PATTERNS/PLAN 和设计说明。

执行 Phase 6 后，package/catalog/validator/runner 分别使用计划规定的任务提交。整个组装过程不删除历史 phase 目录、不改写 `v1.0` tag、不使用 reset/force-push。远端看到的每一部分都能独立回答“这是什么、来自哪里、是否经过修改”。

## 7. 近期执行顺序

当前规划已经完成，下一步不是立即训练 Koopman，而是：

```text
1. 按既定边界组装并推送 simulator snapshot、v1 source evidence、v2 planning。
2. 执行 Phase 6 Wave 1，建立唯一 easyuuv_nc package contract。
3. 执行 Wave 2 的 catalog/TAM 与 artifact-validator TDD。
4. 执行 Wave 3 本地回归并生成服务器 runbook。
5. 在服务器完成八构型 smoke，拉回并验证 qualification.json。
6. Phase 6 verification 通过后才规划/执行 Phase 7 Koopman Bridge。
```

## 8. 当前可以准确对外表达的结论

可以说：新版代码提供八种公开动力学/推进器构型，包含 4、6、8 推进器和明确的欠驱动差异；v2.0 已建立从环境资格验证、跨构型 Koopman 数据合同、模型 OOD gate、configuration-aware MPC、环境在线更新到低频 Agent Supervisor 的分阶段路线。

暂时不能说：八种构型已经全部在 Isaac 上通过；现有 v1 Koopman 已经支持 4/6/8 推进器；Koopman 已证明跨构型迁移；Agent 已产生闭环收益。这些结论分别需要 Phase 6、7–9、8/12 和 11/12 的实际证据。

---

一句话总结：先把八种 EasyUUV 构型变成可信、可审计的实验对象，再统一 4D Koopman 控制语义，随后验证跨构型预测与闭环迁移，最后加入受限的环境更新和 Agent 监督。
