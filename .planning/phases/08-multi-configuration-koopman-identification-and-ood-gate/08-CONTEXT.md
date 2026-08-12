# Phase 8 Context: Multi-Configuration Koopman Identification and OOD Gate

**Captured:** 2026-08-13
**Source:** user knowledge-alignment discussion, revised `08-SPEC.md`, Phase 7 verified handoff

<phase_boundary>

Phase 8 identifies and evaluates a topology-independent v2 Koopman predictor on complete held-out configurations. It may hand one provenance-checked pooled or conditional candidate to Phase 9, or it may end with `no_selection`.

Phase 8 does not implement Koopman-MPC, closed-loop tracking, environment adaptation, an Agent Supervisor, Sim2Real or hardware validation. Phase 7 server smoke remains evidence that the data/control path runs; it is not Phase 8 training or OOD evidence.

</phase_boundary>

<decisions>

## Scientific and modeling decisions

- **D-01 — Prediction-only claim:** Phase 8 proves or rejects held-out-configuration prediction transfer. It makes no MPC, closed-loop, environment, Agentic or hardware-effect claim.
- **D-02 — Model-role vocabulary:** `persistence` and `simple_linear_v2` are baselines; per-configuration, pooled and conditional are training regimes of one additive v2 Koopman backend; expert upper bound reuses per-configuration implementation as a non-promoting evaluation role.
- **D-03 — One additive backend:** Phase 8 starts with one versioned controlled-EDMD v2 backend and a small pre-registered observable candidate set. Existing v1 direct-state and paper-lifted implementations remain frozen research history, not a backend×regime product matrix.
- **D-04 — Primary deployable input:** Selection-eligible plant predictors use `state_11 + virtual_control_4`; conditional adds only a frozen physical platform descriptor available from catalog/runtime facts.
- **D-05 — Reference is a diagnostic hypothesis:** `reference_5` is not silently added to the primary model. A pre-registered reference-conditioned diagnostic may test missing-state/closed-loop bias, but has a separate model ID and can never be promoted.
- **D-06 — Execution diagnostics stay diagnostic:** padded PWM, thruster mask, measured post-actuator wrench, saturation and energy explain coverage/execution error; they do not become selection inputs. Measured future wrench is not assumed available to Phase 9 MPC.
- **D-07 — Conditional context is physical, not identity:** configuration name/one-hot remains provenance only. Candidate platform features are physical numeric/topology facts, selected and normalized inside each outer fold using only its seven source configurations.
- **D-08 — Nominal environment only:** oracle and estimated environment context are excluded from Phase 8 selection inputs. Cross-environment modeling remains Phase 10.

## Isolation and experimental decisions

- **D-09 — Strict exact-eight LOCO:** eight outer folds each seal one complete configuration trajectory from primary model diagnostics, feature/hyperparameter choice, normalization, fit and gate-number selection.
- **D-10 — Complete-episode roles:** row-level random split is forbidden. Fit, validation and test roles are assigned to whole episodes before main collection and cannot be rewritten after bytes exist.
- **D-11 — Pilot is collection-health only:** exact-eight pilot checks schema, runtime, safety, bounded channel/state coverage, `uuv4*` yaw mask, logs and hashes. It does not fit models, compare features/horizons/backends or inspect prediction error/rank/condition.
- **D-12 — Ordered freeze chain:** pilot policy precedes pilot collection; main role protocol precedes main collection; inventory/split follows collection but precedes fit; analysis policy precedes fold decisions; each seven-source fold decision precedes its candidate fit and outer test.
- **D-13 — Expert namespace:** for holdout `C`, expert alone uses `C` fit/validation and shares only `C` test episodes with primary results. Expert artifacts never feed pooled/conditional decisions or selection.
- **D-14 — Same comparison contract:** all roles use the same dataset/split, pre-registered candidate set, inner-decision algorithm, training budget, metric schema and gate template. Fold-local hyperparameters are legal only when chosen by that shared algorithm from seven source configurations.
- **D-15 — Final refit without test leakage:** after family selection, Phase 9 refit hyperparameters/features are selected again by the pre-registered inner algorithm using all eight configurations' fit+validation only, then one model is fit on those same non-test roles. Outer-test metrics cannot vote or be averaged into refit settings.

## Metric, evidence and delivery decisions

- **D-16 — Quaternion-correct metric:** official orientation error is sign-invariant SO(3) geodesic radians. Quaternion-component RMSE is diagnostic only; invalid/projection failures are reason-coded.
- **D-17 — Configuration-balanced report:** report per-configuration, equal-weight macro and worst-configuration results. Row-weighted global summaries cannot independently promote a model.
- **D-18 — Negative results are valid:** collection-health failure yields `pilot_insufficient`; incomplete main evidence yields `data_insufficient`; no eligible candidate yields `no_selection` with no loadable model path.
- **D-19 — Additive evidence envelope:** Phase 8 qualification levels are external aggregate-envelope fields earned by validators. Frozen Phase 7 transition `evidence_level` values remain unchanged and cannot self-promote.
- **D-20 — v1 and prior evidence are protected:** v1 `PWM_8` model/MPC defaults, v1.0 archives and Phase 6/7 canonical evidence remain unchanged. Phase 8 code is additive.
- **D-21 — Local before SSH:** before each pilot or main server checkpoint, targeted/full tests, compileall, dependency checks, native script parsing, clean/protected diffs and a verified offline bundle must pass at one clean commit. The user only powers/confirms the unchanged server; the agent performs SSH/SCP and commands.
- **D-22 — Evidence/push isolation:** planning, local implementation, pilot evidence, main dataset evidence, offline evaluation/selection and planning closeout remain distinct commits. Local tests never pre-create canonical `source/results/koopman_phase8*` success directories.
- **D-23 — Human protocol checkpoint:** after pilot health passes and before main bundle creation, present the exact main role/episode/action protocol and analysis policy to the user. Approval freezes their hashes; changes create a new experiment ID before collection.

</decisions>

<specifics>

## Recommended pre-registered collection budgets

These are engineering budgets for the executable plans, not claims of statistical optimality.

- Pilot recommendation: exact eight configurations × two 128-transition episodes (`axis_pulse`, `bounded_multisine`), unique seeds/episode IDs, bounded raw action magnitude at most 0.25.
- Main recommendation: exact eight configurations × twelve 512-transition episodes: six `fit`, three `validation`, three `test`; three pre-registered excitation families with role-separated seeds.
- Main fit prefixes: `{2, 4, 6}` complete fit episodes per source configuration. A fold may choose one prefix only from its seven-source inner validation evidence. If the maximum prefix remains data-limited, that fold fails `data_insufficient` rather than collecting post-test patches.
- Historical finite horizons `{5,20,60}` steps remain an analysis-policy candidate because Phase 7 measured `control_dt_s=0.02` (0.10/0.40/1.20 s), but the protocol must label them as pre-registered engineering scales, report full episode too, and never describe them as theoretically optimal.

## Recommended v2 model candidate set

- Backend: `controlled_edmd_v2`, predicting `next_state_11` from a versioned state observable and `virtual_control_4`.
- Observable candidates: identity sanity candidate and one physics-motivated `auv_kinematic_v1` dictionary; the exact order/dimensions are versioned and tested before data use.
- Conditional form: affine parameter-varying interactions between the same state/control design and a fold-normalized physical platform descriptor; no configuration identity.
- Primary quaternion preprocessing: deterministic episode-continuous sign alignment for model fitting plus unit projection during rollout. Stored schema-v2 rows are not rewritten.

</specifics>

<deferred>

- Pilot policy may be revised only before pilot collection and then receives a new pilot experiment ID/hash. D-23 applies only to the main role/action protocol and analysis policy before main collection; any approved revision receives a new main experiment ID/hash. No value may change after its corresponding collection/test gate.
- If the non-promoting reference diagnostic substantially outperforms the primary model, do not silently promote it. Record that the current state/control Markov contract may be incomplete and require a separate future design decision.
- If no physical descriptor candidate can be selected without held-out leakage or rank failure, conditional returns reason-coded failure; pooled remains the only eligible family.
- Deep Koopman, neural encoders, online learning, applied-wrench predictors and environment-conditioned operators are not Phase 8 fallback scope.

</deferred>

---

*Phase: 08-multi-configuration-koopman-identification-and-ood-gate*
*Context status: locked for planning after independent SPEC audit pass*
