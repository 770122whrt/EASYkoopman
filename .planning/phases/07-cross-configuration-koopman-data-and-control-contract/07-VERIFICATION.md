---
phase: 07-cross-configuration-koopman-data-and-control-contract
verified: 2026-08-12
status: passed
score: 5/5 requirements verified
tested_source_commit: a36689abeee00c98eb480ebcdf02e147edcaa6e3
evidence_commit: 1c0a6cabe82d4153efd9a8e60485f2423ddd4f41
artifact_sha256: 2f07a6835f0b32fe0277fd819394580f261b6028dc3d07520e70b124e0758463
server_runtime_executed: true
---

# Phase 7 Goal-Backward Verification

## Verdict

**PASS.** Phase 7 的目标已经实现：schema v2、原子 Koopman Bridge、4D topology-independent control、diagnostic-only padded PWM、实际 post-actuator wrench、oracle/estimated context 分离、DatasetV2 和显式 v1 compatibility boundary 均已建立，并由 `base`、`uuv6`、`uuv4` 三类真实 Isaac 拓扑的连续服务器证据验证。

这是 goal-backward verification，不是“任务做完即通过”。验证从 CONT-01..05 和 Phase 7 的非目标倒推实现、测试与服务器 artifact。结论只覆盖数据/控制合同接入；不覆盖 Koopman 模型效果、OOD transfer 或 MPC 闭环性能。

## Requirement Verification

| Requirement | Status | Why it passes |
|---|---|---|
| CONT-01 | PASS | 唯一 schema ID、required fields、shape/range/finiteness、context/provenance、episode continuity 均由严格 validator 覆盖；服务器 24 行和 3 个 manifest 全部通过。 |
| CONT-02 | PASS | Bridge 从真实同一步 telemetry 读取 post-mask/pre-TAM `virtual_control_4=[roll,pitch,yaw,depth]`；DatasetV2 `.U` 精确为 4D；8/6/4 拓扑共享该语义，uuv4 两个非零 raw-yaw probe 的 virtual yaw 为零。这里验证的是 v2 consumer contract；实际 MPC 迁移仍归 Phase 9。 |
| CONT-03 | PASS | `motor_pwm_padded_8` 和 `thruster_mask_8` 只通过 `ActuatorDiagnostics` 暴露，4/6 路 padding 精确为零，默认 DatasetV2 没有 PWM/action/control alias。 |
| CONT-04 | PASS | schema/API 分离 oracle 与 estimated context；24 行 oracle 均为 same-step runtime truth，estimated 均显式 unavailable，mutation tests 拒绝 oracle-copy-as-estimate 和缺失 provenance。 |
| CONT-05 | PASS | canonical v1 fixture 只能经 `V1CompatibilityView` 读取，并明确 false v2 eligibility/缺失字段；raw v1 和 adapter view 都不能通过 strict v2 promotion，冻结 v1 loader/model/MPC 回归通过。 |

## Acceptance Criteria Verification

| Criterion | Status | Evidence |
|---|---|---|
| Strict schema semantics | PASS | `koopman/schema_v2.py`, `workflows/validate_koopman_v2.py`, schema mutation suites and real server aggregate. |
| Exact-eight local topology contract | PASS | Phase 6 catalog/TAM remains canonical; Phase 7 tests validate all eight without copying a second catalog. |
| `uuv4*` yaw mask before TAM | PASS | Local `uuv4`/`uuv4_angled` tests plus real uuv4 step 2/6 `±0.2 -> 0.0`. |
| DatasetV2 default control width 4 | PASS | Immutable `KoopmanDatasetV2.U`; three topology fixtures and real episodes. |
| Actual thruster-only wrench | PASS | Runtime cache after PWM dynamics/efficiency and before environmental forces; 22/24 rows nonzero and all 24 carry a valid 6D field. |
| Oracle/estimated separation | PASS | Independent typed namespaces/provenance in all real rows; estimated unavailable accepted but never treated as valid estimate. |
| Explicit v1 compatibility | PASS | `koopman/v1_compatibility.py` delegates to v1 loader and cannot promote/write/infer v2 facts. |
| v1/Phase 6 isolation | PASS | Protected diff gate, frozen v1 model/MPC width 8 and unchanged Phase 6 canonical evidence. |
| Real exact-three server evidence | PASS | 3×8 contiguous transitions, native/tee/semantic pass, exact source/runtime/hash agreement. |
| Runbook/evidence/summary/verification | PASS | Runbook, aggregate package, `07-SERVER-EVIDENCE.md`, `07-04-SUMMARY.md` and this report exist. |

## Fresh Closeout Verification

以下命令在最终 `a36689a` 服务器证据已回传、inventory completion-state 复验已补齐且 planning closure 已更新后重新执行；没有沿用 pre-transfer 或已撤销 `b16fb89` 包的旧结果。

| Gate | Fresh result |
|---|---|
| Phase 7 targeted schema/Bridge/Dataset/compat/server-contract suite | `224 passed, 1 skipped in 51.69s` |
| Full collect-only | `562 tests collected in 8.07s` |
| Full repository pytest | `561 passed, 1 skipped in 80.81s` |
| `compileall` over `koopman`, `easyuuv_nc`, `workflows`, `scripts`, `tests` | exit 0 |
| `.venv` pip check | `No broken requirements found.` |
| Phase 7 Bash / PowerShell native parse | 2 Bash and 3 PowerShell scripts pass |
| Promoted evidence inventory | `sha256_inventory_valid`, 44 server-authored files; only explicit local pullback verdict excluded |
| Strict aggregate validator | exact `base,uuv6,uuv4`, source `a36689a...`, warnings `[]` |
| Aggregate SHA-256 | exact `2f07a6835f0b32fe0277fd819394580f261b6028dc3d07520e70b124e0758463` |
| Frozen v1 and Phase 6 protected diffs | empty |
| `git diff --check` and planning contract grep | pass |

The one skip is the Windows host's unavailable symlink-creation privilege in that test context. Production symlink/path confinement remains fail closed and its non-privileged rejection paths pass.

## Goal-Level Evidence

### 1. 数据链真实接通

The exercised chain was:

```text
Isaac Sim env.step
  -> EasyUUV same-step telemetry snapshot
  -> KoopmanBridgeV2
  -> strict schema-v2 transition
  -> atomic JSONL + manifest
  -> exact-three aggregate
  -> server validator
  -> hash-bound staged pullback
  -> local validator
```

This is stronger than proving that USDs load: the rows contain pre/post state, reference, raw and masked control, executed actuator diagnostics, actual wrench and runtime context from the same step token.

### 2. 三类 actuator topology 使用同一 learned-control meaning

- `base`: 8 thrusters, mask `[1,1,1,1]`, 8 contiguous rows.
- `uuv6`: 6 thrusters, `pinv`, mask `[1,1,1,1]`, 8 contiguous rows.
- `uuv4`: 4 thrusters, `wls`, mask `[1,1,0,1]`, 8 contiguous rows.
- `uuv4` raw yaw probes at steps 2 and 6 are `+0.2` and `-0.2`; both virtual yaw values are `0.0`.

Thus topology changes actuator diagnostics/allocation but not the model-facing control coordinate system.

### 3. 证据不能被本地 fixture 或旧结果替换

- Local fixtures are labelled `local_contract`; aggregate server validation requires `server_isaac_smoke`.
- Bundle, sidecar and server checkout bind source `a36689a...`.
- Runtime provenance binds Isaac Sim/Lab versions and the fixed IsaacLab repo state/patch.
- Every topology has independent native, tee and semantic gates plus episode/log hashes.
- Pullback refuses SCP/hash/source/runtime/validator drift and refuses replacing an existing canonical directory.
- Server and local aggregate SHA-256 agree at `2f07a683...8463`; a separate exact inventory verifies all 44 server-authored files and excludes its own mutable output by construction.

## Threat Model Closure

| Threat | Disposition |
|---|---|
| Mock/local evidence relabelled as server | Closed by server-only provenance, actual SSH execution, independent logs/statuses and staged pullback. |
| Missing/duplicate/extra topology | Closed by exact-three merger and validator. |
| Raw action or desired wrench substituted for runtime truth | Closed by distinct fields/capture points and same-step Bridge token. |
| uuv4 uncontrollable yaw hidden after allocation | Closed by explicit pre-TAM mask and real nonzero-yaw probes. |
| Padded PWM silently used as learned control | Closed by DatasetV2 API separation and alias rejection tests. |
| Source/runtime/version drift | Closed by bundle sidecar plus IsaacLab VERSION/repo/patch binding. |
| Partial process/log success accepted | Closed by native/tee/semantic gates and exact hashes. |
| v1 or Phase 6 evidence overwritten | Closed by isolated paths, protected diffs and independent commits. |

No HIGH Phase 7 threat remains open.

## Preserved Failures and Warnings

Five real-server/final-audit failures were preserved and used to harden the chain: missing conda activation, result-root provenance rejection/SystemExit masking, Isaac Sim version-string mismatch, nested-vs-flat merger layout and a self-referential file inventory. The initially promoted `b16fb89` package was explicitly revoked after the inventory defect was discovered, archived outside canonical, and replaced only after a fresh server run from tested source `a36689a`. No prior transition was reused in the successful aggregate.

Raw Isaac logs retain Warp CUDA driver-entry and Kit/Fabric/deprecation warnings. All required Vulkan/PhysX starts, transitions and semantic gates passed. These warnings are diagnostic facts, not performance evidence.

The pulled IsaacLab patch intentionally retains its original blank lines so its recorded SHA-256 remains reproducible; this raw provenance file is exempt from source-format cleanup.

## Claim Boundary and Phase Transition

Phase 7 may close and Phase 8 planning is unblocked. Phase 8 must use configuration/episode-level splits and held-out-configuration prediction gates to determine whether a shared or conditional Koopman model is actually useful. It is valid for Phase 8 to return `no_selection`.

Phase 7 does **not** establish any of the following:

- multi-configuration Koopman prediction accuracy;
- held-out/OOD transfer quality;
- 4D Koopman-MPC closed-loop tracking or stability;
- environment adaptation benefit;
- Agent Supervisor effectiveness;
- hardware or Sim2Real validity.

Those claims remain assigned to Phase 8–12 and cannot be inferred from this verification.
