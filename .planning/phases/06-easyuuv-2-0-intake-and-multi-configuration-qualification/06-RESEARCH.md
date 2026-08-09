# Phase 6 Research: EasyUUV 2.0 Intake and Multi-Configuration Qualification

**Researched:** 2026-08-09
**Scope:** Phase 6 only
**Requirements:** QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, QUAL-07, QUAL-08

## Research Conclusion

Phase 6 should not begin by editing the received tree in place. The safe implementation sequence is:

1. Preserve the received `easyuuv_v2-main/` tree as the first remote snapshot boundary.
2. In a later integration commit, rename the tracked directory to the declared package name `easyuuv_nc/` and add conventional packaging/asset metadata.
3. Extract embodiment truth from the Isaac-dependent `EasyUUVEnvCfg` into a pure module consumed by the environment, CLIs and tests.
4. Keep TAM math importable without Isaac, then build a deterministic catalog/topology report and qualification artifact validator around it.
5. Run local contract/regression gates first; run the eight-configuration physics smoke only on the Isaac server and validate pulled-back artifacts locally.

This phase is medium integration risk, not high algorithmic risk. The main failure modes are package-path drift, duplicated configuration truth, impossible yaw claims for `uuv4*`, and evidence mixing between local static checks and server physics.

## Current-State Inventory

### Received tree

- `easyuuv_v2-main/__init__.py` declares package `easyuuv_nc`, registers four gym task IDs and catches missing `gymnasium`/`omni` so the package can degrade on non-Isaac hosts.
- The physical directory is `easyuuv_v2-main`, so `import easyuuv_nc` is not currently guaranteed from this repository.
- No `pyproject.toml`, `setup.py` or `setup.cfg` exists in the received tree.
- `env/assets/warpauv.py` resolves one shared USD via a source-relative path to `data/embodiment/embodiment.usd`.
- `workflows/train.py` and `workflows/adapt.py` each hard-code the same eight public embodiment choices.
- `EasyUUVEnvCfg.embodiment_configs` contains those eight configurations plus internal `heavy_duty`.
- Parameter variants use the legacy 8-thruster path. `uuv6*` and `uuv4*` carry explicit `thrust_allocation` configuration.
- `env/thrust_allocation.py` is pure Torch code, but importing it through `easyuuv_nc.env` currently executes `env/__init__.py`, which imports the Isaac-dependent environment.
- No repository-integrated Phase 6 catalog, artifact schema, validator or tests exist.

### Existing EASYkoopman root

- `easyuuv_env.py` is the v1 environment with an embedded Koopman-MPC seam.
- `koopman/model.py` defaults to `STATE_DIM=11`, `REFERENCE_DIM=5`, `control_dim=PWM_DIM=8`.
- `koopman/mpc.py` optimizes and bounds 8D PWM. It is intentionally untouched in Phase 6.
- Existing validators follow a useful pattern: load JSON, require exact fields/values, reject non-finite or unsafe values with `ValueError`, expose `main(argv) -> int`, and test the public function plus CLI behavior.
- Existing Phase 4 work shows the local/server split pattern: deterministic local summarizer/validator, explicit server commands, artifact pullback, then final evidence summary.

## Recommended Integration Architecture

### 1. Package normalization

Recommended approach after the immutable snapshot commit:

```text
git mv easyuuv_v2-main easyuuv_nc
```

Then add a repository-root `pyproject.toml` that discovers only `easyuuv_nc*` packages and includes `easyuuv_nc/data/embodiment/*` as package data. A normal editable install from the repository root becomes the canonical server contract:

```text
python -m pip install -e . --no-deps
python -c "import easyuuv_nc; print(easyuuv_nc.__file__)"
```

Why this option:

- It matches the package name already used throughout the received code.
- Git records a tree rename after the snapshot rather than duplicating 72 MiB of objects.
- It avoids a symlink, wrapper package or importlib alias hack.
- It gives package-data rules one stable root.

Rejected alternatives:

- Keep `easyuuv_v2-main` and inject a runtime alias: repeats the import hack the received code explicitly removed.
- Create a filesystem symlink `easyuuv_nc`: fragile on Windows and ambiguous in archives.
- Maintain two copies: creates configuration and asset drift immediately.

Asset resolution should use one helper based on the installed `easyuuv_nc` package root, not the process working directory. The helper must verify the USD exists and return an absolute path before Isaac creates `UsdFileCfg`.

### 2. Pure configuration truth

Extract the literal embodiment mapping and support metadata into a pure top-level module:

```text
easyuuv_nc/embodiments.py
```

Recommended public values:

```text
SUPPORTED_EMBODIMENTS = (
  "base", "long_body", "heavy_moderate", "asymmetric",
  "uuv6", "uuv6_angled", "uuv4", "uuv4_angled",
)
INTERNAL_EMBODIMENTS = ("heavy_duty",)
EMBODIMENT_CONFIGS = {...}
CONTROL_CHANNELS = ("roll", "pitch", "yaw", "depth")
```

`EasyUUVEnvCfg.embodiment_configs`, `workflows/train.py`, `workflows/adapt.py` and qualification tooling should import these values. This makes the pure module the single source of truth and turns duplicate CLI choices into tested consumers.

For TAM testing, move the pure implementation to:

```text
easyuuv_nc/thrust_allocation.py
```

and keep `easyuuv_nc/env/thrust_allocation.py` as a compatibility re-export if external callers may use the old path. `easyuuv_env.py` imports the top-level module. This avoids executing `easyuuv_nc.env.__init__` during local Torch-only tests.

### 3. Qualification model and commands

Recommended repository-level entry points:

```text
workflows/qualify_easyuuv_v2.py
workflows/validate_easyuuv_v2_qualification.py
tests/test_easyuuv_v2_catalog.py
tests/test_easyuuv_v2_qualification.py
docs/phase6_easyuuv_v2_qualification_runbook.md
```

`qualify_easyuuv_v2.py` should support two modes:

- `--catalog-only`: pure Python/Torch metadata and TAM report; runnable locally.
- server physics mode: import gym/Isaac, create one selected configuration, reset, step, and write one configuration result.

The server runbook loops over the exact public set and merges per-configuration results. Per-process execution is safer than creating all topologies in one process because the environment changes buffer dimensions by embodiment.

### 4. Machine artifact

Use a versioned JSON object, not console scraping:

```json
{
  "schema_version": "easyuuv-v2-qualification-v1",
  "expected_isaac_sim": "5.0",
  "expected_isaac_lab": "2.2.1",
  "actual_versions": {},
  "task_id": "EasyUUV-Direct-v1",
  "results": [
    {
      "configuration": "base",
      "public": true,
      "thruster_count": 8,
      "control_channels": ["roll", "pitch", "yaw", "depth"],
      "control_mask": [1, 1, 1, 1],
      "declared_control_rank": 4,
      "environment_created": true,
      "reset_passed": true,
      "steps_completed": 64,
      "action_min": -1.0,
      "action_max": 1.0,
      "motor_min": -1.0,
      "motor_max": 1.0,
      "nonfinite_count": 0,
      "dimension_mismatch_count": 0,
      "seed": 0,
      "status": "pass",
      "reason_codes": []
    }
  ]
}
```

The validator must compare the configuration set exactly, not only count rows. It must reject duplicate configurations, wrong counts/masks/ranks, missing version/provenance fields, insufficient steps, non-finite numeric fields, bounds beyond `1 + 1e-6`, and non-empty hard-failure reason codes.

## Closest Existing Patterns

| New responsibility | Existing analog | Pattern to reuse |
|---|---|---|
| JSON artifact validator | `workflows/validate_phase5_1_stability_summary.py` | `REQUIRED_FIELDS`, finite checks, exact values, `main(argv)->int`, JSON output |
| CLI validation tests | `tests/test_phase5_1_stability_validator.py` | Valid fixture plus one mutation per hard failure |
| Simple path-based CLI | `workflows/validate_koopman_log.py` | `Path`, stderr error, non-zero exit |
| Local/server evidence split | `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-PLAN.md` | Local validator, explicit server matrix, pullback, summary |
| Source contract tests | `tests/test_phase1_source_contract.py`, `tests/test_isaaclab2_source_contract.py` | Read source without importing Isaac; assert exact contract strings/paths |
| Bounds/non-finite gates | `workflows/validate_phase5_1_stability_summary.py` | Hard-fail finite counts and PWM limits |

## TDD Strategy

`workflow.tdd_mode=true`. Use TDD only where a stable pure input/output contract exists.

### TDD candidates

1. **Canonical catalog and topology report**
   - RED: exact supported/internal sets, counts, masks and ranks fail because no pure catalog exists.
   - GREEN: extract catalog/TAM truth and make environment/CLI consume it.
   - REFACTOR: remove duplicated lists and keep compatibility exports.

2. **Qualification artifact validator**
   - RED: valid eight-row fixture and one-failure-per-rule tests.
   - GREEN: schema loader and deterministic validator/CLI.
   - REFACTOR: shared finite/bounds helpers and stable reason codes.

### Standard tasks

- Snapshot/import Git boundary and clean history assembly.
- Directory rename and `pyproject.toml`/package-data setup.
- Server Isaac runner and runbook.
- Final regression commands and evidence handoff.

These involve filesystem/package wiring or external runtime execution rather than one pure behavior and should not be forced into a one-feature TDD plan.

## Git and Push Strategy

Planning commits currently precede the untracked snapshot on the working branch, so pushing the branch directly would violate the desired order. After planning and before the first remote push:

1. Preserve the current local planning lineage under a backup branch name.
2. Create a clean `v2.0-multi-configuration` delivery branch from `v1.0` without force-updating any remote ref.
3. Because the two untracked directories do not exist at `v1.0`, they can remain in the working tree across the local branch switch.
4. Commit and push the received simulator snapshot first.
5. Commit and push `source/results` plus its manifest second.
6. Cherry-pick the reviewed design/milestone/spec/context/research/plan commits from the preserved local branch and push planning third.

No `git reset --hard`, remote force-push or deletion of v1 phase directories is necessary.

## Security and Integrity Threat Model

### Protected assets

- Received snapshot provenance.
- v1.0 tag and archived planning evidence.
- Package asset path and server command target.
- Machine qualification result used for phase promotion.

### Threats and mitigations

| Threat | Severity | Mitigation |
|---|---|---|
| Path traversal or wrong workspace passed to validator/runner | High | Resolve paths, require expected package/artifact filenames, avoid deleting or recursively moving computed paths. |
| Artifact spoofing by omitting failed configurations | High | Exact set equality, unique configuration keys, per-row status and minimum steps. |
| NaN/Inf serialized as permissive JSON values | High | Reject non-finite values before writing and again while validating; use strict JSON serialization. |
| Command injection through configuration name | Medium | `argparse` choices from `SUPPORTED_EMBODIMENTS`; never interpolate unchecked names into shell command strings. |
| USD path resolves outside installed package | Medium | Resolve absolute path and assert it remains under the `easyuuv_nc` package root. |
| Internal `heavy_duty` silently counted as public success | Medium | Exact public/internal set tests and validator rejection of extra result rows. |
| Local contract result presented as Isaac physics evidence | High | Evidence-level field and required actual Isaac/Isaac Lab versions for server rows. |
| Existing v1 phase directories removed by milestone cleanup | High | Explicitly prohibit phases-clear/deletion; retain canonical archive references. |

Plans should include a `<threat_model>` block and block completion on unresolved High threats.

## Validation Architecture

### Layer 0 — Git/provenance preflight

```powershell
git status --short
git show --stat --oneline <snapshot-commit>
git diff --check
git diff v1.0 -- .planning/milestones .planning/reports
```

Gate: snapshot and later changes are separate; no frozen archive modification.

### Layer 1 — Isaac-free unit and contract tests

```powershell
python -m pytest -q tests/test_easyuuv_v2_catalog.py tests/test_easyuuv_v2_qualification.py
python -m pytest -q --basetemp .pytest-phase6
python -m compileall __init__.py easyuuv_env.py koopman workflows tests easyuuv_nc
```

Gate: exact catalog/topology/validator tests pass; full suite exits 0 with at least 175 tests.

### Layer 2 — Package probes

Local degraded import:

```powershell
python -c "import easyuuv_nc; print(easyuuv_nc.__file__)"
python workflows/qualify_easyuuv_v2.py --catalog-only --output-json .planning/tmp/phase6-catalog.json
python workflows/validate_easyuuv_v2_qualification.py .planning/tmp/phase6-catalog.json --catalog-only
```

Server package/gym/asset probe:

```bash
python -m pip install -e . --no-deps
python -c "import easyuuv_nc, gymnasium as gym; print(easyuuv_nc.__file__); print(gym.spec('EasyUUV-Direct-v1'))"
```

Gate: import path is unique, four gym IDs resolve, shared USD exists under package root.

### Layer 3 — Server physics smoke

Run each public configuration in a separate process. `base` uses `--steps 64`; all others use `--steps 8`. Each process writes one JSON result; a merge command creates the final eight-row artifact.

Gate: exact configuration set, environment create/reset/step pass, finite/bounded controls, correct motor dimension, recorded actual versions.

### Layer 4 — Artifact validation and phase evidence

```powershell
python workflows/validate_easyuuv_v2_qualification.py source/results/koopman_phase6/qualification.json --json
```

Gate: validator returns 0; Phase 6 SUMMARY and VERIFICATION map every QUAL ID to evidence. Any missing server row keeps the phase unverified rather than treating local tests as a substitute.

## Implementation Pitfalls

1. Do not import `EasyUUVEnvCfg` in local catalog tests; it transitively requires Isaac.
2. Do not duplicate the embodiment dictionary into tests or a second runtime catalog; extract one pure source and compare consumers to it.
3. Do not use raw `rank(B)` alone as the control claim for angled layouts; evaluate the declared `[roll,pitch,yaw,depth]` subspace.
4. Do not count `heavy_duty` in the eight public configurations.
5. Do not advertise eight visual robots; all use the shared USD.
6. Do not alter v1 `PWM_DIM=8` to make Phase 6 tests pass; cross-configuration Koopman semantics start in Phase 7.
7. Do not run a destructive GSD phases cleanup; the retained v1 directories have no separate full directory archive.
8. Do not merge partial server results into a passing artifact.
9. Do not hide actual Isaac version drift; record it and decide compatibility explicitly.

## Planning Recommendation

Use four plans in three waves:

| Plan | Type | Wave | Objective |
|---|---|---:|---|
| 06-01 | execute | 1 | Normalize package/install/asset contract after the snapshot boundary. |
| 06-02 | tdd | 2 | Create canonical embodiment catalog and topology/controllability qualification. |
| 06-03 | tdd | 2 | Create strict qualification artifact schema and validator. |
| 06-04 | execute with server checkpoint | 3 | Add server runner/runbook, run regressions, validate eight-configuration evidence and hand off to verification. |

`06-02` and `06-03` can execute in parallel after `06-01`. `06-04` depends on both.

---

## RESEARCH COMPLETE

Phase 6 is ready for planning. The recommended design preserves the received snapshot, makes `easyuuv_nc` a conventional package, extracts one pure embodiment/TAM truth source, and separates local contract evidence from server physics evidence.
