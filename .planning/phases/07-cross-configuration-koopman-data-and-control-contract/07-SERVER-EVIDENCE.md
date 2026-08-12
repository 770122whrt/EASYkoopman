---
phase: 07-cross-configuration-koopman-data-and-control-contract
plan: "04"
evidence_date: 2026-08-12
phase7_gate: pass
evidence_level: server_isaac_smoke
tested_source_commit: a36689abeee00c98eb480ebcdf02e147edcaa6e3
evidence_commit: 1c0a6cabe82d4153efd9a8e60485f2423ddd4f41
artifact_sha256: 2f07a6835f0b32fe0277fd819394580f261b6028dc3d07520e70b124e0758463
configuration_count: 3
---

# Phase 7 Server Evidence

`phase7_gate: pass`

2026-08-12 在既有 `agentic-AUV` 服务器上完成了 Phase 7 的三拓扑真实 Isaac smoke。服务器继续使用原有 `/root/IsaacLab`，Phase 7 使用新的隔离 checkout `/root/EASYkoopman-phase7-v2`。正式证据经 staged SCP、44 文件 exact inventory、远端/本地 SHA-256 对照和本地严格 validator 后，才提升到 `source/results/koopman_phase7/`，并作为独立证据提交 `1c0a6ca` 保存。

## 这次测试实际证明了什么

本次测试证明 Phase 7 的真实数据链已经接通：Isaac Sim 中的 `base`、`uuv6`、`uuv4` 环境可以 create/reset/step，EasyUUV runtime 能在同一个 step token 中提供 state、reference、raw action、post-mask/pre-TAM 4D virtual control、实际 N 路 PWM、post-actuator thruster-only wrench、platform context、oracle environment context 和 next state，`KoopmanBridgeV2` 能将它们原子组装为严格 schema v2 transition，随后由 `KoopmanEpisodeLoggerV2`、manifest、merger 和 aggregate validator 接收。

它还在真实 `uuv4` 运行中证明 yaw 欠驱动 mask 位于 TAM 之前：2 行 transition 带有非零 raw yaw（`+0.2`、`-0.2`），对应的 `virtual_control_4[2]` 都精确为 `0.0`，没有把不可控 yaw 藏进 PWM padding 或伪逆结果。

这不是 Koopman 效果实验。本阶段没有训练或选择多构型 Koopman 模型，没有计算预测误差/OOD 泛化，没有让现有 MPC 改用 4D control，也没有比较闭环跟踪效果。上述结论分别属于 Phase 8 和 Phase 9。

## 执行与回传链

- 本地受测源码：`a36689abeee00c98eb480ebcdf02e147edcaa6e3`。
- 服务器证据提交：`1c0a6cabe82d4153efd9a8e60485f2423ddd4f41`；artifact 内的 `source_commit` 仍指向实际受测源码，而不是后续证据提交。
- 本地 preflight：Phase 7 定向 `224 passed, 1 skipped`；全仓 `561 passed, 1 skipped`；collect-only `562`；compileall、pip check、Bash/PowerShell parse、protected diff、clean worktree 和 canonical-absent gate 均通过。
- 离线 bundle SHA-256：`ae0cdfb789d23dff6922c63269b847db0485ab1bde57e8a6450da1c337dd6131`；本地与服务器一致，`git bundle verify` 确认完整历史和唯一 branch ref。
- 服务器唯一入口：`bash /root/phase7_server_bootstrap.sh`；bootstrap 从 bundle 克隆固定提交，再执行提交内 `scripts/phase7_server_smoke.sh`。
- 三个构型由三个独立 `/root/IsaacLab/isaaclab.sh -p` 进程运行；任一 native exit、`tee` exit、semantic validator、文件/hash 或 exact-three gate 失败都会阻止 aggregate。
- 本地回传入口：`scripts/phase7_pullback.ps1`；它先在隔离 staging 中验证 self-excluding relative-path inventory，比较 source/IsaacLab sidecar、所有文件 hash 并运行严格 aggregate validator，成功后才原子提升 canonical evidence。
- 服务器和 pullback validator 都返回 `validation_gate=koopman_v2_exact_three_server_evidence_valid`、`configuration_count=3`、`warnings=[]`。

## 运行时 provenance

| 项目 | 实际值 |
|---|---|
| Isaac Sim contract / distribution | `5.0` / `5.0.0.0` |
| Isaac Lab VERSION / release label | `2.2.1` / `v2.2.1` |
| Isaac Lab distribution metadata | `0.45.9`（editable metadata；版本合同由 VERSION/release identity 锁定） |
| Isaac Lab release commit | `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| Isaac Lab server HEAD | `c91a125c73c8b574878419a9583afc0b63b99f0a` |
| Server HEAD parent | `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| 既有 tracked dirty files | `source/isaaclab_mimic/setup.py`, `source/isaaclab_rl/setup.py` |
| 既有 patch SHA-256 | `d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079` |
| Python / Conda env | `/opt/conda/envs/isaaclab/bin/python`, env `isaaclab` |
| Wrench source | `post_actuator_thruster_only` |
| Context source | `same_step_oracle_snapshot` |

Phase 7 沿用 Phase 6 已锁定的服务器状态：两处 setup 改动是既有 proxy rewrite。脚本校验其精确文件集合、parent/HEAD 和 patch hash，拒绝额外漂移；没有修改 `/root/IsaacLab`。

## 三拓扑结果

控制顺序固定为 `[roll, pitch, yaw, depth]`。

| Configuration | Thrusters | Allocation | Control mask | Steps | Nonzero wrench rows | Oracle rows | Raw-yaw probes / leaks | Native / tee / semantic | Episode SHA-256 |
|---|---:|---|---|---:|---:|---:|---|---|---|
| `base` | 8 | legacy 8-thruster path | `[1,1,1,1]` | 8 (`0..7`) | 8 | 8 | n/a | `0 / 0 / pass` | `74dfe6c79cfbc2e0b622780b79d20cd13495ea20177915a87b689a9d3034e87b` |
| `uuv6` | 6 | `pinv` | `[1,1,1,1]` | 8 (`0..7`) | 8 | 8 | n/a | `0 / 0 / pass` | `f569946acf664af26b164449b5a8ae58332b63a27b5b6b0e01b30f6db3a75f51` |
| `uuv4` | 4 | `wls` | `[1,1,0,1]` | 8 (`0..7`) | 6 | 8 | 2 / 0 | `0 / 0 / pass` | `08b07ed3545212127b13cd6d664107ca1f764b5851f999f288c83f65cb6374ae` |

全部 24 行均为有限、严格 schema-v2 transition，step index 连续。`uuv4` 的两次 yaw probe 位于 step 2 和 6：`0.2 -> 0.0`、`-0.2 -> 0.0`。`uuv4` 有两行 wrench 为零是确定性动作序列中的零/被 mask 输入结果，不是 telemetry 缺失；其余 6 行记录非零实际 wrench。

## Artifact 与严格验证

- Canonical aggregate：`source/results/koopman_phase7/evidence.json`
- Server/local aggregate SHA-256：`2f07a6835f0b32fe0277fd819394580f261b6028dc3d07520e70b124e0758463`
- Episodes/manifests/logs：`base.*`, `uuv6.*`, `uuv4.*`
- Server validator capture：`source/results/koopman_phase7/validator.json`
- Pure local pullback verdict：`source/results/koopman_phase7/pullback_validator.json`
- Native/tee/semantic gates：`source/results/koopman_phase7/status/`
- 全文件清单：`source/results/koopman_phase7/all_files.sha256`；44 个 server-authored 文件，使用相对路径且明确排除清单自身。server 写后验证一次，pullback 提升前再验证一次；本地随后生成的 `pullback_validator.json` 不冒充 server-authored byte。

严格验证结果：

```json
{
  "configuration_count": 3,
  "configurations": ["base", "uuv6", "uuv4"],
  "evidence_level": "server_isaac_smoke",
  "source_commit": "a36689abeee00c98eb480ebcdf02e147edcaa6e3",
  "validation_gate": "koopman_v2_exact_three_server_evidence_valid",
  "warnings": []
}
```

## CONT-01..05 证据索引

| Requirement | Result | Concrete evidence |
|---|---|---|
| CONT-01 | PASS | `koopman/schema_v2.py` 与严格 validator 覆盖全部固定字段、shape/range/context/provenance/continuity；24 行真实服务器 transition 和 3 个 manifest 均通过。 |
| CONT-02 | PASS | `KoopmanBridgeV2` 记录统一 post-mask/pre-TAM `[roll,pitch,yaw,depth]`；DatasetV2 的 `.U` 固定为 4D；真实 8/6/4 拓扑共享该语义，`uuv4` 两次非零 raw yaw 均变为零 virtual yaw。现有 v1 MPC 仍冻结为 PWM8，实际 MPC 迁移属于 Phase 9。 |
| CONT-03 | PASS | `motor_pwm_padded_8`、`thruster_mask_8` 和 diagnostics 与 model-facing `.U` 分离；4/6 拓扑 padding 为精确零，默认 DatasetV2 没有 PWM 控制别名。 |
| CONT-04 | PASS | 24 行均含独立 oracle/estimated 对象；oracle 为 `same_step_oracle_snapshot` 且 available，estimated 显式 unavailable，没有复制 oracle 冒充部署估计。 |
| CONT-05 | PASS | `V1CompatibilityView` 只读调用既有 v1 loader，标记 `source_schema=v1`、缺失字段和 false training eligibility；strict v2 validator 拒绝 raw/view v1，v1 模型/MPC默认语义保持不变。 |

## D-04..16 disposition

| Decisions | Result | Evidence |
|---|---|---|
| D-04..D-07 | PASS | 4D virtual control、raw/virtual 分离、diagnostic PWM+mask 和 post-actuator thruster-only wrench 在 schema、Bridge、DatasetV2 和真实 rows 中分别出现。 |
| D-08..D-11 | PASS | platform context 来自活动 catalog/runtime；oracle/estimated 分离；严格 reason-coded validation；每行绑定同一步 pre/post telemetry，episode invariants 和时间连续。 |
| D-12 | PASS | local fixtures、mutation tests 和 Isaac-free full suite 仅声称 `local_contract`。 |
| D-13 | PASS | `base`/`uuv6`/`uuv4` 各 8 个真实连续 transition，覆盖 8/6/4 推进器拓扑。 |
| D-14 | PASS | source commit、Isaac versions/repo state、三组 native/tee/semantic status、log/file hash 和 aggregate hash 全部一致。 |
| D-15 | PASS | runbook、machine artifact、本证据报告、`07-04-SUMMARY.md` 和 `07-VERIFICATION.md` 共同映射 CONT-01..05。 |
| D-16 | PASS | 受测服务器实现截止 `a36689a`；promoted-directory 复验接口补强为 `21b4b77`；服务器证据单独提交为 `1c0a6ca`；planning closure 在后续独立提交中完成。 |

## Warnings 与保留失败现场

Isaac 日志保留了 Warp CUDA `cuDeviceGetUuid`/error 36、DirectRLEnv deprecation、render interval 和 Fabric prototype warnings。运行仍实际使用 RTX 4090、Vulkan/PhysX 并完成全部 telemetry/semantic gates；这些 warning 不被解释为性能证据。

正式成功前的失败尝试没有删除或混入 canonical artifact：

- `88c9139`：缺少 locked conda activation，在 runner 前失败。
- `6154c56`：runner 将自身 result-root 误判为 source drift，且 `SystemExit(0)` 掩盖异常；后续 TDD 修复。
- `e364f68`：三构型采集成功，但 merger 错用 `5.0.0` 而非 canonical `5.0`，aggregate 被拒绝。
- `801a43d`：三构型采集成功，但 server 目录布局与 strict merger 的 flat root 不一致，aggregate 被拒绝。
- `eb4669d` / evidence `b16fb89`：三构型和 aggregate 已通过，但最终审计发现 `all_files.sha256` 将创建时为空的自身纳入清单，self-entry 写完即失真；整个包被降级归档，新增 exact inventory validator 后重新运行服务器和 pullback，没有在原地修补或复用旧 transition。

这些现场分别保存在本地 ignored `.pytest-tmp/phase7-server-failure-*` 与服务器 `/root/EASYkoopman-phase7-v2-failed-*` 路径。原始 `logs/isaaclab_repo_diff.patch` 中的空白行也原样保留；清理它们会破坏已绑定 patch SHA-256，因此它们不是待格式化的生产源码。

## 结论边界

Phase 7 可以关闭，因为数据/控制合同已经在真实 simulator telemetry 上成立且可复核。下一阶段仍必须重新回答一个尚未证明的问题：这些对齐数据能否识别出在 held-out configuration 上通过预测门的 Koopman 模型。若无人通过，Phase 8 必须允许 `no_selection`，不能从本 smoke 推导成功。
