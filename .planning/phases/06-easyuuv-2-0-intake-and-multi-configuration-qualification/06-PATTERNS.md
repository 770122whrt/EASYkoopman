# Phase 6 Pattern Map

**Mapped:** 2026-08-09
**Phase:** EasyUUV 2.0 Intake and Multi-Configuration Qualification

## Data Flow

```text
easyuuv_nc/embodiments.py
  ├─> easyuuv_nc/env/easyuuv_env.py
  ├─> easyuuv_nc/workflows/train.py + adapt.py
  └─> workflows/qualify_easyuuv_v2.py --catalog-only
          └─> topology report + server per-config rows
                  └─> qualification.json
                          └─> workflows/validate_easyuuv_v2_qualification.py
                                  └─> Phase 6 VERIFICATION evidence
```

Package and asset flow:

```text
pyproject.toml
  └─> editable install discovers easyuuv_nc*
          └─> import easyuuv_nc registers gym IDs when Isaac is available
                  └─> asset helper resolves easyuuv_nc/data/embodiment/embodiment.usd
```

## File-to-Analog Map

| Target file | Role | Closest analog | Pattern to preserve |
|---|---|---|---|
| `pyproject.toml` | Package discovery and package data | No existing packaging metadata | Discover only `easyuuv_nc*`; include shared embodiment asset; keep v1 root modules unmodified. |
| `easyuuv_nc/__init__.py` | Degraded import plus gym registrations | Received `easyuuv_v2-main/__init__.py` | Catch only missing `gymnasium`/`omni`; re-raise unrelated missing modules; keep four task IDs. |
| `easyuuv_nc/embodiments.py` | Pure configuration truth | `EasyUUVEnvCfg.embodiment_configs` in received `env/easyuuv_env.py` | Preserve numeric literals and nested `thrust_allocation`; add exact public/internal tuples and control-channel order. |
| `easyuuv_nc/thrust_allocation.py` | Pure Torch TAM and rank helpers | Received `env/thrust_allocation.py` | Preserve `ThrusterLayout.from_specs`, `build_wrench_matrix`, `dof_weight_vector`, `allocate`; add declared-control rank helper without Isaac. |
| `easyuuv_nc/env/thrust_allocation.py` | Compatibility import | Existing module path | Thin re-export only; no duplicate implementation. |
| `easyuuv_nc/env/easyuuv_env.py` | Isaac runtime consumer | Existing received implementation | Replace inline mapping with imported `EMBODIMENT_CONFIGS`; do not alter PID/TAM runtime behavior. |
| `easyuuv_nc/workflows/train.py` | Public CLI consumer | Existing `--embodiment` argument | Set `choices=SUPPORTED_EMBODIMENTS`; no second literal list. |
| `easyuuv_nc/workflows/adapt.py` | Public CLI consumer | Existing `--embodiment` argument | Same tuple as training; application order unchanged. |
| `easyuuv_nc/env/assets/warpauv.py` | Shared USD resolution | Existing source-relative `USD_PATH` | Central helper returns resolved absolute path and asserts it stays under package root. |
| `workflows/qualify_easyuuv_v2.py` | Catalog report and server smoke writer | `workflows/play_controller.py` plus Phase 4 runbook pattern | `main(argv)` entry, explicit configuration choice, deterministic JSON, no shell interpolation. |
| `workflows/validate_easyuuv_v2_qualification.py` | Strict artifact gate | `workflows/validate_phase5_1_stability_summary.py` | `REQUIRED_FIELDS`, pure validation function, finite/bound checks, reason-coded `ValueError`, `main(argv)->int`, optional `--json`. |
| `tests/test_easyuuv_v2_catalog.py` | TDD for canonical truth | `tests/test_koopman_data.py`, source-contract tests | Valid expected matrix plus targeted failures; test public behavior, not private calls. |
| `tests/test_easyuuv_v2_qualification.py` | TDD for artifact validator | `tests/test_phase5_1_stability_validator.py` | `valid_summary`-style fixture; mutate one field per rejection test. |
| `docs/phase6_easyuuv_v2_qualification_runbook.md` | Local/server commands and pullback | Phase 4 PLAN/runbook conventions | Exact server setup, one process per config, output paths, validator command, evidence labels. |

## Concrete Existing Signatures

### Validator pattern

From `workflows/validate_phase5_1_stability_summary.py`:

```python
def validate_phase5_1_stability_summary(path: str | Path) -> dict[str, Any]:
    summary = _load_summary(path)
    _require_fields(summary)
    _require_expected_values(summary)
    _require_hard_health(summary)
    return {...}

def main(argv: list[str] | None = None) -> int:
    ...
```

Phase 6 should mirror this public shape:

```python
def validate_easyuuv_v2_qualification(
    path: str | Path,
    *,
    catalog_only: bool = False,
) -> dict[str, Any]:
    ...

def main(argv: list[str] | None = None) -> int:
    ...
```

### CLI error pattern

From `workflows/validate_koopman_log.py`:

```python
try:
    ...
except (OSError, ValueError) as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    return 1
```

Use the same non-zero CLI contract while keeping the pure validation function directly testable.

### TAM pattern

From the received `env/thrust_allocation.py`:

```python
class ThrusterLayout:
    @classmethod
    def from_specs(cls, specs): ...

def build_wrench_matrix(layout: ThrusterLayout) -> torch.Tensor: ...
def dof_weight_vector(controllable_dofs) -> torch.Tensor: ...
def allocate(B, wrench_cmd, mode="pinv", weight=None) -> torch.Tensor: ...
```

The new declared-rank helper should be a pure function accepting actual config data and returning an integer. Tests must derive the report from `EMBODIMENT_CONFIGS`, not copy thruster specs into fixtures.

### Test fixture pattern

From `tests/test_phase5_1_stability_validator.py`:

```python
def valid_summary(checkpoint: Path) -> dict:
    return {...}

def test_validator_rejects_specific_failure(tmp_path):
    payload = valid_summary(...)
    payload["one_field"] = bad_value
    with pytest.raises(ValueError, match="one_field"):
        validate(...)
```

Phase 6 uses one canonical valid eight-row payload and separate tests for duplicate/missing/extra configuration, wrong mask/rank/count, low step count, NaN/Inf, bounds, dimension mismatch and server-version provenance.

## Package and Import Constraints

- Tests that need only catalog/TAM must import `easyuuv_nc.embodiments` and `easyuuv_nc.thrust_allocation`; they must not import `EasyUUVEnvCfg`.
- Root `easyuuv_nc.__init__` may attempt gym registration, but it may only suppress missing `gymnasium` or `omni*` modules.
- The asset helper must resolve relative to the package root, not `Path.cwd()`.
- `pyproject.toml` should not package `source/`, `.planning/`, checkpoints or old top-level v1 modules.

## Plan Ownership Boundaries

### Plan 06-01 — package seam

Owns directory normalization, packaging, import probe and asset path. It must not extract catalog/TAM logic beyond what is necessary for import stability.

### Plan 06-02 — catalog/TAM TDD

Owns pure embodiment truth, TAM importability, CLI/environment consumers and topology tests. It must not implement artifact aggregation.

### Plan 06-03 — artifact validator TDD

Owns schema constants, strict validator/CLI and validator tests. It consumes catalog truth but does not start Isaac.

### Plan 06-04 — server smoke and evidence

Owns Isaac runner integration, runbook, server result merge, full regression commands and Phase 6 evidence handoff. It does not alter catalog semantics or v1 Koopman control dimensions.

## Anti-Patterns to Reject

- A second hard-coded eight-name list in qualification code.
- `count(results) == 8` without exact set equality.
- Raw quaternion RMSE or unrelated control metrics in Phase 6 qualification.
- Dynamic `importlib` aliasing from `easyuuv_v2-main` to `easyuuv_nc`.
- A local mock artifact labelled as server Isaac pass.
- A test that imports Isaac merely to read literal configuration metadata.
- A plan task that combines package rename, catalog design, validator and server execution into one commit.

---

## PATTERN MAPPING COMPLETE

The Phase 6 target files now have concrete existing analogs and non-overlapping plan ownership.
