---
phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification
plan: "04"
evidence_date: 2026-08-11
qualification_gate: pass
evidence_level: server_isaac_smoke
tested_source_commit: e24f76a0d5c047eeb16c6acf20fdd01bd20c264b
evidence_commit: 7670f66
artifact_sha256: 6cb83fcb63fc7bd33ffcfa678d09f3e128fcf6f6380ee3b948541814421a1a92
configuration_count: 8
---

# Phase 6 Server Evidence

`qualification_gate: pass`

2026-08-11 在既有 `agentic-AUV` 服务器上完成了八构型 Isaac 资格测试。服务器使用隔离目录 `/root/EASYkoopman-phase6-v2`；历史目录 `/root/EASYkoopman` 与 `/root/IsaacLab` 均未被修改。正式结果已通过 fail-closed pullback 流程回传到 `source/results/koopman_phase6/`，并作为独立实验提交 `7670f66` 推送。

## 这次测试实际证明了什么

本次测试证明新版 `easyuuv_nc` 可以在真实 Isaac 运行时中完成四个 Gym task 的注册，并且八种公开构型都能创建环境、reset、执行确定性有界动作、读取实际 virtual-control/PWM telemetry。它还证明 4/6/8 推进器维度、TAM rank 和 `uuv4*` yaw 欠驱动声明与运行结果一致。

这不是 Koopman 效果实验。Phase 6 没有训练或调用 Koopman、MPC、PPO 或 Agent，也没有比较跟踪误差、跨构型泛化或环境适应收益；这些工作从 Phase 7 开始建立数据/控制合同，并在 Phase 8–12 逐步完成。

## 执行与回传链

- 本地测试源码：`e24f76a0d5c047eeb16c6acf20fdd01bd20c264b`。
- 本地 bundle SHA-256：`5b402b25b36acd46304c48eb49917f5cef48e75816afb5948a1968bce40af233`；上传后服务器哈希相同。
- 服务器唯一入口：`bash /root/phase6_server_bootstrap.sh`。
- bootstrap 验证 bundle ref/sidecar 后，将同一提交克隆到 `/root/EASYkoopman-phase6-v2`，再调用提交内的 `scripts/phase6_server_qualification.sh`。
- 每个构型通过独立的 `/root/IsaacLab/isaaclab.sh -p -u ...` 进程运行；完整八条命令固定记录在 `docs/phase6_easyuuv_v2_qualification_runbook.md` 的 `Server Eight-Configuration Smoke`。
- 本地回传入口：`.\scripts\phase6_pullback.ps1`；它先在隔离 staging 中验证源码、IsaacLab provenance、远端/本地 SHA-256 和严格 validator，全部通过后才原子提升到 canonical evidence 目录。
- 服务器与本地严格 validator 都输出 `qualification_gate=server_pass`、`configuration_count=8`、`warnings=[]`。
- 64 个正式证据文件由提交 `7670f66` 独立记录；artifact 内的 `source_commit` 仍指向实际受测源码 `e24f76a...`，而不是后续证据提交。

## 运行时 provenance

| 项目 | 实际值 |
|---|---|
| Isaac Sim contract / distribution | `5.0` / `5.0.0.0` |
| Isaac Lab VERSION / release tag | `2.2.1` / `v2.2.1` |
| Isaac Lab distribution metadata | `0.45.9`（editable distribution metadata；版本合同由 VERSION/release identity 锁定） |
| Isaac Lab release commit | `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| Isaac Lab server HEAD | `c91a125c73c8b574878419a9583afc0b63b99f0a` |
| Server HEAD parent | `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| 既有 tracked dirty files | `source/isaaclab_mimic/setup.py`, `source/isaaclab_rl/setup.py` |
| 既有 patch SHA-256 | `d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079` |
| Python / Conda env | `3.11.13`, `/opt/conda/envs/isaaclab/bin/python`, env `isaaclab` |

这两处 setup 文件是服务器原有 proxy rewrite。资格脚本逐项绑定其文件集合和 patch hash，并拒绝任何额外 staged/untracked IsaacLab 文件，因此没有把“任意脏环境”当作发布基线。

## 八构型结果

控制 mask 顺序固定为 `[roll, pitch, yaw, depth]`。

| Configuration | Thrusters | Mask | Rank | Steps | Action range | Motor range | Nonfinite | Dim mismatch | Status |
|---|---:|---|---:|---:|---|---|---:|---:|---|
| `base` | 8 | `[1,1,1,1]` | 4 | 64 | `[-0.0996355, 0.0996355]` | `[-0.0996355, 0.0996355]` | 0 | 0 | pass |
| `long_body` | 8 | `[1,1,1,1]` | 4 | 8 | `[-0.0996028, 0.0996028]` | `[-0.0996028, 0.0996028]` | 0 | 0 | pass |
| `heavy_moderate` | 8 | `[1,1,1,1]` | 4 | 8 | `[-0.0996028, 0.0996028]` | `[-0.0996028, 0.0996028]` | 0 | 0 | pass |
| `asymmetric` | 8 | `[1,1,1,1]` | 4 | 8 | `[-0.0996028, 0.0996028]` | `[-0.0996028, 0.0996028]` | 0 | 0 | pass |
| `uuv6` | 6 | `[1,1,1,1]` | 4 | 8 | `[-0.0996028, 0.0996028]` | `[-0.3088460, 0.3088460]` | 0 | 0 | pass |
| `uuv6_angled` | 6 | `[1,1,1,1]` | 4 | 8 | `[-0.0996028, 0.0996028]` | `[-0.3136106, 0.3136106]` | 0 | 0 | pass |
| `uuv4` | 4 | `[1,1,0,1]` | 3 | 8 | `[-0.0536650, 0.0536649]` | `[-0.0580533, 0.0580533]` | 0 | 0 | pass |
| `uuv4_angled` | 4 | `[1,1,0,1]` | 3 | 8 | `[-0.0536650, 0.0536649]` | `[-0.0580533, 0.0580533]` | 0 | 0 | pass |

所有 8 个 runner exit、8 个 `tee` exit 和 8 个 semantic artifact gate 文件均为 `0`。`base` 完成 64 steps，其余七个构型各完成 8 steps；总 non-finite count 与 dimension-mismatch count 均为 0。没有 `heavy_duty` 行。

## Artifact 与严格验证

- Canonical artifact：`source/results/koopman_phase6/qualification.json`
- Server/local SHA-256：`6cb83fcb63fc7bd33ffcfa678d09f3e128fcf6f6380ee3b948541814421a1a92`
- Server validator：`source/results/koopman_phase6/validator.json`
- Pullback validator：`source/results/koopman_phase6/pullback_validator.json`
- Eight row artifacts：`source/results/koopman_phase6/rows/*.json`
- Per-run logs：`source/results/koopman_phase6/logs/*.log`
- Native/log/semantic gate codes：`exit_codes/`, `log_exit_codes/`, `artifact_gate_codes/`

严格验证结果：

```json
{
  "actual_versions": {"isaac_lab": "2.2.1", "isaac_sim": "5.0"},
  "configuration_count": 8,
  "evidence_level": "server_isaac_smoke",
  "qualification_gate": "server_pass",
  "warnings": []
}
```

## QUAL-01..08 证据索引

| Requirement | Result | Concrete evidence |
|---|---|---|
| QUAL-01 | PASS | Received snapshot commit `7ba2499`; canonical package provenance in `easyuuv_nc/SNAPSHOT_PROVENANCE.md`; tested source commit `e24f76a...` separately recorded in artifact. |
| QUAL-02 | PASS | `easyuuv_nc/embodiments.py`, catalog CLI/tests and exact eight names in `qualification.json`; no public `heavy_duty`. |
| QUAL-03 | PASS | `pyproject.toml`, package probes, server offline editable-install log and `gym_tasks.log` proving four registered task IDs and resolved USD. |
| QUAL-04 | PASS | Eight-row table above, per-row artifacts, TAM/rank/mask contract tests; `uuv4*` is rank 3 with yaw mask 0. |
| QUAL-05 | PASS | Real server row/log per configuration: base 64 steps and seven 8-step smokes; every create/reset/step status is pass. |
| QUAL-06 | PASS | Actual telemetry has zero nonfinite/dimension mismatches and remains within declared bounds; strict mutation tests reject NaN/Inf, inversions, wrong dimensions and out-of-range values. |
| QUAL-07 | PASS | Fresh full local suite and compile/diff gates in `06-VERIFICATION.md`; frozen v1 planning/model/MPC diff is empty. |
| QUAL-08 | PASS | Runbook, 64-file machine-readable evidence package, `06-04-SUMMARY.md`, this evidence record and `06-VERIFICATION.md`. |

## Locked Decision Disposition

- D-02/D-03/D-14: snapshot, v1 evidence, v2 integration, server evidence and planning remain separate commits; v1 model/MPC semantics remain untouched.
- D-04/D-08: exact eight public configurations and topology facts are enforced; `heavy_duty` remains internal.
- D-06: `uuv4*` yaw is explicitly masked and not misreported as controllable.
- D-10: finite, bounds and motor-dimension checks use actual telemetry and fail closed.
- D-11/D-12: only server processes emitted `server_isaac_smoke`; local catalog artifacts cannot substitute for it; actual runtime versions are recorded.
- D-13: strict validator plus independent pullback hash is the promotion gate.

## Warnings and preserved failures

Isaac logs contain Warp CUDA driver-entry warnings (`cuDeviceGetUuid`, error 36) and benign DirectRLEnv/render/Fabric warnings. The run still used the server RTX 4090 through Vulkan/PhysX, and all required row telemetry and semantic gates passed. These warnings are retained in the raw logs and are not interpreted as Koopman performance evidence.

Earlier failed/superseded attempts remain preserved outside the canonical directory, locally under ignored `.pytest-tmp/phase6-server-*` paths and on the server under `/root/EASYkoopman-phase6-v2-failed-*` / `/root/EASYkoopman-phase6-v2-success-fb70281`. They were not deleted or merged into the final artifact.
