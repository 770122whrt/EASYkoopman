# Bounded repaired-plant representation diagnostic

Frozen before new collection/fitting, 2026-09-12. User has enabled a persistent goal through the current Koopman-UUV / Agentic-AUV route; routine implementation and bounded server work are authorized. Scientific admission and a new formal D-23 remain separate.

## Coverage replacement and budget

The abandoned legacy matrix remains incomplete historical work. It tested a plant with a demonstrated initialization defect. Replace its remaining coverage for the current interface decision with the accepted authored_static_v1 cold/warm/on/off evidence and the following eight additional cold, traced cases in the unchanged tested r5 source (`a9a6e20f4ac05b183cf28fd4710f5a21478b9d7c`):

- base / uuv4, seed8202, PRBS: two cases.
- base / uuv4 / uuv6, seed8201, zero and step: six cases.

Each has32 control intervals, two physics substeps, no preparation:256 additional intervals, cumulative1312. Use declared_v1 inertia, episode_local_v1 controller reset, authored_static_v1 initialization, backend readback, fixed source excitation amplitude0.1 and4-interval PRBS hold. Reuse the already accepted four cold PRBS trajectories (three seed8201 fit and three seed8202 validation after this supplement), without counting warm/off duplicates as independent samples. The supplemental zero/step traces are out-of-family diagnostics, never fit. Maximum5min per process and45min batch including preflight; fail on first native/source/runtime/trace violation. Preserve every attempt and pullback with exact case inventory and hashes. No new simulator code, old formal data, model grid or formal experiment.

## Fixed representation comparison

Exactly12 fits: three configuration-local fits for each of four variants: last-control + causal4D proxy; ordered two controls + causal4D proxy; last-control + causal N-speed; ordered two controls + causal N-speed. This factorial diagnostic controls the regression family and trajectories; different feature dimensions and sample sizes remain confounds and must be reported. No inference of pooled/OOD benefit from per-configuration fits.

Features: bias, world z, body-to-world rotation R6, body v/omega, chosen memory at interval start and chosen preset controls. N-speed slots follow each configuration's exact thruster geometry/order; no anonymous padded cross-platform vector. Proxy follows the frozen v2.1 last-control recurrence and N-speed is reconstructed from known zero reset and generated commands, never measured speed. Inputs can be precomputed only because the measured controller consumes preset raw action and its own history; this is not true future feedback availability.

Fit increment targets using the existing SO(3)10D increment convention, feature centering/scaling from the one fit episode only (std floor1e-6), intercept unpenalized, ridge1e-3 in mean-squared objective. Solve by SVD; no hyperparameter search, contraction, clipping or lift selection. Remove structurally masked uuv4 yaw-control/proxy columns by topology before fit; report rank, singular values and conditioning without silently deleting empirical low-variance columns.

Report matched raw depth/attitude/linear/angular RMSE versus persistence at teacher-forced one step and all sliding1/5/20/32-step origins wholly inside each32-step episode. Each recursion uses only its initial measured state plus causally generated controls/memory, not intermediate measured state. Nonfinite predictions, abs depth/body velocities greater100 or SO(3) failure terminate that origin and invalidate its complete aggregate; report failures rather than survivor-only scores. Relative ratios use fixed denominator floors0.01m,0.01rad,0.01m/s,0.01rad/s and are exploratory. Also report per-channel increment residuals, activation/deadzone/saturation and unique action counts. No60/full512 claim; no model promotion. Existing seed8202 uuv6 was inspected for reconstruction, so this is exploratory validation, not untouched confirmation.

## Decision use

Close8.3 only after evaluating its actual six requirements. Interface correctness and causal sufficiency can justify a bounded8.4 fresh pilot; short-trace gains do not justify formal recollection or Phase9. If these fits are underdetermined or disagree, record that uncertainty explicitly and design one fresh pilot with sufficient whole-episode coverage. Prefer direct bounded pre-TAM control if consistent with observed mechanisms and Phase9; make its changed hold waveform explicit and test it rather than claiming plant equivalence automatically.
