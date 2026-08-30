---
phase: 08-multi-configuration-koopman-identification-and-ood-gate
verified: 2026-08-30T03:03:33Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
terminal_verdict: PASS_VALID_FROZEN_NO_SELECTION
selection_status: no_selection
human_verification: []
---

# Phase 8: Multi-Configuration Koopman Identification and OOD Gate Verification

**Phase Goal:** 在 configuration/episode 隔离的真实 exact-eight 数据上，以同一
controlled-EDMD v2 backend 和冻结分析协议完成八折 LOCO 预测比较，并只允许
pooled/conditional 通过冻结硬门；否则输出可审计且无模型路径的 `no_selection`。

**Verified:** 2026-08-30T03:03:33Z  
**Status:** `passed`  
**Re-verification:** No — initial independent verification  
**Verdict:** `PASS_VALID_FROZEN_NO_SELECTION`

本报告从 KID-01..05 和 ROADMAP success criteria 反向检查真实代码、canonical
evidence 和验证命令。没有使用 SUMMARY 作为实现证据，没有 SSH、重采集、改动
dataset/evaluation/selection bytes，也没有进入 Phase 9。

## Terminal Interpretation

Phase 8 的研究目标已完成，但结果是合法的负结果：八折证据链有效，冻结门判定
当前两个 eligible families 均不可晋升，因此 terminal artifact 是
`no_selection`，不是“实验失败”或“证据缺失”。

- `pooled_koopman_v2` 与 `simple_linear_v2` 的六个 full-rollout primary metrics
  完全相同；对 simple-linear 的 bootstrap lower bound 全为 `0.0`，且六项 1%
  improvement 均未通过。对 persistence 也只有 angular-velocity RMSE 改善。
- `conditional_koopman_v2` 在 `heavy_moderate`、`uuv4`、`uuv4_angled` 上出现
  reason-coded `quaternion_projection_limit`，所以完整 family fail closed。
- `selection_result.json` 的 `selected_family=null`、`selected_model_path=null`，
  reason codes 为 `baseline_improvement_failed` 和 `role_failed`。
- 这证明的是“冻结候选没有通过跨构型预测晋升门”，并不证明 Koopman-MPC、
  closed-loop、环境迁移、Agentic、Sim2Real 或硬件有效性。

## Goal Achievement

### KID Requirements

| Requirement | Status | Goal-backward evidence |
|---|---|---|
| `KID-01` configuration/episode isolation | **PASS** | Pilot envelope live-validates with 51 references and `collection_chain_ready`; main envelope live-validates with 293 references. Inventory has 96 unique episode IDs and 96 unique transition hashes: each of 8 configurations has 6 fit + 3 validation + 3 test episodes, each configuration totals 6,144 transitions. The 8 split folds each contain exactly 7 source configurations, 63 source fit+validation episodes, 3 held-out test episodes and 9 held-out expert fit+validation episodes; all sets match inventory bytes. |
| `KID-02` comparable six-role matrix | **PASS** | `evaluation_summary.json` has exactly 8 folds and exactly the 6 required roles in every fold. Persistence, simple-linear, source-per-configuration, pooled and expert succeed in all folds; conditional failures remain present and reason-coded. Only pooled/conditional carry `selection_eligible=true`; expert and all diagnostics are false. Primary inputs are `state_11 + virtual_control_4`; conditional adds only `platform_physical_descriptor`; reference diagnostic is frozen disabled/non-promoting. |
| `KID-03` held-out one/multi/full evaluation | **PASS** | Every successful role artifact reports `one_step`, `5`, `20`, `60`, `full`; failed conditional horizons retain null metrics plus reason/counters rather than being dropped. Aggregate artifacts include per-configuration, equal-configuration macro, worst-configuration and diagnostic-only row-weighted results. Episode-local recursive rollout behavior is implemented in `koopman/metrics_v2.py` and covered by the passing targeted suite. |
| `KID-04` quaternion-correct SO(3) | **PASS** | Official metrics are `so3_geodesic_{mean,rmse,max}_radians`. `so3_geodesic_radians()` normalizes, uses `abs(dot)`, clamps to `[0,1]` and calculates `2*acos`; zero/non-finite/projection-limit paths fail closed. Tests cover `q/-q`, 0/90/180 degrees, clamp, invalid quaternion, projection limit, and forbidden component-RMSE aliases. |
| `KID-05` provenance-checked terminal decision | **PASS** | Evaluation and selection envelopes live-validate with 106 and 1 referenced files respectively, both `warnings=[]`. The selector recomputes exact folds/roles/freezes/metrics from referenced leaf evidence, accepts only pooled/conditional and emits a single atomic `no_selection` root. The result has no selected model/load path. The negative outcome follows frozen gates rather than missing evidence. |

**Score:** 5/5 KID requirements verified.

### ROADMAP Success Criteria

| # | Criterion | Status | Evidence |
|---:|---|---|---|
| 1 | Pilot is collection-health-only | **VERIFIED** | `pilot_health_decision.json` says `collection_chain_ready`, 8 configurations, 16 episodes, 2,048 transitions, `warnings=[]`. Canonical pilot root contains only 16 JSONL, 16 manifests, 16 logs and 4 policy/inventory/decision/envelope JSON files; no model/selection result is promoted from pilot. |
| 2 | Whole configuration/episode LOCO; seven-source decisions only | **VERIFIED** | Exact inventory/split audit above; every evaluation fold records 63 source hashes, excludes its held-out configuration, seals the decision with `test_open_count_at_seal=0`, then freezes with candidate/model/test/mutation counters all zero. |
| 3 | Same policy and six roles; pooled/conditional only eligible | **VERIFIED** | Role/input/eligibility audit is exact across all 8 folds; role protocol SHA-256 is shared everywhere. |
| 4 | one-step, 5/20/60/full, SO(3), per-config/macro/worst | **VERIFIED** | Leaf metrics and `aggregate_metrics.json` contain the exact requested horizons and aggregation namespaces; strict evaluation validator recomputed all 106 referenced files. |
| 5 | Provenance-bound selection or pathless no-selection | **VERIFIED** | Canonical selection qualification is `no_selection`; selection result hash is bound and no model path exists. Final refit is correctly not invoked because no family was selected. |

## Frozen Provenance

| Artifact | Verified SHA-256 |
|---|---|
| Role protocol | `499b79089a4bfb0769ce6a902ad676f09e9c64190069a0bf5b51cd76f1d6cf26` |
| Authoritative analysis policy | `0d95edaf3d2511a7b0ca0440698c5e22fff51881076422ecef1712fe23c1b401` |
| Pilot envelope | `6052570ebf24f14d1ef39b057bd2aee8796ad7d5b7e5ffd70622778281b82155` |
| Pilot health decision | `a26c05f597768c1b2eac375d89e771a84cfc6100d362cd599b27f02971279a3d` |
| Dataset inventory file | `cfac12d15f062c9f330d2acf6381d341769e989dc35cd00ae29759a6f94f395b` |
| LOCO split file | `0e245dfa238df252145e99751be8dcc9ed6a1ef340f382428f6fd3c86db5d8ed` |
| Dataset envelope | `46d02531457123f2a1dfda3b16159b359a6caff2d90b14283094a349647a1b04` |
| Evaluation summary | `0e19b4cfbbd2db80496834c6cf066f5df220c60305fd0b4a1a3d1963a5651ff4` |
| Evaluation envelope | `5c776002d4d849f8504badbfe00fe564a82b7107a05992b26469a8a2df1f4181` |
| Selection result | `a7585fb8acdcb3f0b3a55cb94ce7413070aa4ceea5f060d824aa5c12ce3e23a9` |
| Selection envelope | `5e30db3ce2889eafa8338a4537abaa2352974b106db3ed8e7781b40d88b3eba4` |

Source commits embedded in the canonical chain resolve locally as commits:

- main dataset: `a7e819848ffc1c621fbeeff971063f1cdbeac0b3`
- evaluation: `c7ee70f46497c896aa3ae8f5ace94b7873e0116b`
- selector: `983a6bb4efcce87e04755aae10da8a31f6b34785`

The main-data evidence records the earlier collection-time analysis-policy hash
`4083...`; the authoritative policy was then deliberately revised and reapproved as
`0d95...` before any fold decision/test access. The dataset envelope is bound to the
unchanged role protocol; every fold decision, evaluation summary and terminal selector
is bound to `0d95...`. This is the approved D-23 sequence, not post-test retuning.

## Required Artifacts

| Artifact | Exists | Substantive | Wired | Status |
|---|---:|---:|---:|---|
| `source/results/koopman_phase8_pilot/pilot_envelope.json` | yes | 51 referenced files, valid health decision | input prerequisite for main-stage evidence boundary | **VERIFIED** |
| `source/results/koopman_phase8_dataset/{dataset_inventory,loco_split_manifest,dataset_envelope}.json` | yes | 96 episodes / 8 exact folds / strict envelope | loaded and checked by evaluator before any fit | **VERIFIED** |
| `koopman/loco_v2.py` | yes, 930 lines | immutable fold decision/freeze/test-token state machine | imported and used by `koopman/evaluation_v2.py` | **VERIFIED** |
| `koopman/metrics_v2.py` | yes, 803 lines | episode-local rollout, failure counters, SO(3), aggregate logic | used by evaluator and selector schema checks | **VERIFIED** |
| `koopman/selection_v2.py` | yes, 526 lines | strict exact-eight selector and pathless negative result | called by `workflows/select_koopman_v2.py` | **VERIFIED** |
| `source/results/koopman_phase8_evaluation/` | yes | 106 immutable referenced leaf files, 8 fold decisions and result matrix | sole scientific input to selector | **VERIFIED** |
| `source/results/koopman_phase8_selection/` | yes | one result + one terminal envelope | evaluation envelope SHA-256 is bound in runtime/result | **VERIFIED** |
| `08-OOD-EVALUATION.md` | yes | exact fold/role/horizon metrics, gates and claim boundary | reports the canonical hashes/result without becoming selector input | **VERIFIED** |

## Key Link Verification

| From | To | Mechanism | Status |
|---|---|---|---|
| Canonical server dataset | `run_phase8_loco_evaluation_v2()` | `_validate_dataset_bindings()` validates dataset qualification, role protocol, inventory and split before staging/fitting | **WIRED** |
| Fold source views | held-out test bytes | `FoldExecutionV2.seal_decision()` reads 7-source fit/validation; `FrozenPrimaryStateV2` + `PrimaryTestAccessTokenV2` are required before `open_primary_test()` | **WIRED** |
| Evaluator | SO(3)/rollout aggregates | evaluator calls episode-local metric artifacts and writes per-role leaves plus equal-macro/worst aggregates | **WIRED** |
| `workflows/select_koopman_v2.py` | `koopman/selection_v2.py` | calls `select_phase8_candidate()` on the validated evaluation envelope; caller cannot supply metrics, eligibility or a model path | **WIRED** |
| Selection envelope | Evaluation envelope | `runtime_provenance.evaluation_envelope_sha256` and `inventory_sha256` both equal `5c7760...f4181`; selection result repeats the same evaluation hash | **WIRED** |
| Negative selector branch | terminal artifact | staging is validated as `no_selection` and atomically renamed; `Phase8SelectionResultV2` forbids family/model path on this status | **WIRED** |

## Data-Flow Trace

| Stage | Real data source | Verified flow |
|---|---|---|
| Collection | 96 server-origin strict JSONL episodes | Dataset envelope revalidated all 293 references and role/hash bindings. |
| Split | Inventory entries | 8 folds each map exact source fit+validation, held-out test, and isolated expert fit+validation sets. |
| Source decision | 63 source episode hashes/fold | Candidate, normalization and platform descriptors are selected from the seven source configurations and sealed in `fold_protocol_decision.json`. |
| Freeze/test | Frozen candidate + four primary model identities | All 8 folds have decision/test-open/revision/mutation counters at zero before held-out access; a bound token opens exactly 3 held-out test episodes. |
| Evaluation | Held-out leaf predictions | Six roles emit complete horizons or reason-coded failures; aggregate derives per-config/equal-macro/worst results. |
| Terminal gate | Immutable evaluation summary/envelope | Selector recomputes gates and publishes only `no_selection`; no test metric modifies any candidate or threshold. |

## Behavioral Checks Re-run

| Check | Result | Status |
|---|---|---|
| `validate_phase8_evidence.py --qualification server_isaac_identification_pilot` | 51 references, `phase8_external_evidence_valid`, `warnings=[]` | **PASS** |
| `validate_phase8_evidence.py --qualification server_isaac_identification_dataset` | 293 references, valid, `warnings=[]` | **PASS** |
| `validate_phase8_evidence.py --qualification offline_koopman_ood_evaluation` | 106 references, valid, `warnings=[]` | **PASS** |
| `validate_phase8_evidence.py --qualification no_selection` | 1 reference, valid, `warnings=[]` | **PASS** |
| `pytest test_koopman_selection_v2.py test_phase8_ood_evaluation_contract.py test_koopman_loco_v2.py test_koopman_metrics_v2.py` | `64 passed in 5.08s` | **PASS** |
| Structural JSON audit | 96 unique episodes; exact 8×(6/3/3); exact 8 folds; exact roles; all freeze counters zero | **PASS** |

## Adversarial/Anti-Pattern Review

| Finding | Classification | Disposition |
|---|---|---|
| `selection_v2._validate_role()` returns `{}` for a failed role | Info, not a stub | This is the deliberate fail-closed sentinel consumed by `_family_diagnostics()`; the failed role remains present in leaf evidence with its reason. |
| `tests/test_phase8_ood_evaluation_contract.py` is narrower than its filename suggests | Warning, non-blocking | It tests fixed rollout policy, physical descriptor binding and family pairing, not a full real-data rerun. The canonical evaluator execution plus strict leaf-envelope revalidation and LOCO/metric/selector mutation tests provide the actual evidence used for this verdict. |
| `publish_terminal_result()` rejects a hypothetical passing selection until operational final refit is implemented | Warning, non-blocking for this frozen experiment | The selected branch was not reached: both families failed the frozen gate. This is a safe fail-closed limitation, not a way to turn missing evidence into `no_selection`. A future experiment that produces a passing family must implement and verify the test-free final-refit publication path before exposing a Phase 9 model. |
| TODO/FIXME/placeholder scan | None blocking | No placeholder implementation found in the inspected Phase 8 selector/evaluator/metric pipeline. |

## Human Verification

None. The Phase 8 outcome is a deterministic offline evidence/selection pipeline with
machine-readable artifacts; no visual, real-time or external-service behavior is part
of this closeout. Real Isaac collection provenance is carried by the already pulled
and strictly revalidated server envelope; this verification did not repeat SSH work.

## Gaps and Claim Boundary

No unresolved Phase 8 blocker was found. `KID-01`..`KID-05` are satisfied by a valid
negative outcome, not by claiming a transferable model exists.

There is no Phase 9 handoff model. Phase 9 Koopman-MPC execution therefore must not
start from this artifact. A later explicitly versioned identification experiment may
address the candidate/model limitation, but it must not rewrite or retune the frozen
Phase 8 result.

No protocol deviation.

---

_Verifier: independent gsd-verifier agent_  
_Terminal verdict: `PASS_VALID_FROZEN_NO_SELECTION`_
