---
phase: 04-evaluation-documentation-and-isaac-sim-runbook
status: completed
created: 2026-07-02
target_branch: isaaclab2-migration
type: implementation
wave_count: 5
requirements: [EVAL-01, EVAL-02, DOC-01, DOC-02]
---

# Phase 4: Evaluation, Documentation And Isaac Sim Runbook - Plan

**Spec:** `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-SPEC.md`
**Context:** `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-CONTEXT.md`
**Research:** `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-RESEARCH.md`
**Mode:** local metrics tooling plus server Isaac experiments
**Primary outputs:** `source/results/koopman_phase4/` and Phase 4 docs
**Completed:** 2026-07-02

## Purpose

Create a reproducible controller-only evaluation baseline before PPO is reintroduced.

Phase 4 should answer:

```text
Under the same scripted references, how do legacy control, direct-state Koopman+MPC
and paper-lifted Koopman+MPC compare on tracking, effort, smoothness, fallback and latency?
```

## Wave 0: Planning Contract

Files:

- Create: `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-SPEC.md`
- Create: `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-CONTEXT.md`
- Create: `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-RESEARCH.md`
- Create: `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-PLAN.md`
- Update if needed: `.planning/ROADMAP.md`
- Update if needed: `.planning/STATE.md`

Verification:

```powershell
git diff --check
```

Acceptance:

- Phase 4 is explicitly controller-only.
- Phase 4.5 remains the PPO/RL adapter phase.
- PPO and LLM are out of scope for Phase 4.

## Wave 1: Local Metrics Aggregation

Files likely to create:

- `koopman/evaluation_logs.py`
- `workflows/summarize_phase4_evaluation.py`
- `tests/test_phase4_log_metrics.py`
- `tests/test_phase4_summary_workflow.py`

Implementation contract:

1. Read one or more Koopman JSONL logs with `koopman_data.load_koopman_samples()`.
2. Compute per-log metrics:

```text
sample_count
trajectory_type
controller_mode
backend_used
depth_rmse
attitude_angle_rmse
mean_pwm_l2
mean_pwm_abs
pwm_saturation_rate
mean_delta_pwm_l2
max_delta_pwm_l2
fallback_rate
status_counts
mean_latency_ms
max_latency_ms
latency_budget_violation_rate
pwm_min
pwm_max
pwm_bounded
nonfinite_count
```

3. Compute attitude error with quaternion sign equivalence:

```text
2 * acos(abs(dot(q_state, q_reference)))
```

4. Write:

```text
source/results/koopman_phase4/reports/metrics_summary.json
source/results/koopman_phase4/reports/metrics_summary.md
```

Expected local command:

```powershell
python workflows\summarize_phase4_evaluation.py `
  --logs source\results\koopman_phase4\data\legacy_step_run01.jsonl `
         source\results\koopman_phase4\data\direct_state_mpc_step_run01.jsonl `
         source\results\koopman_phase4\data\paper_lifted_mpc_step_run01.jsonl `
  --output-json source\results\koopman_phase4\reports\metrics_summary.json `
  --output-md source\results\koopman_phase4\reports\metrics_summary.md
```

Acceptance:

- Unit tests cover legacy logs without solver diagnostics and Koopman logs with solver diagnostics.
- Metrics workflow runs without importing Isaac.
- Output JSON is deterministic enough for tests.
- Output Markdown contains a table grouped by trajectory and controller.

## Wave 2: Server Evaluation Matrix

Create a Phase 4 runbook section or standalone document:

- `docs/phase4_controller_evaluation_runbook.md`

Default server setup:

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab
mkdir -p /root/EASYkoopman/source/results/koopman_phase4/data
cd /root/IsaacLab
```

Manifest paths:

```bash
DIRECT_MANIFEST=/root/EASYkoopman/source/results/koopman_phase2_5_verify_20260701_231802/selected_model_manifest.json
PAPER_MANIFEST=/root/EASYkoopman/source/results/koopman_phase3_5/paper_lifted_manifest.json
```

Legacy command shape:

```bash
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --controller_mode legacy \
  --trajectory_type step \
  --trajectory_cycles 2 \
  --steps_per_action 100 \
  --koopman_log_path /root/EASYkoopman/source/results/koopman_phase4/data/legacy_step_run01.jsonl
```

Direct-state command shape:

```bash
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --controller_mode koopman_mpc \
  --koopman_manifest_path "$DIRECT_MANIFEST" \
  --mpc_horizon 5 \
  --mpc_timeout_ms 12 \
  --trajectory_type step \
  --trajectory_cycles 2 \
  --steps_per_action 100 \
  --koopman_log_path /root/EASYkoopman/source/results/koopman_phase4/data/direct_state_mpc_step_run01.jsonl
```

Paper-lifted command shape:

```bash
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --controller_mode koopman_mpc \
  --koopman_manifest_path "$PAPER_MANIFEST" \
  --mpc_horizon 5 \
  --mpc_timeout_ms 12 \
  --trajectory_type step \
  --trajectory_cycles 2 \
  --steps_per_action 100 \
  --koopman_log_path /root/EASYkoopman/source/results/koopman_phase4/data/paper_lifted_mpc_step_run01.jsonl
```

Repeat each command with:

```text
trajectory_type = sine
trajectory_type = irregular
```

Acceptance:

- Runbook names all nine target logs.
- If paper-lifted is skipped, runbook records the skip reason and still runs legacy/direct-state.
- Commands use the same `trajectory_cycles`, `steps_per_action`, horizon and timeout for matched comparisons.

## Wave 3: Server Validation And Artifact Pullback

Server validation commands:

```bash
cd /root/EASYkoopman
python workflows/validate_koopman_log.py source/results/koopman_phase4/data/legacy_step_run01.jsonl
python workflows/validate_koopman_log.py source/results/koopman_phase4/data/direct_state_mpc_step_run01.jsonl
python workflows/validate_koopman_log.py source/results/koopman_phase4/data/paper_lifted_mpc_step_run01.jsonl
```

For full matrix validation:

```bash
for f in source/results/koopman_phase4/data/*.jsonl; do
  python workflows/validate_koopman_log.py "$f" || exit 1
done
```

Local pullback options:

```powershell
scp -F "$env:USERPROFILE\.ssh\config" agentic-AUV:/root/EASYkoopman/source/results/koopman_phase4/data/*.jsonl `
  "E:\code for project\Agentic AUV\EasyUUV\source\results\koopman_phase4\data\"
```

Acceptance:

- All included logs pass validation.
- Pullback path is documented.
- Failed or partial logs are excluded from the final summary unless marked as failure evidence.

## Wave 4: Run Metrics And Write Summary

Expected local command:

```powershell
python workflows\summarize_phase4_evaluation.py `
  --glob "source/results/koopman_phase4/data/*.jsonl" `
  --output-json source/results/koopman_phase4/reports/metrics_summary.json `
  --output-md source/results/koopman_phase4/reports/metrics_summary.md
```

Files likely to create:

- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-SUMMARY.md`
- `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-VERIFICATION.md`
- `source/results/koopman_phase4/reports/phase45_handoff.md`

Summary must state:

```text
which controllers ran
which trajectories ran
which logs validated
which metrics were generated
whether paper_lifted_edmd was included
fallback/latency limitations
recommended Phase 4.5 PPO baseline
```

Acceptance:

- Summary distinguishes smoke/evaluation evidence from performance superiority claims.
- Phase 4.5 handoff names the baseline controller and logs PPO should compare against.
- Limitations are explicit.

## Wave 5: Final Verification And Commit

Local verification:

```powershell
python -m pytest -q
python -m compileall __init__.py easyuuv_env.py koopman workflows tests
git diff --check
```

Server verification:

```bash
cd /root/EASYkoopman
/opt/conda/envs/isaaclab/bin/python -m pytest -q
/opt/conda/envs/isaaclab/bin/python -m compileall __init__.py easyuuv_env.py koopman workflows tests
```

Isaac validation:

```bash
cd /root/EASYkoopman
for f in source/results/koopman_phase4/data/*.jsonl; do
  python workflows/validate_koopman_log.py "$f" || exit 1
done
```

Commit plan:

```text
docs(04): plan controller evaluation phase
test(04): cover phase4 metrics aggregation
feat(04): add phase4 evaluation summary workflow
docs(04): add Isaac evaluation runbook
docs(04): summarize controller evaluation baseline
```

## Success Statement

Recommended Phase 4 success wording:

```text
Phase 4 produced a reproducible controller-only Isaac evaluation baseline.
It compared legacy, direct-state Koopman+MPC and eligible paper-lifted
Koopman+MPC under matched scripted references, generated local metrics from
validated JSONL logs, documented the server runbook and handed Phase 4.5 a
clean PPO integration baseline.
```

## Completion Evidence

Phase 4 completed on the `agentic-AUV` Isaac server and the local workstation on 2026-07-02.

- Server matrix: 9/9 runs completed for `legacy`, `direct_state_mpc` and `paper_lifted_mpc` across `step`, `sine` and `irregular`.
- Log validation: all 9 JSONL logs passed `workflows/validate_koopman_log.py` with `state_dim=11`, `reference_dim=5`, `action_dim=4` and `pwm_dim=8`.
- Metrics report: `source/results/koopman_phase4/reports/metrics_summary.json` and `.md` generated.
- Main result: legacy remains the most stable controller-only baseline; direct-state Koopman+MPC is runnable but fallback/latency need reduction; paper-lifted EDMD is included as a paper-style comparison backend but is not ready to replace direct-state for depth control.
- Handoff: `.planning/phases/04-evaluation-documentation-and-isaac-sim-runbook/04-PHASE45-HANDOFF.md`.
