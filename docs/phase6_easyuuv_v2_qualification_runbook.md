# Phase 6 EasyUUV v2 Qualification Runbook

This runbook qualifies the eight public EasyUUV v2 configurations without
modifying the frozen v1 repository or its evidence. Run every local gate before
powering on the Isaac server. The server checkout is transferred as a Git bundle
because the server is not expected to have reliable GitHub access.

## Evidence Levels

- `local_contract` proves package, catalog, topology, schema, CLI and regression
  behavior without starting Isaac. It is useful preflight evidence only.
- `server_isaac_smoke` is written only by a real process launched in the target
  Isaac Sim/Isaac Lab environment. It records actual post-step PID and clipped
  motor telemetry.

The levels are not interchangeable. A local fixture, catalog-only validation,
mock row, copied console statement or manually edited JSON cannot satisfy the
server gate. The final phase result remains open until the pulled server artifact
and its hash pass the normal validator without `--catalog-only`.

## Local Preflight

Run from a clean checkout of `v2.0-multi-configuration` in the repository root.
On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import easyuuv_nc; from easyuuv_nc.package_paths import EMBODIMENT_USD_PATH; assert EMBODIMENT_USD_PATH.is_file(); print(easyuuv_nc.__file__); print(EMBODIMENT_USD_PATH)"
.\.venv\Scripts\python.exe -m pytest -q tests\test_easyuuv_v2_package.py tests\test_easyuuv_v2_catalog.py tests\test_easyuuv_v2_qualification.py tests\test_easyuuv_v2_qualification_runner.py
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp/phase6-full-suite
.\.venv\Scripts\python.exe -m compileall __init__.py easyuuv_env.py koopman workflows tests easyuuv_nc
git diff --check
git diff v1.0 -- .planning/milestones .planning/reports koopman/model.py koopman/mpc.py
```

Generate and validate a local-only catalog artifact. This file deliberately has
empty actual runtime versions and zero physics steps:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import json; from easyuuv_nc.embodiments import SUPPORTED_EMBODIMENTS,qualification_record; from workflows.easyuuv_v2_qualification_artifact import QUALIFICATION_SCHEMA_VERSION,LOCAL_EVIDENCE_LEVEL,EXPECTED_ISAAC_SIM_VERSION,EXPECTED_ISAAC_LAB_VERSION,EXPECTED_TASK_ID; rows=[{'configuration':n,'thruster_count':r['thruster_count'],'control_channels':list(r['control_channels']),'control_mask':list(r['control_mask']),'declared_control_rank':r['declared_control_rank'],'environment_created':False,'reset_passed':False,'steps_completed':0,'action_min':0.0,'action_max':0.0,'motor_min':0.0,'motor_max':0.0,'motor_vector_length':r['thruster_count'],'nonfinite_count':0,'dimension_mismatch_count':0,'seed':0,'status':'pass','reason_codes':[]} for n in SUPPORTED_EMBODIMENTS for r in [qualification_record(n)]]; p={'schema_version':QUALIFICATION_SCHEMA_VERSION,'evidence_level':LOCAL_EVIDENCE_LEVEL,'expected_isaac_sim':EXPECTED_ISAAC_SIM_VERSION,'expected_isaac_lab':EXPECTED_ISAAC_LAB_VERSION,'actual_isaac_sim':'','actual_isaac_lab':'','task_id':EXPECTED_TASK_ID,'source_commit':'0'*40,'results':rows}; out=Path('.pytest-tmp/phase6-local-contract.json'); out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(p,allow_nan=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')"
.\.venv\Scripts\python.exe workflows\validate_easyuuv_v2_qualification.py .pytest-tmp\phase6-local-contract.json --catalog-only --json
```

Expected result: `qualification_gate` is `local_contract_pass`. Do not copy this
file into `source/results/koopman_phase6` and do not call it physics evidence.

After all local gates pass, create the offline delivery bundle and verify it:

```powershell
.\scripts\phase6_prepare_bundle.ps1
scp .\.pytest-tmp\phase6-transfer\EasyUUV-phase6-v2.bundle agentic-AUV:/root/EasyUUV-phase6-v2.bundle
if ($LASTEXITCODE -ne 0) { throw "bundle_scp_failed:$LASTEXITCODE" }
scp .\.pytest-tmp\phase6-transfer\expected-source-commit.txt agentic-AUV:/root/expected-source-commit.txt
if ($LASTEXITCODE -ne 0) { throw "commit_sidecar_scp_failed:$LASTEXITCODE" }
scp .\.pytest-tmp\phase6-transfer\phase6_server_bootstrap.sh agentic-AUV:/root/phase6_server_bootstrap.sh
if ($LASTEXITCODE -ne 0) { throw "bootstrap_scp_failed:$LASTEXITCODE" }
```

The helper rejects tracked source drift and proves current branch tip = tested
HEAD = bundle branch ref = `expected-source-commit.txt`. It extracts the server
bootstrap from that exact Git commit, rather than copying a potentially modified
working-tree script. Do not create or transfer this directory until every local
regression gate has passed.

## Server Setup

Power on the unchanged `agentic-AUV` server only after local preflight passes.
The existing `/root/EASYkoopman` directory is read-only historical v1 state for
this phase. Use the isolated `/root/EASYkoopman-phase6-v2` checkout. The following
bootstrap intentionally stops if that isolated path already exists; inspect it
instead of deleting it. Run exactly one entry point:

```bash
bash /root/phase6_server_bootstrap.sh
```

Both scripts use `set -Eeuo pipefail`. The bootstrap verifies the bundle ref and
sidecar, clones once, requires exact server HEAD and a completely clean clone,
then delegates to the committed qualification script. That script rechecks
tracked source state, activates the existing `isaaclab` Conda environment, and
then uses `/root/IsaacLab/isaaclab.sh -p` for every Python process. It pins Isaac
Sim `5.0` and the unchanged server's exact IsaacLab state:

- `VERSION=2.2.1` and release tag identity `v2.2.1`;
- official release commit
  `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20`;
- server HEAD `c91a125c73c8b574878419a9583afc0b63b99f0a`, whose commit-object
  parent is that release commit and whose only code change is the official
  ground-plane visibility fix;
- exactly two pre-existing setup-file proxy rewrites and binary-diff SHA-256
  `d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079`;
- no staged or untracked IsaacLab files.

The upstream release and post-release commit are independently inspectable at
<https://github.com/isaac-sim/IsaacLab/releases/tag/v2.2.1> and
<https://github.com/isaac-sim/IsaacLab/commit/c91a125c73c8b574878419a9583afc0b63b99f0a>.
The script does not create a tag, clean the repository, edit the Conda
environment, or modify `/root/IsaacLab`. It proves all four Gym registrations
after AppLauncher, runs all eight processes, and records both the runner and
`tee` exit status under `exit_codes/` and `log_exit_codes/`. A failed runner or
failed log capture blocks merge; only then may the script validate and hash the
aggregate. Any failed gate stops all later stages.

## Server Eight-Configuration Smoke

The bootstrap above executes this exact matrix through the committed helper.
The explicit commands below are an auditable reference, not an alternate manual
workflow. Each invocation is a separate Isaac process. The helper preserves JSON,
log and `PIPESTATUS[0]` for every configuration and refuses to merge if any is
nonzero.

The machine helper first runs:

```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab
```

```bash
/root/IsaacLab/isaaclab.sh -p -u /root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration base --steps 64 --seed 0 --num-envs 1 --headless --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 --output-json /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/base.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/logs/base.log
printf '%s\n' "${PIPESTATUS[0]}" > /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/exit_codes/base.txt

/root/IsaacLab/isaaclab.sh -p -u /root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration long_body --steps 8 --seed 0 --num-envs 1 --headless --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 --output-json /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/long_body.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/logs/long_body.log
printf '%s\n' "${PIPESTATUS[0]}" > /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/exit_codes/long_body.txt

/root/IsaacLab/isaaclab.sh -p -u /root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration heavy_moderate --steps 8 --seed 0 --num-envs 1 --headless --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 --output-json /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/heavy_moderate.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/logs/heavy_moderate.log
printf '%s\n' "${PIPESTATUS[0]}" > /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/exit_codes/heavy_moderate.txt

/root/IsaacLab/isaaclab.sh -p -u /root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration asymmetric --steps 8 --seed 0 --num-envs 1 --headless --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 --output-json /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/asymmetric.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/logs/asymmetric.log
printf '%s\n' "${PIPESTATUS[0]}" > /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/exit_codes/asymmetric.txt

/root/IsaacLab/isaaclab.sh -p -u /root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration uuv6 --steps 8 --seed 0 --num-envs 1 --headless --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 --output-json /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/uuv6.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/logs/uuv6.log
printf '%s\n' "${PIPESTATUS[0]}" > /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/exit_codes/uuv6.txt

/root/IsaacLab/isaaclab.sh -p -u /root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration uuv6_angled --steps 8 --seed 0 --num-envs 1 --headless --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 --output-json /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/uuv6_angled.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/logs/uuv6_angled.log
printf '%s\n' "${PIPESTATUS[0]}" > /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/exit_codes/uuv6_angled.txt

/root/IsaacLab/isaaclab.sh -p -u /root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration uuv4 --steps 8 --seed 0 --num-envs 1 --headless --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 --output-json /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/uuv4.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/logs/uuv4.log
printf '%s\n' "${PIPESTATUS[0]}" > /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/exit_codes/uuv4.txt

/root/IsaacLab/isaaclab.sh -p -u /root/EASYkoopman-phase6-v2/workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration uuv4_angled --steps 8 --seed 0 --num-envs 1 --headless --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 --output-json /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/uuv4_angled.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/logs/uuv4_angled.log
printf '%s\n' "${PIPESTATUS[0]}" > /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/exit_codes/uuv4_angled.txt
```

Do not continue to merge until all eight exit-code files contain `0`. The
underactuated `uuv4` configurations receive zero yaw excitation by construction.

## Merge and Validate

The merger requires exactly one row from every public configuration, identical
source/runtime provenance, and a strict server-mode validator pass before it
atomically replaces the final file.

```bash
/root/IsaacLab/isaaclab.sh -p /root/EASYkoopman-phase6-v2/workflows/merge_easyuuv_v2_qualification.py \
  --input /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/base.json \
  --input /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/long_body.json \
  --input /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/heavy_moderate.json \
  --input /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/asymmetric.json \
  --input /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/uuv6.json \
  --input /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/uuv6_angled.json \
  --input /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/uuv4.json \
  --input /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/rows/uuv4_angled.json \
  --result-root /root/EASYkoopman-phase6-v2/source/results/koopman_phase6 \
  --output /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/qualification.json 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/merge.log

/root/IsaacLab/isaaclab.sh -p /root/EASYkoopman-phase6-v2/workflows/validate_easyuuv_v2_qualification.py /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/qualification.json --json --expected-source-commit-file /root/expected-source-commit.txt --expected-isaaclab-commit-file /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/isaaclab_repo_commit.txt --expected-isaaclab-release-file /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/isaaclab_release_tag.txt --expected-isaaclab-release-commit-file /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/isaaclab_release_commit.txt --expected-isaaclab-patch-sha256-file /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/isaaclab_repo_patch.sha256 --expected-isaaclab-dirty-files-file /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/isaaclab_repo_dirty_files.txt 2>&1 | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/validator.json
sha256sum /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/qualification.json | tee /root/EASYkoopman-phase6-v2/source/results/koopman_phase6/qualification.sha256
```

The validator must exit 0 and report `server_pass` with a configuration count of
8. This normal final command intentionally does not use the local-only flag.

## Pullback and Hash

From local Windows PowerShell, use the fail-closed pullback helper:

```powershell
.\scripts\phase6_pullback.ps1
```

The helper allocates a never-reused staging directory, checks native `scp` and
validator exit codes, parses the single server SHA-256 line, computes and compares
the local SHA-256, checks pulled `source_commit.txt` against the locally tested
sidecar, binds the public strict validator to both source and IsaacLab commits,
and only then promotes the staged directory to `source/results/koopman_phase6`.
It refuses to overwrite an existing canonical evidence directory. Record the
source commit and equal artifact SHA-256 in Phase 6 evidence before closing.

## Failure Handling

- Preserve every partial row, nonzero exit code, runner log, merge log and
  validator output as failure evidence.
- Never omit a failed row, rename another row to replace it, edit values to pass,
  or merge fewer than the exact eight public configurations.
- Report Isaac Sim distribution drift, Conda activation drift, IsaacLab
  distribution/VERSION drift, release-parent drift, repository HEAD drift,
  proxy-patch hash drift, or any extra staged/untracked file explicitly.
- The same unchanged command may be retried once for an infrastructure-only
  interruption. A code, parameter or environment change requires a new local
  commit, a new fully tested Git bundle and a new eight-process run.
- Do not write `qualification_gate: pass`, create final Phase 6 verification, or
  begin Phase 7 until exact-eight server validation and pullback hash comparison
  both pass.
