# EASYkoopman

## 项目目标

以 EasyUUV / Isaac 仿真建立 Koopman-UUV 与后续 Agentic-AUV 的可复现证据：先验证预测与有界控制，再研究跨构型、环境适应及上层 Agent 的增量作用。普通线性、persistence、物理模型和分构型模型可作对照或必要 fallback，不能因其局部表现更好而自动替换研究目标。

v1.0 冻结于 tag `v1.0`。v2.0 已完成八构型接入与拓扑无关数据/控制接口；Phase 8.2 以 `VERIFIED / NO_SELECTION` 结束，没有向 Phase 9 交付合格模型。Phase 9 保持开放，阶段证据与当前工作见[研究索引](../docs/phase9_research_index.md)、[STATE](STATE.md)和[ROADMAP](ROADMAP.md)。

## 当前授权范围：v87（2026-09-29）

用户要求扩大含扰动场景重新离线训练与独立测试，继续比较三臂：冻结物理、完整提升 Koopman、冻结物理＋自主提升学习部分。物理基线不利用新增扰动数据重新校准，也不读取隐藏扰动真值。结合策略保留，但其整体优势和闭环收益仍需实验。

本轮固定 base 构型与额外 20% 二次阻力，扩大输入类型、幅值和轨迹时长。训练、验证、测试按整条轨迹分离；模型在测试时全部冻结，不能反复使用测试结果调到获胜。数据数量、信号、参数与门限由[v87运行说明](../docs/phase9_diverse_v87_runbook.md)及版本化协议统一管理，不在入口文档重复维护。

允许审查并修复共同控制链、数据校验和求解器问题。先完成预测与求解验证，再按准入条件执行相同任务、初态和扰动下的 2 秒配对闭环；之后才考虑更长时间与更多构型。本轮不开展在线自进化、Agent 或额外模型家族。

## 必须保持的控制与证据边界

- 完整非线性提升状态在预测时域内自行传播；实际控制边界可根据当前状态及因果历史初始化，预测内部不得不断解码再重提升，不得读取未来真值。
- 高层策略不能绕过有界低层控制直接输出 PWM。三臂共用可控轴掩码、TAM、PWM、死区、执行器记忆和实际 Isaac plant；PWM 受 `[-1,1]` 及更严格的任务约束限制。
- 控制接口为 TAM 前 `virtual_control_4 = [roll,pitch,yaw,depth]`；它是四维虚拟命令，不是四维物理 wrench。`uuv4*` 不可控偏航必须显式处理，不能计作可行跟踪目标。
- 求解状态、原始最后候选、独立可行性、最终所选计划与 fallback 分别记录。超时候选可经独立验收使用，超时本身不能改写成收敛，历史 fallback 不能算新候选。
- 模型、checkpoint、来源与版本不一致时拒绝准入；`no_selection` 是有效结果。局部收益不自动升级为普遍模型优势或未见构型泛化。
- 本地测试、合成数据、离线求解、真实 Isaac 轨迹与闭环效果分开报告。模型内部预测代价不跨模型比较，也不替代实际任务收益。
- 原始实验材料、失败证据、v1.0 和 Phase 8/8.1/8.2 冻结结果保留；新增证据使用独立版本目录，不覆盖旧测试。

## 后续里程碑与未证明范围

八个支持构型为 `base`、`long_body`、`heavy_moderate`、`asymmetric`、`uuv6`、`uuv6_angled`、`uuv4`、`uuv4_angled`。配置接入不等于 Koopman 迁移成功；它们共享 USD 外观，机械参数或推进器拓扑不同。

跨构型闭环迁移、长时稳定、实时 30Hz、真实传感器状态估计、在线 RLS/KF、自适应和 Agent 增量均须另行验证。在线更新若后续获准，仍须参数边界、非有限值拒绝、冻结先验与回滚。Agent 只能是低频 allow-list supervisor，不能进入 PWM 或实时 `env.step()` 控制环。当前不作 Sim2Real、硬件或普遍六自由度成功声明。

## 历史与文档分工

[STATE](STATE.md)只记录当前工作；[研究索引](../docs/phase9_research_index.md)负责代码入口与历史导航；[控制链合同](../docs/phase9_control_chain_contract.md)负责共同执行语义；版本运行说明负责精确协议，版本报告负责数字结论。旧文档中“当前”“下一步”只代表其版本时点。

本次整理前 PROJECT、STATE、README 与控制链合同原文完整保存在[历史档案](../docs/history/phase9_status_before_v87_20260929.md)。冻结里程碑见[MILESTONES](MILESTONES.md)、[v1.0总结](reports/MILESTONE_SUMMARY-v1.0.md)及[Phase 8.2验证](phases/08.2-phase-8-1-fresh-server-evaluation-and-closeout/08.2-VERIFICATION.md)。历史具体目录以研究索引链接核对为准。
