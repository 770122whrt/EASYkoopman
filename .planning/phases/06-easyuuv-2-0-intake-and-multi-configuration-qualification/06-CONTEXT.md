# Phase 6: EasyUUV 2.0 Intake and Multi-Configuration Qualification — Context

**Gathered:** 2026-08-09
**Status:** Ready for planning
**Source:** PRD Express Path (`06-SPEC.md`, derived from the user-approved v2.0 milestone design)

<domain>
## Phase Boundary

Phase 6 imports and qualifies the received EasyUUV 2.0 simulator as the single `easyuuv_nc` source for v2.0. It delivers provenance separation, a reproducible package/runtime contract, an eight-configuration catalog, topology/controllability truth, local Isaac-free validators, tiered server smoke commands and phase evidence.

It does not change Koopman control semantics, train a model or policy, implement environment adaptation, or add an Agent runtime. Those capabilities remain in Phase 7–11.

</domain>

<decisions>
## Implementation Decisions

### Git and source provenance

- **D-01:** The received `easyuuv_v2-main/` tree is committed as an unmodified snapshot before any package normalization, tests or integration changes.
- **D-02:** Snapshot, v1.0 `source/results` evidence and v2.0 planning/integration remain independently auditable commit/push boundaries; no remote force-push is part of the delivery procedure.
- **D-03:** The `v1.0` tag, `.planning/milestones/v1.0-*`, `.planning/reports/MILESTONE_SUMMARY-v1.0.md` and retained v1 phase directories are not rewritten or deleted.

### Supported simulator contract

- **D-04:** The only public Phase 6 configuration set is `base`, `long_body`, `heavy_moderate`, `asymmetric`, `uuv6`, `uuv6_angled`, `uuv4`, `uuv4_angled`; internal `heavy_duty` remains unsupported and absent from public CLI choices.
- **D-05:** `easyuuv_nc` is the canonical package/import name. One runbook must define its physical directory or packaging mechanism, Isaac-free import behavior, four gym IDs and USD asset resolution.
- **D-06:** All eight configurations use the shared `data/embodiment/embodiment.usd`; Phase 6 describes them as dynamics/thruster variants, not eight distinct visual robots.

### Topology and control truth

- **D-07:** The controller-facing channel order for qualification metadata is `[roll,pitch,yaw,depth]`.
- **D-08:** `base/long_body/heavy_moderate/asymmetric` have 8 thrusters and mask `[1,1,1,1]`; `uuv6/uuv6_angled` have 6 and `[1,1,1,1]`; `uuv4/uuv4_angled` have 4 and `[1,1,0,1]`.
- **D-09:** Declared-control rank is 4 for the six full four-channel configurations and 3 for `uuv4*`; a validator must fail if yaw is reported controllable for either 4-thruster configuration.
- **D-10:** Normalized action/virtual-control and PWM bounds are `[-1,1]` with validator tolerance `1e-6`; NaN, Inf, bound violations and thruster-dimension mismatches have distinct reason codes.

### Evidence split and completion

- **D-11:** Local evidence is limited to static contracts, pure Python/Torch qualification logic, pytest and compileall; Isaac rollout claims require server artifacts.
- **D-12:** Server qualification uses Isaac Sim 5.0 + Isaac Lab 2.2.1 as the expected baseline, records actual versions, runs `base` for at least 64 physics steps and each other configuration for at least 8 steps.
- **D-13:** Phase 6 cannot complete without a machine-readable eight-row qualification artifact, validator, server runbook, SUMMARY and VERIFICATION covering QUAL-01..08.
- **D-14:** Existing v1 Koopman state/reference/control dimensions and runtime selection behavior remain unchanged during Phase 6.

### the agent's Discretion

- Exact filename/module layout for the catalog, probe CLI, artifact schema and validator, provided each has a stable documented public entry point.
- Whether packaging uses a conventional `pyproject.toml` editable install or a documented directory/PYTHONPATH layout, provided `import easyuuv_nc` and asset lookup are unique and reproducible.
- How pure-Torch TAM tests load the configuration source without importing Isaac, provided configuration truth is not duplicated in an unvalidated second source.
- Exact pytest file grouping and helper decomposition.
- Exact JSON indentation and human-readable report formatting; the machine schema and required values remain deterministic.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked Phase Contract

- `.planning/phases/06-easyuuv-2-0-intake-and-multi-configuration-qualification/06-SPEC.md` — Falsifiable Phase 6 requirements, constraints and acceptance criteria.
- `.planning/REQUIREMENTS.md` — Canonical QUAL-01..08 descriptions and milestone traceability.
- `.planning/ROADMAP.md` — Phase 6 goal, dependencies and success criteria.
- `docs/Agentic_AUV_v2_milestone_design.md` — User-approved v2.0 architecture and Git isolation decisions.

### Received EasyUUV 2.0 Source of Truth

- `easyuuv_v2-main/__init__.py` — Declared `easyuuv_nc` imports and four gym registrations.
- `easyuuv_v2-main/env/easyuuv_env.py` — Embodiment presets, `apply_embodiment_config`, 4D action contract and runtime thruster paths.
- `easyuuv_v2-main/env/thrust_allocation.py` — TAM construction, controllable-DOF weights, pinv/WLS allocation and 4D-channel-to-wrench mapping.
- `easyuuv_v2-main/env/assets/warpauv.py` — Shared USD relative path.
- `easyuuv_v2-main/workflows/train.py` — Public training CLI embodiment choices.
- `easyuuv_v2-main/workflows/adapt.py` — Public adaptation CLI embodiment choices and application order.
- `easyuuv_v2-main/README.md` — Received run/import claims and server command assumptions.

### v1 Isolation Baseline

- `easyuuv_env.py` — Existing root v1 EasyUUV environment and Koopman-MPC integration seam.
- `koopman/model.py` — Existing 8D-PWM Koopman model contract that Phase 6 must not change.
- `koopman/mpc.py` — Existing bounded PWM MPC contract that remains v1-only in this phase.
- `.planning/milestones/v1.0-ROADMAP.md` — Frozen prior milestone scope.
- `.planning/milestones/v1.0-REQUIREMENTS.md` — Frozen prior requirements.

</canonical_refs>

<specifics>
## Specific Ideas

- Prefer one canonical catalog that both CLI choices and qualification tooling consume, or an explicit validator proving duplicated CLI lists exactly match it.
- Report both raw TAM/mixing metadata and the rank over the declared `[roll,pitch,yaw,depth]` subspace so angled thrusters do not create misleading raw 6D-rank conclusions.
- The machine artifact should make missing configurations impossible to hide by validating exact set equality rather than `count == 8` alone.
- Server output should distinguish environment creation, reset and stepping failures so package/asset errors are not mislabeled as controller instability.
- Qualification must be runnable without loading the v1 Koopman controller; Phase 6 tests the simulator intake seam, not the final bridge.

</specifics>

<deferred>
## Deferred Ideas

- schema v2 and fixed 4D Koopman control input — Phase 7.
- Multi-configuration data collection, pooled/conditional models and OOD gates — Phase 8.
- TAM-aware Koopman-MPC — Phase 9.
- Environment context estimation and RLS/KF online adaptation — Phase 10.
- Low-frequency Agent Supervisor — Phase 11.
- Final multi-shift matched evaluation and research claims — Phase 12.
- Distinct CAD/visual assets, hardware validation and Sim2Real — future milestones.

</deferred>

---

*Phase: 06-easyuuv-2-0-intake-and-multi-configuration-qualification*
*Context gathered: 2026-08-09 via PRD Express Path*
