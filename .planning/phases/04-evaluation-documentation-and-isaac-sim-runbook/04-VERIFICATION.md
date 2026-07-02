---
phase: 04-evaluation-documentation-and-isaac-sim-runbook
status: completed
verified: 2026-07-02
---

# Phase 4 Verification

## 1. Server Code Sync

Local code was packaged from `HEAD` and uploaded to the server because GitHub/TLS was unreliable:

```powershell
git archive --format=tar -o "$env:TEMP\easykoopman_phase4.tar" HEAD
scp -F "$env:USERPROFILE\.ssh\config" "$env:TEMP\easykoopman_phase4.tar" agentic-AUV:/tmp/easykoopman_phase4.tar
```

Server unpack and local-tool checks:

```bash
cd /root/EASYkoopman
tar -xf /tmp/easykoopman_phase4.tar
/opt/conda/envs/isaaclab/bin/python -m pytest -q tests/test_phase4_log_metrics.py tests/test_phase4_summary_workflow.py
/opt/conda/envs/isaaclab/bin/python -m compileall __init__.py easyuuv_env.py koopman workflows tests
/opt/conda/envs/isaaclab/bin/python -m pytest -q
```

Observed result:

```text
3 passed in 0.21s
compileall passed
70 passed in 0.98s
```

## 2. Isaac Evaluation Matrix

The following 9 runs completed on `agentic-AUV`:

```text
legacy_step_run01.jsonl
legacy_sine_run01.jsonl
legacy_irregular_run01.jsonl
direct_state_mpc_step_run01.jsonl
direct_state_mpc_sine_run01.jsonl
direct_state_mpc_irregular_run01.jsonl
paper_lifted_mpc_step_run01.jsonl
paper_lifted_mpc_sine_run01.jsonl
paper_lifted_mpc_irregular_run01.jsonl
```

Common run settings:

```text
num_envs = 1
trajectory_cycles = 2
steps_per_action = 100
mpc_horizon = 5
mpc_timeout_ms = 12
mpc_delta_pwm_limit = 0.35
headless = true
```

## 3. JSONL Validation

Command:

```bash
cd /root/EASYkoopman
for f in source/results/koopman_phase4/data/*.jsonl; do
  /opt/conda/envs/isaaclab/bin/python workflows/validate_koopman_log.py "$f" || exit 1
done
```

Observed result:

```text
9/9 logs passed validation
sample_count = 1400 for every log
state_dim = 11
reference_dim = 5
action_dim = 4
pwm_dim = 8
t_start = 0.016666667
t_end = 23.333333333
```

## 4. Metrics Generation

Command:

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python workflows/summarize_phase4_evaluation.py \
  --glob 'source/results/koopman_phase4/data/*.jsonl' \
  --output-json source/results/koopman_phase4/reports/metrics_summary.json \
  --output-md source/results/koopman_phase4/reports/metrics_summary.md
```

Observed result:

```text
Run count: 9
Eligible for Phase 4.5 baseline: yes
All runs have finite values
All PWM outputs are bounded
```

## 5. Artifact Pullback

Artifacts were copied back to:

```text
source/results/koopman_phase4/data/
source/results/koopman_phase4/reports/
source/results/koopman_phase4/run_logs/
```

Windows `scp` note:

```text
For paths with spaces, use the destination directory without a trailing backslash.
```

## 6. Acceptance Criteria Status

| Criterion | Status | Evidence |
|---|---|---|
| Run matrix names every expected artifact | pass | `docs/phase4_controller_evaluation_runbook.md` and this verification file |
| Server commands documented | pass | `docs/phase4_controller_evaluation_runbook.md` |
| Every JSONL validated | pass | 9/9 logs passed `validate_koopman_log.py` |
| Metrics run without Isaac imports | pass | local and server unit tests pass outside Isaac app startup |
| Metrics include required fields | pass | `metrics_summary.json` includes tracking, effort, smoothness, fallback, latency and PWM bounds |
| Paper-lifted comparison is explicit | pass | paper-lifted ran in all three trajectories but is not promoted |
| Runbook covers environment and copy-back | pass | runbook includes conda, `/root/IsaacLab`, manifests, validation and pullback |
| Phase 4.5 baseline defined | pass | `04-PHASE45-HANDOFF.md` |

## 7. Residual Risks

- Direct-state Koopman+MPC fallback and latency are still high, especially on irregular trajectories.
- Paper-lifted EDMD is valuable as a research comparison, but its depth RMSE makes it unsuitable as the default low-level controller.
- These are single-run Isaac results, not statistical confidence intervals.
- No real hardware or disturbed-fluid validation has been performed.
