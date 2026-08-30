# Repository guidance

## Start here

- Run repository commands from this `EasyUUV` Git root. For milestone or phase work, use `.planning/PROJECT.md`, `.planning/ROADMAP.md`, and `.planning/STATE.md` to locate the current contract, then read only the task-relevant `*-SPEC.md`, `*-CONTEXT.md`, or `*-PLAN.md`. Keep phase-specific hashes, thresholds, artifact paths, and procedures in those files and their runbooks rather than copying them here.
- Treat the upstream Isaac Lab 1.x setup in `README.md` as historical. Use the planning files and their linked runbooks under `docs/` for current environment and workflow guidance.

## Preserve project boundaries

- Keep the v1.0 historical records, models, and evidence frozen unless a task explicitly targets that history. Implement current milestone work through the versioned interfaces identified by the current phase contract.
- Preserve the control and evidence invariants in `.planning/PROJECT.md`: high-level policies must not bypass bounded low-level control, configuration and topology constraints must remain explicit, and model, checkpoint, or evidence promotion must fail closed on missing or inconsistent provenance.
- Do not treat local fixtures, mocks, or Isaac-free runs as Isaac physics evidence. Server/Isaac claims require the applicable runbook's real-server collection, validation, inventory, and pullback gates. Do not manually pre-create, copy, or relabel canonical success artifacts under `source/results/` to satisfy those gates.

## Test and validation routing

- For code changes and bug fixes, add or update a focused failing pytest contract before implementation when practical. Run focused tests with the active project interpreter via `python -m pytest -q ...`, then run the broader relevant suite after they pass.
- For server or evidence work, follow the applicable checked-in `scripts/*_local_preflight.ps1` when present and the matching `docs/*_runbook.md`. Those artifacts own the exact tests, clean-tree requirements, runtime, bundle, hash, inventory, and promotion procedure; do not replace a stricter checked-in gate with a generic command.
