# Phase 8 Pattern Map

**Mapped:** 2026-08-13
**Purpose:** identify the closest repository analog for each Phase 8 artifact while naming the semantics that must not be copied

## New/Modified File Map

| Phase 8 file | Closest analog | Reuse | Do not copy |
|---|---|---|---|
| `koopman/evidence_v2.py` | `koopman/schema_v2.py`, `workflows/merge_koopman_v2_evidence.py` | exact fields, bounded JSON, duplicate-key rejection, SHA-256, atomic write, external file revalidation | do not extend the transition evidence enum or trust self-asserted qualification |
| `koopman/protocol_v2.py` | `workflows/easyuuv_v2_qualification_artifact.py`, `koopman/schema_v2.py` | immutable version constants, exact configuration set, reason-coded validators, canonical JSON | do not pre-fill hashes for files that have not been collected |
| `workflows/collect_koopman_v2_identification.py` | `workflows/collect_koopman_v2_smoke.py` | AppLauncher order, Bridge use, confined paths, strict logger, clean source/runtime provenance | do not retain exact-three choices, 8-step minimum, one-episode process semantics or smoke aggregate label |
| `workflows/audit_koopman_v2_pilot.py` | `workflows/validate_easyuuv_v2_qualification.py`, `workflows/validate_koopman_v2.py` | exact-set aggregation, finite/topology/semantic gates, deterministic CLI | do not import or call model fitting/evaluation modules |
| `koopman/collection_v2.py` | `koopman/dataset_v2.py` | immutable arrays/mappings, strict per-episode loader, named diagnostics | do not concatenate away episode/configuration/role boundaries |
| `koopman/splits_v2.py` | `koopman/splits.py` | explicit manifest dataclass and read/write validation style | do not use path-only overlap checks, row randomization or mutable roles |
| `koopman/platform_features_v2.py` | `koopman/schema_v2.py`, `easyuuv_nc/embodiments.py` | exact platform fields, topology validation, lazy canonical facts | do not encode configuration names/one-hot or fit normalizers across held-out configs |
| `koopman/model_v2.py` | `koopman/model.py`, `koopman/edmd.py` | ridge solve/pinv fallback, explicit dimensions, serialization/version checks, normalizer artifacts | do not accept reference/PWM defaults, mutate v1 constants or silently clip invalid data |
| `koopman/baselines_v2.py` | `koopman/baselines.py` | persistence and ridge linear structure | do not accept `reference_5` or `PWM_8` in v2 primary baselines |
| `koopman/metrics_v2.py` | `koopman/evaluation.py` | one-step/rollout organization and finite failure reporting | do not use component quaternion RMSE as angle, cross episodes, teacher-force rollout or hard-code v1 thresholds |
| `koopman/loco_v2.py` | `koopman/sweep.py`, `koopman/splits.py` | deterministic candidate iteration and machine-readable results | do not use one global concatenated split, outer-test retuning or backend×regime expansion |
| `koopman/selection_v2.py` | `koopman/selection.py`, `workflows/select_phase5_4_candidate.py` | explicit negative outcome, limitations and model-path removal | do not rank on row-weighted score, promote expert or let test metrics choose final refit hyperparameters |
| `workflows/run_koopman_v2_loco.py` | `workflows/sweep_koopman_models.py` | CLI orchestration and exact artifact output | do not call v1 dataset/model/evaluation/selection functions |
| `workflows/validate_phase8_evidence.py` | `workflows/validate_koopman_v2.py` | deterministic `--json`, nonzero failure and byte/hash revalidation | do not infer qualification from filename or envelope claim alone |
| `scripts/phase8_*_local_preflight.ps1` | `scripts/phase7_local_preflight.ps1` | full gates, native Git stderr handling, clean HEAD/canonical absence | do not share pilot/main canonical roots or permit concurrent dirty work |
| `scripts/phase8_*_prepare_bundle.ps1` | `scripts/phase7_prepare_bundle.ps1` | preflight invocation, complete bundle, commit sidecar | do not bundle a different HEAD from the tested one |
| `scripts/phase8_*_server_bootstrap.sh` | `scripts/phase7_server_bootstrap.sh` | isolated target, exact HEAD, clean checkout, fail-closed shell | do not reuse Phase 7 server/result directories |
| `scripts/phase8_*_server_run.sh` | `scripts/phase7_server_smoke.sh` | Isaac wrapper, offline install, native/tee/semantic/log status, exact inventory | do not omit an episode after failure or merge partial evidence |
| `scripts/phase8_*_pullback.ps1` | `scripts/phase7_pullback.ps1` | fresh staging, local HEAD gate, SCP/hash/runtime/validator before promotion | do not overwrite existing canonical evidence or validate with dirty/newer code |
| `docs/phase8_koopman_identification_runbook.md` | `docs/phase7_koopman_v2_runbook.md` | exact local/bundle/server/pullback/failure commands and agent/user responsibility | do not claim model or MPC success from collection alone |

## Core Implementation Patterns

### 1. External qualification envelope

Keep two meanings separate:

```text
transition.episode_provenance.evidence_level = server_isaac_smoke
envelope.artifact_origin_level               = server_isaac_smoke
envelope.qualification_level                 = server_isaac_identification_pilot | ...
```

The transition tells where a row came from. The envelope tells what a validated collection/evaluation is qualified to support. Only the external validator writes/accepts the latter.

### 2. Pre-collection intent, post-collection fact

Use distinct schemas:

```text
role_assignment_protocol: expected IDs, roles, seeds, scenarios, lengths
dataset_inventory: actual paths, bytes, hashes, counts, invariants
split_manifest: references immutable inventory entries and roles
```

Do not overload one manifest with desired and actual state.

### 3. Sealed held-out access

Every loader called by fold selection takes an explicit `allowed_configurations` set and records the opened episode hashes. A fold decision validator recomputes:

```text
opened configurations == exact seven sources
heldout configuration  not in opened hashes/statistics/features
decision timestamp/hash precedes heldout test open
```

Path naming alone is not sufficient evidence.

### 4. One backend, several regimes

Use one `ControlledEDMDV2` serialization/runtime with a design builder configured by:

```text
observable_schema: identity_v1 | auv_kinematic_v1
conditioning: none | platform_affine
training_scope: per_configuration | pooled
```

`expert` is not a new model class; it is per-configuration training in a protected evaluation namespace.

### 5. Source-fold normalizers

Normalizers are artifacts, not implicit arrays. Each records:

- fold ID and exact seven source configurations;
- source episode hashes;
- feature schema/version;
- mean/scale values and SHA-256;
- zero-scale handling rule.

The conditional model must reject a normalizer whose source set contains the held-out configuration.

### 6. Episode-safe rollout

Evaluation iterates explicit episode objects:

```text
for episode in heldout_test_episodes:
    state = episode.X[0]
    for k in horizon:
        state = model.predict_next(state, episode.U[k], platform)
```

It never slices a globally concatenated array across an episode boundary.

### 7. Atomic negative outcome

`no_selection` is a complete artifact with hashes, failed gates, limitations and disallowed claims. It contains no `model_path`, `selected_model_path`, fallback candidate or stale symlink.

## Tests Closest to Reuse

| New test focus | Closest test |
|---|---|
| exact/mutation protocol and envelope | `tests/test_koopman_schema_v2.py`, `tests/test_easyuuv_v2_qualification.py` |
| runner and operational scripts | `tests/test_phase7_server_evidence_contract.py`, `tests/test_easyuuv_v2_qualification_runner.py` |
| immutable multi-episode collection | `tests/test_koopman_dataset_v2.py` |
| model fitting/serialization | `tests/test_koopman_edmd.py`, `tests/test_lifted_edmd.py`, `tests/test_koopman_runtime.py` |
| baselines | `tests/test_koopman_baselines.py` |
| split/leakage | `tests/test_koopman_splits.py` plus new dynamic opened-file instrumentation |
| rollout and selection | `tests/test_koopman_evaluation.py`, `tests/test_koopman_selection.py` |
| no-selection/report boundary | `tests/test_phase54_final_selection.py` and Phase 7 claim-boundary tests |

## No Exact Existing Analog

The following require new design rather than copy/edit:

1. nested exact-eight configuration LOCO with episode roles;
2. fold-local physical feature selection and parameter-affine interactions;
3. external Phase 8 qualification envelope over frozen Phase 7 transitions;
4. SO(3)-correct open-loop episode evaluation with quaternion projection diagnostics;
5. expert upper-bound isolation from primary selection;
6. final refit inner selection using all fit+validation but no test episodes.

These are the highest-risk review targets and should have behavior tests before implementation.

## Recommended Plan Boundaries

- `08-01`: evidence/protocol/pilot runner and real pilot checkpoint.
- `08-02`: collection/inventory/split/platform features and leakage gates.
- `08-03`: model/baselines/metrics/LOCO decision building.
- `08-04`: approved main protocol and real dataset checkpoint.
- `08-05`: complete nested evaluation, selection/no-selection and final refit.

Do not combine a real server checkpoint with another plan that is modifying tracked files in parallel; the clean tested HEAD is part of the evidence.

---

*Pattern map status: complete*
