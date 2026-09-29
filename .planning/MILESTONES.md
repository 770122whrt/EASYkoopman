# Project Milestones: EASYkoopman

## v1.0 Koopman-UUV Single-Configuration Control (Shipped: 2026-08-09)

**Delivered:** A runnable, evidence-tracked single-configuration EasyUUV pipeline spanning Isaac data collection, offline Koopman identification, bounded MPC, PPO reference adaptation, Koopman-MPC-conditioned PPO retraining and matched parameter experiments.

**Phases completed:** 1 through 5.4 (14 phase plans)

**Key accomplishments:**

- Migrated the EasyUUV direct environment and controller workflows to Isaac Sim 5.0 + Isaac Lab 2.2.1.
- Built a reproducible JSONL -> Koopman model -> selected manifest -> bounded 8D PWM MPC pipeline.
- Added and qualified direct-state and paper-style lifted EDMD backends without conflating engineering and paper-aligned claims.
- Integrated RSL-RL PPO above Koopman-MPC through a versioned 4D-to-5D reference adapter and checkpoint provenance gates.
- Completed stability training, one-factor ablation, cross-combination screening and an 11-profile matched Pareto sweep.
- Closed honestly with `selection_status=no_selection`; the system is a research baseline, not a superiority or deployment claim.

**Stats:**

- 212 tracked files before archival
- 40,887 inserted lines before archival
- 121 Python files, approximately 12,741 lines
- 14 phases, 14 phase plans
- 45 commits through the final implementation commit
- 61 days from first planning commit to closure

**Git range:** `3952258` -> `e2f88a0`

**Known gaps accepted at close:**

- 14/40 requirements have complete formal three-source verification; 20 are functionally met with traceability gaps and 6 paper-lifted requirements are verification-orphaned.
- 5/14 phase directories contain a formal `VERIFICATION.md`.
- No Phase 5.4 parameter profile passed every promotion gate.
- No multi-configuration, online adaptation, LLM runtime, Sim2Real or hardware evidence is included.

See:

- `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`

**What's next:** No next milestone was created in this closure. Multi-configuration AUV work will be defined separately by the user.

---
