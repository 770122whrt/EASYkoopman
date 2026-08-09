# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 - Koopman-UUV Single-Configuration Control

**Shipped:** 2026-08-09
**Phases:** 14 | **Plans:** 14

### What Was Built

- A direct EasyUUV controller/data workflow compatible with Isaac Lab 2.2.1.
- Offline direct-state and paper-style lifted EDMD identification/evaluation tooling.
- A manifest-gated, bounded 8D PWM Koopman-MPC controller with fallback diagnostics.
- A PPO-to-reference adapter and RSL-RL training path that actually includes Koopman-MPC dynamics.
- Checkpoint provenance, matched evaluation, health metrics and versioned experiment profiles.
- One-factor, cross-combination and dual-track Pareto experiments through Phase 5.4.

### What Worked

- Local-first implementation reduced expensive Isaac iteration to explicit server gates.
- Keeping legacy/S-Surface runnable made every controller claim comparable and reversible.
- Manifest and provenance contracts prevented model/checkpoint relabeling errors.
- Separating direct-state engineering evidence from paper-lifted algorithm alignment kept conclusions honest.
- Sentinel -> candidate -> matched-evaluation ladders limited wasted server time.
- Parameter profiles and selectors made ablation results reproducible instead of relying on command history.

### What Was Inefficient

- `STATE.md` and `ROADMAP.md` accumulated historical notes instead of being compact current-state documents.
- Requirements checkboxes were not updated as phases completed, creating a large closeout reconciliation task.
- Several phases were executed without standard `SUMMARY.md`/`VERIFICATION.md` pairs.
- Repeated zip/bundle/server sync work was needed because the server's GitHub TLS connection was unreliable.
- Early experiments focused on broad reward/MPC tuning before adapter semantics and fallback cost margins were fully observable.
- Raw server artifacts were copied into the repository tree without an explicit data-versioning policy.

### Patterns Established

- Isaac-dependent code requires a local contract test plus a named server gate.
- Every learned model is selected through a manifest, not an implicit file path.
- Every PPO checkpoint claim carries provenance, evidence level and controller path.
- High-level policy output cannot bypass the low-level controller to PWM.
- Negative selection results such as `no_selection` are preserved as valid experimental outcomes.
- Controller evaluation uses matched step/sine/irregular workloads and reports fallback reasons, saturation, clipping, tracking and latency together.

### Key Lessons

1. A runnable control chain is not the same as a superior controller; both statements need separate gates.
2. Model form that resembles a paper is insufficient when held-out and closed-loop errors disagree.
3. PPO must be retrained after the low-level controller changes because transition dynamics and effective action semantics change.
4. Small reward/MPC weight changes cannot repair an ambiguous policy-to-reference contract.
5. Fallback rate must be decomposed by reason; moving failures from timeout to `no_cost_improvement` is not progress.
6. Multi-configuration work must condition data, dynamics, model selection and evaluation on configuration identity instead of treating assets as interchangeable USD files.

### Cost Observations

- Server work was concentrated in data collection, PPO training and matched evaluation.
- Local tests grew to 175 passing tests at closure.
- The strongest process improvement would be writing phase summary/verification artifacts immediately after each server gate.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key change |
|---|---:|---|
| v1.0 | 14 | Established local-first + Isaac-gate control research workflow. |

### Cumulative Quality

| Milestone | Tests | Coverage | Notable gate |
|---|---:|---|---|
| v1.0 | 175 passed | Not measured | Model manifest and checkpoint provenance fail closed. |

### Top Lessons

1. Preserve negative experimental results and their gates; they define the next useful question.
2. Keep current planning state compact and archive phase history at milestone boundaries.
