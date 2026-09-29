# Phase 2: Offline Koopman Identification - Plan

**Spec:** `.planning/phases/02-offline-koopman-identification/02-SPEC.md`
**Target branch:** `isaaclab2-migration`
**Mode:** local-first, Isaac-free implementation

## Current Baseline

The server smoke log is valid:

```text
OK: 2 samples
state_dim=11 reference_dim=5 action_dim=4 pwm_dim=8
t_start=0.016666667 t_end=0.033333333
trajectory_types=step
controller_modes=legacy/Ssurface
```

This proves the data pipe works. It does not provide enough excitation for Koopman identification. Serious training needs longer logs, preferably step, sine and irregular.

## Repository Asset Decision

Track the EasyUUV USD assets in Git:

- `data/easyuuv/model.usd` (~46 MB)
- `data/easyuuv/Props/instanceable_meshes.usd` (~28 MB)

Rationale:

- Both files are below GitHub's 100 MB single-file limit.
- Server failures already showed that missing USD assets break Isaac before controller logic is reached.
- Keeping assets with code makes zip upload and branch sync less fragile.

Verification:

- `git status --short` shows both USD files tracked after commit.
- `assets/easyuuv.py` still points to `../data/easyuuv/model.usd`.
- Server clone or zip contains both USD files.

## Implementation Waves

### Wave 1: Offline Dataset And Fixtures

Create:

- `koopman/__init__.py`
- `koopman/dataset.py`
- `tests/fixtures/koopman_step_small.jsonl`
- dataset tests

Tasks:

- Load one or more JSONL paths through the existing `koopman_data.load_koopman_samples()`.
- Convert samples into arrays `X`, `U`, `R`, `Y`.
- Preserve metadata: sample count, source paths, `dt` estimate, trajectory types, controller modes.
- Reject empty datasets and schema-invalid logs.

Verification:

```powershell
python -m pytest tests\test_koopman_dataset.py -q
```

### Wave 2: Lifting And EDMD Core

Create:

- `koopman/lifting.py`
- `koopman/edmd.py`
- tests for deterministic features and synthetic linear recovery

Tasks:

- Implement configurable lifting with raw state/reference and optional simple nonlinear terms.
- Implement ridge-regression EDMD fit.
- Keep the first model small and understandable before adding richer features.

Verification:

```powershell
python -m pytest tests\test_koopman_lifting.py tests\test_koopman_edmd.py -q
```

### Wave 3: Model Save/Load And Prediction Evaluation

Create:

- `koopman/model.py`
- `koopman/evaluation.py`
- tests for artifact round-trip and metrics

Tasks:

- Save model matrices and metadata to a versioned artifact.
- Load artifact and reproduce predictions.
- Compute one-step RMSE and multi-step rollout RMSE.

Verification:

```powershell
python -m pytest tests\test_koopman_model.py tests\test_koopman_evaluation.py -q
```

### Wave 4: Local Workflow CLI

Create:

- `workflows/train_koopman.py`
- `workflows/evaluate_koopman.py`
- CLI tests or source-contract tests

Tasks:

- Train from JSONL logs without Isaac imports.
- Save model artifact under `source/results/koopman_models/`.
- Evaluate saved model against JSONL logs and write metrics JSON.

Verification:

```powershell
python workflows\train_koopman.py --help
python workflows\evaluate_koopman.py --help
python -m pytest -q
python -m compileall koopman workflows tests
```

## Server Data Collection Plan

The next server run should collect longer logs before real training:

```bash
cd /root/IsaacLab
WANDB_MODE=disabled ./isaaclab.sh -p /root/EASYkoopman/workflows/play_controller.py \
  --task EasyUUV-Direct-v1 \
  --num_envs 1 \
  --headless \
  --steps_per_action 200 \
  --koopman_log_path /root/EASYkoopman/source/results/koopman_phase1/koopman_step_long.jsonl
```

Then validate:

```bash
cd /root/EASYkoopman
python workflows/validate_koopman_log.py source/results/koopman_phase1/koopman_step_long.jsonl
```

For Phase 2 code implementation itself, Isaac is not required.

## Upload / Server Sync Policy

No server upload is needed for pure Phase 2 offline modules until you want to train or evaluate on server logs.

Server upload or pull is needed when any of these change:

- `easyuuv_env.py`
- `assets/easyuuv.py`
- `data/easyuuv/**/*.usd`
- `workflows/play_controller.py`
- trajectory collection workflows
- task registration or Isaac compatibility modules

If the next patch is only `koopman/*.py`, tests and local CLI, you can keep working locally and train with copied JSONL logs. If the patch touches Isaac workflow files or USD assets, package/pull to the server before rerunning Isaac.

## Expected End State

At the end of Phase 2:

- A validated JSONL dataset can be converted into training matrices.
- A Koopman/EDMD model can be trained offline.
- The model can be saved, loaded and evaluated.
- One-step and multi-step prediction metrics are available.
- Phase 3 can consume the saved model to build the Koopman+MPC controller.

