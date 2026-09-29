# Phase 8 Exact-Eight LOCO OOD Evaluation

**Status:** `NO_SELECTION`  
**Executed:** 2026-08-30  
**Scope:** held-out-configuration open-loop prediction only

## Outcome

All eight leave-one-configuration-out folds completed. In every fold, fitting,
normalization and candidate selection used the other seven configurations only;
the primary state was frozen with `test_open_count_at_freeze=0`, and every fold
finished with `post_test_mutation_count=0`. No leakage was detected.

The frozen selector returned `no_selection`:

- `pooled_koopman_v2` was numerically identical to `simple_linear_v2` for every
  primary aggregate metric and therefore could not satisfy the registered 1%
  improvement and bootstrap gates. Against persistence it improved only angular
  velocity RMSE; the other five full-rollout metrics were worse.
- `conditional_koopman_v2` was ineligible because held-out `heavy_moderate`,
  `uuv4`, and `uuv4_angled` produced reason-coded
  `quaternion_projection_limit` failures. The failure was retained and was not
  repaired by expanding the candidate space or changing the gate.
- No selected or loadable model path exists. The held-out expert remained a
  non-promoting diagnostic role. The reference diagnostic was disabled by the
  frozen policy.

## Frozen provenance

| Item | Value |
|---|---|
| Evaluation source commit | `c7ee70f46497c896aa3ae8f5ace94b7873e0116b` |
| Selector source commit | `983a6bb4efcce87e04755aae10da8a31f6b34785` |
| Role protocol SHA-256 | `499b79089a4bfb0769ce6a902ad676f09e9c64190069a0bf5b51cd76f1d6cf26` |
| Analysis policy SHA-256 | `0d95edaf3d2511a7b0ca0440698c5e22fff51881076422ecef1712fe23c1b401` |
| Dataset inventory file SHA-256 | `cfac12d15f062c9f330d2acf6381d341769e989dc35cd00ae29759a6f94f395b` |
| Dataset inventory content SHA-256 | `41e23460b4e86b5f9748c9030bb5b1d9e33abd5222958adfa132bcb8ea8b613d` |
| LOCO split content SHA-256 | `4581427d0d63eac9b1fea038dd8f8068c363a457816141c8098ef91df85346bb` |
| Evaluation envelope SHA-256 | `5c776002d4d849f8504badbfe00fe564a82b7107a05992b26469a8a2df1f4181` |
| Evaluation decision SHA-256 | `0e19b4cfbbd2db80496834c6cf066f5df220c60305fd0b4a1a3d1963a5651ff4` |
| Selection envelope SHA-256 | `5e30db3ce2889eafa8338a4537abaa2352974b106db3ed8e7781b40d88b3eba4` |
| Selection result SHA-256 | `a7585fb8acdcb3f0b3a55cb94ce7413070aa4ceea5f060d824aa5c12ce3e23a9` |

The evaluation envelope validates as `offline_koopman_ood_evaluation` with 106
referenced leaf files and `warnings=[]`. The terminal envelope validates as
`no_selection` with one referenced immutable result and `warnings=[]`.

## Fold isolation and frozen candidates

The pooled candidate was the same registered identity candidate in all folds:
`identity_v1`, no platform features, no normalization, ridge `0.01`, prefix `6`.
Conditional candidates used only source-side physical platform descriptors.

| Held-out configuration | Conditional source-side choice | Freeze/test boundary | Pooled | Conditional |
|---|---|---|---|---|
| base | core, prefix 6, ridge 0.01 | frozen / 0 opens / 0 mutations | success | success |
| long_body | compact, prefix 6, ridge 0.01 | frozen / 0 opens / 0 mutations | success | success |
| heavy_moderate | compact, prefix 6, ridge 0.01 | frozen / 0 opens / 0 mutations | success | failed: quaternion projection |
| asymmetric | compact, prefix 2, ridge 0.01 | frozen / 0 opens / 0 mutations | success | success |
| uuv6 | compact, prefix 6, ridge 0.01 | frozen / 0 opens / 0 mutations | success | success |
| uuv6_angled | compact, prefix 6, ridge 0.01 | frozen / 0 opens / 0 mutations | success | success |
| uuv4 | compact, prefix 6, ridge 0.01 | frozen / 0 opens / 0 mutations | success | failed: quaternion projection |
| uuv4_angled | compact, prefix 6, ridge 0.01 | frozen / 0 opens / 0 mutations | success | failed: quaternion projection |

All six roles were emitted in every fold: persistence, simple linear,
source-per-configuration Koopman, pooled Koopman, conditional Koopman, and the
non-promoting held-out expert. A failed conditional role remains present with a
stable failure reason rather than being silently omitted.

## Per-configuration pooled results

Each cell is
`depth / linear-velocity / angular-velocity / SO(3)-mean / SO(3)-RMSE / SO(3)-max`.
All quantities are RMSE except the explicitly named SO(3) mean/max; orientation
is in radians. Lower is better.

| Held-out | Horizon | Six official metrics |
|---|---:|---|
| asymmetric | 5 | 0.008597 / 0.016836 / 0.387785 / 0.107356 / 0.131685 / 0.369177 |
| asymmetric | 20 | 0.032503 / 0.036834 / 1.011160 / 0.392106 / 0.484569 / 1.380610 |
| asymmetric | 60 | 0.099131 / 0.056001 / 1.098060 / 0.655903 / 0.772576 / 2.212960 |
| asymmetric | full | 0.300414 / 0.070387 / 1.140400 / 1.855150 / 1.894650 / 2.438050 |
| base | 5 | 0.003649 / 0.017308 / 0.174882 / 0.088726 / 0.097432 / 0.182004 |
| base | 20 | 0.015642 / 0.036838 / 0.368413 / 0.328890 / 0.359042 / 0.647114 |
| base | 60 | 0.039196 / 0.051425 / 0.513761 / 0.754166 / 0.834027 / 1.523590 |
| base | full | 0.078412 / 0.052808 / 0.514916 / 1.313810 / 1.374410 / 1.919960 |
| heavy_moderate | 5 | 0.019586 / 0.081990 / 0.502084 / 0.049288 / 0.069541 / 0.244012 |
| heavy_moderate | 20 | 0.085251 / 0.158796 / 1.092700 / 0.203367 / 0.277750 / 0.854361 |
| heavy_moderate | 60 | 0.250465 / 0.183095 / 1.361160 / 0.588448 / 0.761181 / 2.026740 |
| heavy_moderate | full | 1.395980 / 0.234741 / 0.921288 / 1.100990 / 1.183620 / 1.882930 |
| long_body | 5 | 0.004846 / 0.021007 / 0.230948 / 0.115933 / 0.134847 / 0.302107 |
| long_body | 20 | 0.021301 / 0.049470 / 0.590610 / 0.438608 / 0.511039 / 1.116250 |
| long_body | 60 | 0.056303 / 0.067614 / 0.851951 / 0.858589 / 0.981667 / 1.934400 |
| long_body | full | 0.166973 / 0.059304 / 0.848557 / 0.869451 / 0.965474 / 1.888460 |
| uuv4 | 5 | 0.002757 / 0.010971 / 0.118617 / 0.083304 / 0.094477 / 0.207271 |
| uuv4 | 20 | 0.013454 / 0.032141 / 0.304075 / 0.304011 / 0.339990 / 0.716933 |
| uuv4 | 60 | 0.056276 / 0.059987 / 0.479576 / 0.640238 / 0.709739 / 1.379700 |
| uuv4 | full | 0.593179 / 0.075550 / 0.430730 / 1.170700 / 1.271270 / 1.704630 |
| uuv4_angled | 5 | 0.002662 / 0.011663 / 0.124472 / 0.084004 / 0.095637 / 0.210068 |
| uuv4_angled | 20 | 0.013492 / 0.033517 / 0.324047 / 0.306777 / 0.344336 / 0.731753 |
| uuv4_angled | 60 | 0.057504 / 0.062119 / 0.505718 / 0.643552 / 0.712009 / 1.395270 |
| uuv4_angled | full | 0.612619 / 0.078163 / 0.451840 / 1.170520 / 1.273560 / 1.717620 |
| uuv6 | 5 | 0.002441 / 0.014883 / 0.373807 / 0.156871 / 0.169892 / 0.318524 |
| uuv6 | 20 | 0.011966 / 0.040159 / 0.635179 / 0.506771 / 0.551016 / 1.059330 |
| uuv6 | 60 | 0.047033 / 0.063136 / 0.808191 / 0.867632 / 0.940070 / 1.833200 |
| uuv6 | full | 0.636188 / 0.089589 / 0.792889 / 1.602280 / 1.704050 / 2.500830 |
| uuv6_angled | 5 | 0.002502 / 0.014841 / 0.420882 / 0.161302 / 0.174963 / 0.333796 |
| uuv6_angled | 20 | 0.011690 / 0.039181 / 0.728641 / 0.531240 / 0.578050 / 1.112830 |
| uuv6_angled | 60 | 0.042314 / 0.062447 / 0.857543 / 0.880619 / 0.957483 / 1.877000 |
| uuv6_angled | full | 0.608232 / 0.091711 / 0.874831 / 1.664030 / 1.777510 / 2.640600 |

## All-role aggregate and worst-configuration results

The metric order is the same six-value order above. `NA` means a required role
failed, so the aggregate deliberately fails closed. `one_step` is retained for
KID-03 even though promotion uses the frozen primary metric dimensions.

| Role | Horizon | Equal-configuration macro | Worst configuration |
|---|---:|---|---|
| persistence | one_step | 0.002257 / 0.008329 / 0.093830 / 0.020175 / 0.023474 / 0.053541 | 0.006335 / 0.037157 / 0.144938 / 0.032229 / 0.034916 / 0.085234 |
| persistence | 5 | 0.011253 / 0.026949 / 0.379577 / 0.099700 / 0.115729 / 0.260493 | 0.031572 / 0.081432 / 0.648630 / 0.158912 / 0.171555 / 0.422943 |
| persistence | 20 | 0.043507 / 0.059745 / 0.854422 / 0.353218 / 0.411549 / 0.912861 | 0.123492 / 0.164192 / 1.272550 / 0.523141 / 0.571179 / 1.527440 |
| persistence | 60 | 0.120622 / 0.089968 / 1.257990 / 0.651458 / 0.754676 / 1.608410 | 0.308298 / 0.243784 / 1.762040 / 0.907477 / 1.055710 / 2.071980 |
| persistence | full | 0.484308 / 0.088792 / 0.815882 / 1.103470 / 1.171560 / 1.751210 | 1.178390 / 0.228090 / 1.212930 / 2.026320 / 2.060570 / 2.533920 |
| simple_linear_v2 | one_step | 0.001144 / 0.007630 / 0.071824 / 0.021413 / 0.024559 / 0.055919 | 0.003774 / 0.037218 / 0.155884 / 0.032761 / 0.035671 / 0.075805 |
| simple_linear_v2 | 5 | 0.005880 / 0.023687 / 0.291685 / 0.105848 / 0.121059 / 0.270870 | 0.019586 / 0.081990 / 0.502084 / 0.161302 / 0.174963 / 0.369177 |
| simple_linear_v2 | 20 | 0.025662 / 0.053367 / 0.631853 / 0.376471 / 0.430724 / 0.952397 | 0.085251 / 0.158796 / 1.092700 / 0.531240 / 0.578050 / 1.380610 |
| simple_linear_v2 | 60 | 0.081028 / 0.075728 / 0.809496 / 0.736143 / 0.833594 / 1.772860 | 0.250465 / 0.183095 / 1.361160 / 0.880619 / 0.981667 / 2.212960 |
| simple_linear_v2 | full | 0.548999 / 0.094032 / 0.746932 / 1.343360 / 1.430570 / 2.086630 | 1.395980 / 0.234741 / 1.140400 / 1.855150 / 1.894650 / 2.640600 |
| source_per_configuration_koopman_v2 | one_step | 0.005302 / 0.132454 / 0.373627 / 0.026131 / 0.029993 / 0.063485 | 0.006944 / 0.190805 / 0.524376 / 0.042329 / 0.045469 / 0.088648 |
| source_per_configuration_koopman_v2 | 5 | 0.036228 / 0.498996 / 1.043110 / 0.139534 / 0.156494 / 0.314211 | 0.052049 / 0.666792 / 1.408620 / 0.205144 / 0.218724 / 0.407327 |
| source_per_configuration_koopman_v2 | 20 | 0.318477 / 0.882710 / 1.029530 / 0.517126 / 0.571386 / 1.149070 | 0.439986 / 1.143720 / 1.309100 / 0.690220 / 0.739787 / 1.650070 |
| source_per_configuration_koopman_v2 | 60 | 1.122460 / 0.685784 / 0.870344 / 0.990848 / 1.063870 / 1.959720 | 1.583220 / 1.046370 / 1.168810 / 1.170810 / 1.232010 / 2.313230 |
| source_per_configuration_koopman_v2 | full | 1.419650 / 0.203210 / 0.849913 / 1.291290 / 1.365820 / 2.017790 | 1.638920 / 0.252525 / 1.200000 / 2.186760 / 2.223980 / 2.620780 |
| pooled_koopman_v2 | one_step | 0.001144 / 0.007630 / 0.071824 / 0.021413 / 0.024559 / 0.055919 | 0.003774 / 0.037218 / 0.155884 / 0.032761 / 0.035671 / 0.075805 |
| pooled_koopman_v2 | 5 | 0.005880 / 0.023687 / 0.291685 / 0.105848 / 0.121059 / 0.270870 | 0.019586 / 0.081990 / 0.502084 / 0.161302 / 0.174963 / 0.369177 |
| pooled_koopman_v2 | 20 | 0.025662 / 0.053367 / 0.631853 / 0.376471 / 0.430724 / 0.952397 | 0.085251 / 0.158796 / 1.092700 / 0.531240 / 0.578050 / 1.380610 |
| pooled_koopman_v2 | 60 | 0.081028 / 0.075728 / 0.809496 / 0.736143 / 0.833594 / 1.772860 | 0.250465 / 0.183095 / 1.361160 / 0.880619 / 0.981667 / 2.212960 |
| pooled_koopman_v2 | full | 0.548999 / 0.094032 / 0.746932 / 1.343360 / 1.430570 / 2.086630 | 1.395980 / 0.234741 / 1.140400 / 1.855150 / 1.894650 / 2.640600 |
| conditional_koopman_v2 | one_step | 0.001073 / 0.009056 / 0.089331 / 0.028239 / 0.035403 / 0.092905 | 0.002902 / 0.037815 / 0.269065 / 0.054379 / 0.092531 / 0.347205 |
| conditional_koopman_v2 | 5 | 0.005557 / 0.029219 / 0.386231 / 0.139384 / 0.174221 / 0.446227 | 0.016363 / 0.088439 / 1.110150 / 0.266826 / 0.453390 / 1.645420 |
| conditional_koopman_v2 | 20 | NA | NA |
| conditional_koopman_v2 | 60 | NA | NA |
| conditional_koopman_v2 | full | NA | NA |
| heldout_expert_upper_bound_v2 | one_step | 0.000704 / 0.007422 / 0.046920 / 0.020671 / 0.023359 / 0.051845 | 0.001647 / 0.044135 / 0.138224 / 0.034639 / 0.038263 / 0.081428 |
| heldout_expert_upper_bound_v2 | 5 | 0.003691 / 0.023071 / 0.168704 / 0.101701 / 0.115081 / 0.252546 | 0.009609 / 0.116425 / 0.303555 / 0.170085 / 0.187896 / 0.396618 |
| heldout_expert_upper_bound_v2 | 20 | 0.015910 / 0.052322 / 0.369835 / 0.356686 / 0.405219 / 0.875290 | 0.049224 / 0.204283 / 0.634925 / 0.564957 / 0.635048 / 1.436500 |
| heldout_expert_upper_bound_v2 | 60 | 0.045526 / 0.073287 / 0.482905 / 0.682415 / 0.759825 / 1.524730 | 0.124332 / 0.207487 / 0.935226 / 1.179500 / 1.272920 / 2.623720 |
| heldout_expert_upper_bound_v2 | full | 0.137724 / 0.076179 / 0.536121 / 1.239870 / 1.354830 / 2.070160 | 0.234563 / 0.141060 / 1.017210 / 1.942390 / 2.070720 / 3.137830 |

## Frozen promotion gates

| Family | Completeness/health | Baseline improvement | Bootstrap/noninferiority | Conditional margin | Terminal eligibility |
|---|---|---|---|---|---|
| pooled | PASS | FAIL: identical to simple linear; 5/6 full metrics worse than persistence | FAIL | N/A | FAIL |
| conditional | FAIL: three reason-coded projection failures | not evaluated as complete family | not evaluated as complete family | not promotable | FAIL |

The pooled candidate's bootstrap lower bound against simple linear is exactly
`0.0` for all six primary metrics, and its improvement check is false for all
six. The selector reasons are `baseline_improvement_failed` and `role_failed`.

## Requirement evidence

| Requirement | Evidence result |
|---|---|
| KID-01 | Exact configuration/episode-isolated dataset and eight seven-source/one-test LOCO folds are present and validated. |
| KID-02 | All six frozen model roles are present for all eight folds; conditional failures are explicit rather than omitted. |
| KID-03 | One-step, 5, 20, 60 and full prediction results are present with equal-configuration macro and worst-configuration aggregation. |
| KID-04 | Orientation uses the official SO(3) geodesic mean/RMSE/max metrics in radians, with invalid quaternion and projection failures reason-coded. |
| KID-05 | A provenance-checked `no_selection` envelope was produced by the frozen selector and contains no model path. |

Formal PASS/FAIL and Phase 8 closeout remain subject to the independent
goal-backward verifier required by Plan 08-05.

## Engineering validation

- Targeted selector/evaluator tests: `20 passed`.
- Relevant selector/LOCO/metrics regression: `58 passed`.
- Relevant Phase 8 implementation regression before formal evaluation:
  `73 passed`; the wider affected Phase 8 set previously passed `82 passed`.
- `python -m compileall -q koopman workflows`: pass.
- Native selector CLI help: pass.
- Evaluation validator: `phase8_external_evidence_valid`, 106 references,
  `warnings=[]`.
- Selection validator: `phase8_external_evidence_valid`, qualification
  `no_selection`, one reference, `warnings=[]`.

The full repository suite and historical 08-04 byte revalidation were not
mechanically repeated: this turn changed only the 08-05 evaluator/selector path,
and the user explicitly required risk-driven targeted and relevant regression.

Two noncanonical staging attempts are preserved for audit. Both stopped before
decision freeze and before any held-out test access: one exposed read-only
descriptor serialization, and one was interrupted after revealing avoidable
source-validation runtime. Their fixes were covered before the single canonical
evaluation was published; neither staging root is promotion evidence.

## Deviations and claim boundary

No protocol deviation.

This result proves that the exact-eight server-origin dataset can be consumed by
the frozen v2 LOCO identification/evaluation chain and that the tested candidates
do **not** clear the frozen cross-configuration promotion gate. It does not prove
closed-loop Koopman-MPC performance, environment transfer, online adaptation,
Agentic behavior, Sim2Real transfer, or hardware validity.
