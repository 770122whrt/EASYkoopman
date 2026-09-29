# Phase 8 Research: Multi-Configuration Koopman Identification and OOD Gate

**Researched:** 2026-08-13
**Status:** implementation-ready after revised SPEC audit
**Scope:** exact-eight collection health, main identification data, leak-free controlled-EDMD v2, LOCO evaluation and fail-closed selection

## Executive Summary

Phase 8 should not begin by training “many kinds of Koopman.” The smallest defensible implementation is:

1. preserve Phase 7 schema-v2 rows and prove an exact-eight collection-health pilot;
2. pre-register and collect a separate main episode inventory;
3. implement one additive controlled-EDMD v2 backend with a small observable candidate set;
4. run that backend under per-configuration, pooled and physical-context conditional training regimes, alongside persistence/simple-linear baselines and a non-promoting expert role;
5. use nested exact-eight LOCO: seven source configurations decide every model-affecting value, while the eighth trajectory remains sealed until outer evaluation;
6. select only pooled/conditional, or produce `no_selection`.

The Phase 7 artifact is insufficient for identification because it has only three configurations and one eight-transition episode each. There is no universal theorem that converts “24 transitions” or any other fixed count into adequate Koopman identification for this nonlinear closed-loop simulator. EDMD quality depends on the observable dictionary, sampling distribution and amount/coverage of data. Therefore Phase 8 must separate a collection-health pilot from fold-local model adequacy and retain `data_insufficient` as a valid result.

## Primary-Source Basis

The implementation choices below use primary research only as conceptual support, not as proof that EasyUUV will pass:

- Williams, Kevrekidis and Rowley define EDMD as a finite-dimensional data-driven approximation using snapshot pairs and a chosen dictionary of observables; dictionary selection is part of the approximation, not a solved universal choice. [Journal of Nonlinear Science publication record](https://collaborate.princeton.edu/en/publications/a-datadriven-approximation-of-the-koopman-operator-extending-dyna/) and [author manuscript](https://oar.princeton.edu/bitstream/88435/pr1x609/1/RowleyJoNSV25-2015.pdf).
- Proctor, Brunton and Kutz show why actuated systems must separate autonomous dynamics from control/forcing; this supports using the actual post-mask `virtual_control_4` as the controlled model input rather than fitting an autonomous model. [Generalizing Koopman theory to inputs and control](https://arxiv.org/abs/1602.07647) and [DMD with control](https://arxiv.org/abs/1409.6358).
- Korda and Mezić prove convergence statements under sampling assumptions and increasing sample/dictionary limits; this does not provide a finite EasyUUV episode count, which is why convergence and conditioning must be diagnosed from source-fold data. [On Convergence of EDMD](https://arxiv.org/abs/1703.04680).
- Persistency-of-excitation literature formulates data informativeness through rank/coverage conditions, not a universal row count. The Phase 8 plan therefore pre-registers bounded excitation and later checks source-fold regressor rank/conditioning rather than declaring a magic sample number. [On the design of persistently exciting inputs](https://arxiv.org/abs/2303.08707) and [On the persistency of excitation](https://www.sciencedirect.com/science/article/pii/S0005109822005210).
- Parameter-varying Koopman work motivates conditioning an operator on physical parameters, but does not establish that the EasyUUV descriptor will generalize. The conditional regime remains a tested hypothesis against pooled, not an assumed improvement. [Parameter-Varying Koopman Operator](https://arxiv.org/abs/2309.10278).

## Verified Codebase Facts

### Data and runtime boundary

- `koopman/schema_v2.py` accepts one exact schema-v2 transition contract and only row-origin levels `local_contract` or `server_isaac_smoke`.
- `koopman/dataset_v2.py` loads one strict episode/manifest pair and exposes `U == virtual_control_4`; `R == reference_5` and actuator/context data remain separately named.
- `workflows/koopman_bridge_v2.py` captures one atomic step after real telemetry becomes available.
- `easyuuv_nc/env/easyuuv_env.py` caches raw action before clipping, post-mask/pre-TAM virtual control, PWM, post-actuator thruster wrench and same-step platform/environment facts.
- `easyuuv_nc/embodiments.py` contains the exact public configuration set and topology facts; schema-v2 rows already contain mass, inertia diagonal, COM/COB offset, volume, drag multiplier, thruster time constant, count, mask, rank and allocation mode.

### v1 components that are analogs, not reusable contracts

- `koopman/model.py` and `koopman/edmd.py` require v1 `reference_5` and default `PWM_8`; changing them would violate Phase 7/v1 isolation.
- `koopman/baselines.py` also uses v1 reference/PWM and needs additive v2 baselines.
- `koopman/splits.py` checks path overlap only; it has no configuration, episode-role, LOCO or sealed-test semantics.
- `koopman/evaluation.py` rolls from the first row of a concatenated dataset, labels quaternion-component RMSE as attitude angle and contains hard-coded v1 horizon/divergence assumptions.
- `koopman/selection.py` opens held-out logs after a v1 validation ranking but does not bind an exact-eight inventory, nested decisions, physical features or Phase 8 evidence chain.
- `workflows/collect_koopman_v2_smoke.py` is the closest real-Isaac runner analog, but it is deliberately exact-three/eight-step smoke and must not simply be widened and relabelled.

## Recommended Artifact and Freeze Chain

The ordering is part of the scientific contract:

```text
pilot_collection_policy.json
  -> real exact-eight pilot rows/logs
  -> pilot_inventory.json
  -> pilot_health_decision.json
  -> human checkpoint
role_assignment_protocol.json + analysis_policy.json
  -> real main episode rows/logs
  -> dataset_inventory.json + split_manifest.json
  -> eight fold_protocol_decision.json files
  -> fold models/results
  -> immutable OOD aggregate
  -> selected_manifest.json or no_selection.json
  -> optional final_refit_decision.json + Phase 9 model
```

Pre-collection files contain IDs, roles and expected structure, never hashes for bytes that do not yet exist. Post-collection inventory contains actual relative paths, sizes, hashes, row counts and invariant provenance. Validators must reject inverted timestamps, stale source commit, changed role assignment or an inventory whose files were created before/after the wrong gate.

## Evidence Vocabulary Without Schema Drift

Do not add Phase 8 names to the existing transition `evidence_level` enum. Each real transition continues to say `server_isaac_smoke`, which means “this row came from the verified real-server runtime path.” A new external `phase8-evidence-envelope-v1` carries:

- `artifact_origin_level` — the frozen row origin (`server_isaac_smoke`);
- `qualification_level` — one of `server_isaac_identification_pilot`, `server_isaac_identification_dataset`, `offline_koopman_ood_evaluation`, `koopman_selection`, `no_selection`;
- experiment/protocol/inventory/source/runtime hashes;
- exact referenced-file inventory and validator status;
- allowed/disallowed claims.

The envelope validator earns a higher qualification only after re-reading every referenced artifact. A local builder may emit only `local_contract`. This preserves old artifacts and prevents a row from self-asserting Phase 8 qualification.

## Collection Protocol Recommendations

These are pre-registered engineering budgets to make the plan executable, not estimates of a theoretically sufficient sample count.

### Pilot

- Exact configurations: `base`, `long_body`, `heavy_moderate`, `asymmetric`, `uuv6`, `uuv6_angled`, `uuv4`, `uuv4_angled`.
- Two episodes/configuration, 128 transitions/episode.
- `axis_pulse` uses deterministic signed pulses across all four raw channels; `bounded_multisine` uses deterministic seed-derived phases/frequencies.
- Raw action magnitude never exceeds 0.25; `uuv4*` must receive nonzero raw yaw requests while recording zero virtual yaw.
- Pilot pass gates are collection health only: exact rows/continuity, finite/bounded fields, both signs for every controllable virtual channel, expected topology/mask, nonconstant state/control diagnostics, native/tee/semantic/log success, exact source/runtime and file hashes.
- Pilot must not import modeling modules or produce rank, condition, fit, validation or rollout metrics.

### Main recommendation for the D-23 user checkpoint

- Twelve episodes/configuration, 512 transitions/episode.
- Roles: six fit, three validation, three test, assigned before collection.
- Excitation families: `independent_prbs`, `bounded_multisine`, `coupled_chirp`; each role covers all three families with role-separated seeds. Fit uses two seeds/family; validation and test use one distinct seed/family.
- Raw actions remain bounded at 0.25 and deterministic from protocol+seed. Every episode is finalized independently; a failed episode is never replaced by rows from another role.
- Fit-prefix candidates `{2,4,6}` complete fit episodes per source configuration let each outer fold test whether more source data still changes validation error. The maximum budget is fixed before collection; a source-fold trend that is still materially improving at the maximum returns `data_insufficient`, not post-test recollection.

The user must see and approve the exact generated role/action matrix before the main bundle is transferred. Approval freezes hashes; it is not permission to change the matrix after results.

## Multi-Episode Dataset and Split Design

Add `KoopmanDatasetCollectionV2` instead of extending the one-episode object until boundaries disappear. It should retain:

- immutable episode objects and ordered episode IDs;
- role, configuration, scenario and seed indexes;
- exact source JSONL/manifest hashes;
- row views only when explicitly requested;
- physical platform facts and actuator diagnostics without making them default inputs.

`splits_v2.py` should generate exactly eight folds. For `holdout=C`:

- primary source fit/validation: only the seven non-`C` configurations;
- primary test: only `C` preassigned test episodes, opened after the fold decision hash;
- `C` fit/validation: sealed from primary, available only to the expert namespace;
- no episode appears in two roles and no role changes after inventory;
- normalization/feature selection/data-prefix/hyperparameter evidence explicitly lists only seven source configurations.

A structural leakage validator should recompute every set from inventory rather than trust path lists in the manifest.

## Additive Controlled-EDMD v2 Backend

### Common equation

For pooled/per-configuration models:

```text
phi(x[k+1]) or x[k+1] = K * [phi(x[k]), u4[k]]
```

For conditional models, use the same fitting/runtime class with an affine physical-parameter interaction:

```text
design = [phi(x), u4, p, kron(p, [phi(x), u4])]
```

This permits the learned operator to change with physical platform facts. It is a modeling hypothesis; fold-local ridge/feature validation may reject it for rank or error reasons.

### Observable candidates

Keep the pre-registered set small:

1. `identity_v1`: bias + canonicalized `state_11`; a sanity candidate expected to overlap the simple-linear hypothesis.
2. `auv_kinematic_v1`: bias + canonicalized `state_11` + depth square + componentwise linear/angular velocity squares + quaternion×angular-velocity products + linear-velocity×angular-velocity products.

The second dictionary is physics-motivated by rigid-body kinematic couplings but remains a candidate, not a proven invariant subspace. Its exact order and dimension must be constants with round-trip serialization tests.

### Quaternion preprocessing

- Never rewrite stored schema rows.
- For each episode, align each quaternion sign with the previous quaternion (`dot >= 0`); use a deterministic first-row convention and record preprocessing version/hash.
- Align the next-state quaternion consistently with the current/next sequence.
- During rollout, reject non-finite or near-zero quaternion predictions; normalize valid predictions and record projection correction before the next step.
- Compute official orientation error from normalized `abs(dot)` SO(3) geodesic radians.

### Platform descriptor candidates

Candidate physical values already supported by schema/runtime include log-scaled positive mass/volume/inertia/drag/time-constant values, COM/COB offset, normalized thruster count/rank, control mask and a fixed categorical allocation-mode descriptor. Do not use configuration identity. Candidate schemas are pre-registered in `analysis_policy`; a fold chooses one using seven-source validation and fits its normalizer on those same source configurations only.

### v2 baseline behavior

- `PersistenceBaselineV2.predict_next(x,u,p=None) -> x`.
- `SimpleLinearBaselineV2` fits bias + `state_11` + `virtual_control_4`; no reference or platform context.
- Both share the same model-facing predict protocol and evaluation path as controlled EDMD.

## Reference Diagnostic

The primary plant model assumes `x,u` are sufficient. Because the data are produced through a closed-loop controller and may omit controller internal state, this assumption needs a diagnostic rather than dogma.

`reference_conditioned_diagnostic_v2` may add `reference_5` to the same source-fold design only when declared in `analysis_policy`. It must be:

- trained/evaluated in a separate result namespace;
- labelled `selection_eligible=false`;
- excluded from feature/hyperparameter choices of primary candidates;
- interpreted as evidence that state/control may be non-Markov if it wins, not as a silently promoted model.

## Evaluation and SO(3)

All models report the same pre-registered horizons. Recommended initial policy is one-step plus 5, 20 and 60 steps (0.10/0.40/1.20 s at the Phase 7 `control_dt_s=0.02`) and full 512-step episode. The values are inherited engineering scales and must be labelled as such, not optimality claims.

For each horizon and full rollout, report:

- depth RMSE;
- body linear-velocity RMSE;
- body angular-velocity RMSE;
- SO(3) geodesic mean/RMSE/max in radians;
- quaternion projection correction statistics;
- non-finite, invalid-quaternion and divergence count/rate;
- configuration, episode and transition counts.

Open-loop rollout uses one true initial state and recorded `virtual_control_4`; it cannot reset from later truth. Windows never cross episode boundaries. Aggregate is per-configuration, equal-weight macro and worst-configuration. A row-weighted global diagnostic is allowed but never sufficient for selection.

## Nested Decision and Selection Protocol

For each outer fold:

1. load only seven source configurations' fit/validation episodes;
2. calculate source-only preprocessing, feature and normalization statistics;
3. evaluate pre-registered data prefixes, observable candidates, ridges and platform descriptor candidates;
4. produce `fold_protocol_decision.json` with the exact source episode/hash list and chosen settings;
5. fit frozen per-config/pooled/conditional primary models;
6. separately fit the held-out expert from its own fit/validation namespace;
7. open the common held-out test episodes and evaluate all roles once;
8. seal model/result hashes; no grid expansion or refit is allowed.

Selection should avoid an arbitrary sum of metrics with incompatible units. The recommended gate template:

- hard zero tolerance for non-finite predictions, invalid quaternions and undeclared divergence;
- candidate must improve over both persistence and simple-linear on predeclared full-rollout primary groups (depth, linear velocity, angular velocity, SO(3)) at equal-config macro level;
- no held-out configuration may regress beyond its source-derived pre-test noninferiority tolerance;
- a one-sided episode-block bootstrap rule, with alpha and resampling seed fixed in `analysis_policy`, supplies a positive source-derived improvement margin without reading held-out results;
- conditional can claim superiority only if the corresponding pooled-vs-conditional paired gate passes and no configuration regresses;
- any missing fold or provenance mismatch produces `no_selection`.

The D-23 human checkpoint must approve the exact alpha/resampling/margin algorithm before main collection. This is a declared experimental design choice, not a theorem.

## Final Refit for Phase 9

If pooled or conditional passes the OOD gate, outer-test results choose only the family. Do not vote among eight fold-local hyperparameter dictionaries.

Instead:

1. freeze the selected family;
2. rerun the already pre-registered inner-selection algorithm using only all eight configurations' fit+validation episodes, with configuration-blocked inner validation;
3. write `final_refit_decision.json` containing only non-test episode hashes and the selected feature/hyperparameter settings;
4. fit one final model on all fit+validation episodes;
5. validate its serialization/runtime contract, but do not evaluate or refit on test episodes.

If this refit decision or fit fails, downgrade the Phase 9 handoff to `no_selection`; never hand off a stale fold model.

## Security, Integrity and Failure Model

Reuse the Phase 7 chain but keep pilot and main roots separate. Required fail-closed defenses include:

- exact configuration/episode set; no duplicate/missing/extra rows/files;
- bounded path resolution, symlink rejection, fresh canonical target and atomic promotion;
- clean local HEAD, complete offline Git bundle and 40-hex sidecar;
- isolated server checkout, unchanged Isaac 5.0/Lab 2.2.1, offline install and `PYTHONDONTWRITEBYTECODE=1`;
- separate native process, `tee`, semantic and validator statuses;
- source/runtime/protocol/inventory/log/model/result hashes checked both server-side and after pullback;
- no evidence overwrite; preserve failure artifacts outside canonical success path;
- exact no-selection semantics: failed manifests contain no selected model path.

## Stable Reason-Code Families

At minimum:

- `pilot_policy_invalid`, `pilot_health_failed`, `pilot_modeling_forbidden`;
- `role_protocol_invalid`, `role_assignment_drift`, `data_insufficient`;
- `inventory_set_mismatch`, `artifact_hash_mismatch`, `evidence_level_mismatch`;
- `split_episode_overlap`, `heldout_design_leakage`, `heldout_normalization_leakage`;
- `feature_identity_forbidden`, `model_input_forbidden`, `reference_diagnostic_not_eligible`;
- `regressor_rank_insufficient`, `condition_limit_exceeded`, `fold_decision_stale`;
- `rollout_cross_episode`, `teacher_forcing_forbidden`, `quaternion_invalid`, `rollout_diverged`;
- `post_test_retune`, `expert_promotion_forbidden`, `selection_gate_failed`, `no_selection`.

## Testing Strategy

- Strict TDD RED commits must fail for the intended missing behavior, not only syntax/import errors after the module skeleton exists.
- Synthetic local fixtures use multiple configurations/episodes and a known controlled system so split/model/metric behavior can be asserted without Isaac.
- Mutation tests must alter one field/role/hash at a time and assert stable reason codes.
- Dynamic leakage tests instrument file reads/statistic inputs and prove held-out episodes are never opened before fold decision.
- Model tests verify v2 input widths, serialization, conditioning interactions, source-only normalizers and no reference/PWM/wrench/oracle access.
- SO(3) property tests cover `q/-q`, 0/90/180 degrees, nonunit projections, zero norm and non-finite values.
- Operational script tests use temporary Git repositories and fake SSH/SCP/Isaac commands before any real checkpoint.
- Every local full-suite run uses ignored repository-local basetemp; canonical Phase 8 success roots must remain absent until real pullback/evaluation.

## Recommended Plan Decomposition

1. **08-01 — Pilot/evidence contract and real exact-eight health checkpoint.** Add external envelope, policy/health validators, generalized identification collector and a complete offline server chain. Stop after real pilot pullback and user-visible health decision.
2. **08-02 — Multi-episode inventory and strict LOCO split.** Add collection object, role protocol, post-collection inventory, exact-eight folds, physical feature candidates and leakage mutation gates.
3. **08-03 — Controlled-EDMD v2, baselines and metrics.** Add one backend, model regimes, reference diagnostic, quaternion preprocessing/SO(3), rollout and fold decision logic.
4. **08-04 — Frozen main collection and real dataset checkpoint.** After D-23 approval, collect exact-eight main episodes on the server, build immutable inventory/split, pull back and validate independently.
5. **08-05 — Nested LOCO evaluation, selector and final refit.** Produce all fold roles/results, enforce gates, write selected/no-selection and create a non-test Phase 9 refit only after a pass.

This sequence is deliberately serial at server boundaries. It prevents a parallel worker from dirtying the worktree while a bundle/preflight claims one tested commit.

---

*Research status: complete*
*Next artifact: 08-PATTERNS.md and executable plans*
