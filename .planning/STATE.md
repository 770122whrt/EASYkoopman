# Project State: EASYkoopman

**Updated:** 2026-08-09
**Current focus:** Milestone v1.0 closed; awaiting user-led definition of the next milestone
**Active milestone:** none
**Branch:** `isaaclab2-migration`

## Project Reference

See `.planning/PROJECT.md`.

**Core value:** Build control experiments whose model, checkpoint, controller path and evaluation evidence are explicit enough to reproduce, compare and reject safely.

## Milestone Status

```text
v1.0 Koopman-UUV Single-Configuration Control
status = closed
scope = Phase 1 through Phase 5.4
closure = research baseline with accepted gaps
```

Canonical closeout records:

- `.planning/reports/MILESTONE_SUMMARY-v1.0.md`
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `.planning/MILESTONES.md`
- `.planning/RETROSPECTIVE.md`

## Verified At Close

```text
python -m pytest -q --basetemp .pytest-milestone-v1
175 passed

python -m compileall __init__.py easyuuv_env.py koopman workflows tests
passed
```

Server evidence accumulated during v1.0 includes:

- Isaac Sim 5.0 + Isaac Lab 2.2.1 direct-controller rollout;
- validated step/sine/irregular Koopman logs;
- Phase 2.5 direct-state model gate pass;
- Phase 3 bounded Koopman-MPC smoke;
- controller-only three-backend matched evaluation;
- Koopman-MPC-conditioned PPO checkpoint smoke;
- Phase 5.1 stable-training candidate;
- Phase 5.2 one-factor, Phase 5.3 cross-combination and Phase 5.4 Pareto experiments.

## Frozen v1.0 Conclusions

- The single-configuration end-to-end control/retraining/evaluation chain runs.
- `direct_state` is the engineering Koopman backend for v1.0.
- `paper_lifted_edmd` is a research comparison and is not the default controller.
- Legacy/S-Surface remains the strongest nominal baseline.
- Phase 5.4 completed 11/11 sentinels and 11/11 matched candidates but selected no profile.
- Latency was not the primary Phase 5.4 bottleneck.
- Adapter/reference semantics and `no_cost_improvement` fallback are stronger hypotheses than further broad reward/MPC micro-tuning.
- No online Koopman learning or LLM runtime is present.

## Deferred Items Accepted At Close

| Category | Item | Status |
|---|---|---|
| control | Diagnose or replace `heuristic_reference_delta_v0` | deferred |
| MPC | Add candidate/fallback cost-margin and prediction-error diagnostics | deferred |
| performance | Find a profile that passes all matched promotion gates | deferred |
| model | Diagnose paper-lifted depth mismatch | deferred |
| planning | Define configuration identity and multi-AUV scope | deferred to a future milestone |
| adaptation | Online Koopman KF/RLS | deferred |
| agent | Low-frequency LLM planning/tuning | deferred |
| deployment | Sim2Real and hardware validation | deferred |
| documentation | Missing formal verification artifacts for nine phase directories | accepted technical debt |
| artifacts | About 104 MB of raw server results remain local and outside the Git tag | accepted technical debt |

## Next Action

None is active. The user will create and scope the next milestone separately. This closeout must not be interpreted as approval of a specific multi-configuration architecture or roadmap.
