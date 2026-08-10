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
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-phase6
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
git status --short
git rev-parse HEAD
git bundle create EasyUUV-phase6-v2.bundle v2.0-multi-configuration
git bundle verify EasyUUV-phase6-v2.bundle
scp .\EasyUUV-phase6-v2.bundle agentic-AUV:/root/EasyUUV-phase6-v2.bundle
```

The commit printed here is the expected server source commit. Do not create or
transfer the bundle until the local regression section has passed.

## Server Setup

Power on the unchanged `agentic-AUV` server only after local preflight passes.
The existing `/root/EASYkoopman` directory is read-only historical v1 state for
this phase. Use the isolated `/root/EASYkoopman-phase6-v2` checkout. The following
safe check intentionally stops if that isolated path already exists; inspect it
instead of deleting it.

```bash
test ! -e /root/EASYkoopman-phase6-v2
git bundle verify /root/EasyUUV-phase6-v2.bundle
git clone --branch v2.0-multi-configuration /root/EasyUUV-phase6-v2.bundle /root/EASYkoopman-phase6-v2
cd /root/EASYkoopman-phase6-v2
git status --short
git rev-parse HEAD
source /opt/conda/etc/profile.d/conda.sh
conda activate isaaclab
test "$(python -c 'from importlib.metadata import version; print(".".join(version("isaacsim").split(".")[:2]))')" = "5.0"
test "$(git -C /root/IsaacLab describe --tags --exact-match HEAD)" = "v2.2.1"
git -C /root/IsaacLab rev-parse HEAD
python -c 'from importlib.metadata import version; print("isaacsim_distribution="+version("isaacsim")); print("isaaclab_distribution="+version("isaaclab"))'
python -m pip install -e . --no-deps
python -c 'import easyuuv_nc; from easyuuv_nc.package_paths import EMBODIMENT_USD_PATH; assert EMBODIMENT_USD_PATH.is_file(); print(easyuuv_nc.__file__); print(EMBODIMENT_USD_PATH)'
mkdir -p source/results/koopman_phase6/rows source/results/koopman_phase6/logs source/results/koopman_phase6/exit_codes
git rev-parse HEAD | tee source/results/koopman_phase6/source_commit.txt
git -C /root/IsaacLab describe --tags --exact-match HEAD | tee source/results/koopman_phase6/isaaclab_repo_tag.txt
git -C /root/IsaacLab rev-parse HEAD | tee source/results/koopman_phase6/isaaclab_repo_commit.txt
```

The two `test` commands are blocking version gates. A missing exact tag, a dirty
or non-release ref, or a Sim version other than 5.0 stops qualification. The
runner separately records the installed `isaaclab` distribution version (known
to differ from the semantic IsaacLab release), exact repository tag and commit.

## Server Eight-Configuration Smoke

Remain in `/root/EASYkoopman-phase6-v2` with the `isaaclab` environment active.
Each invocation is a separate Isaac process. Preserve the JSON and log even when
the process exits nonzero. Bash `PIPESTATUS[0]` records the runner exit rather
than the `tee` exit.

```bash
python -u workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration base --steps 64 --seed 0 --num-envs 1 --headless --output-json source/results/koopman_phase6/rows/base.json 2>&1 | tee source/results/koopman_phase6/logs/base.log
printf '%s\n' "${PIPESTATUS[0]}" > source/results/koopman_phase6/exit_codes/base.txt

python -u workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration long_body --steps 8 --seed 0 --num-envs 1 --headless --output-json source/results/koopman_phase6/rows/long_body.json 2>&1 | tee source/results/koopman_phase6/logs/long_body.log
printf '%s\n' "${PIPESTATUS[0]}" > source/results/koopman_phase6/exit_codes/long_body.txt

python -u workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration heavy_moderate --steps 8 --seed 0 --num-envs 1 --headless --output-json source/results/koopman_phase6/rows/heavy_moderate.json 2>&1 | tee source/results/koopman_phase6/logs/heavy_moderate.log
printf '%s\n' "${PIPESTATUS[0]}" > source/results/koopman_phase6/exit_codes/heavy_moderate.txt

python -u workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration asymmetric --steps 8 --seed 0 --num-envs 1 --headless --output-json source/results/koopman_phase6/rows/asymmetric.json 2>&1 | tee source/results/koopman_phase6/logs/asymmetric.log
printf '%s\n' "${PIPESTATUS[0]}" > source/results/koopman_phase6/exit_codes/asymmetric.txt

python -u workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration uuv6 --steps 8 --seed 0 --num-envs 1 --headless --output-json source/results/koopman_phase6/rows/uuv6.json 2>&1 | tee source/results/koopman_phase6/logs/uuv6.log
printf '%s\n' "${PIPESTATUS[0]}" > source/results/koopman_phase6/exit_codes/uuv6.txt

python -u workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration uuv6_angled --steps 8 --seed 0 --num-envs 1 --headless --output-json source/results/koopman_phase6/rows/uuv6_angled.json 2>&1 | tee source/results/koopman_phase6/logs/uuv6_angled.log
printf '%s\n' "${PIPESTATUS[0]}" > source/results/koopman_phase6/exit_codes/uuv6_angled.txt

python -u workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration uuv4 --steps 8 --seed 0 --num-envs 1 --headless --output-json source/results/koopman_phase6/rows/uuv4.json 2>&1 | tee source/results/koopman_phase6/logs/uuv4.log
printf '%s\n' "${PIPESTATUS[0]}" > source/results/koopman_phase6/exit_codes/uuv4.txt

python -u workflows/qualify_easyuuv_v2.py --task EasyUUV-Direct-v1 --configuration uuv4_angled --steps 8 --seed 0 --num-envs 1 --headless --output-json source/results/koopman_phase6/rows/uuv4_angled.json 2>&1 | tee source/results/koopman_phase6/logs/uuv4_angled.log
printf '%s\n' "${PIPESTATUS[0]}" > source/results/koopman_phase6/exit_codes/uuv4_angled.txt
```

Do not continue to merge until all eight exit-code files contain `0`. The
underactuated `uuv4` configurations receive zero yaw excitation by construction.

## Merge and Validate

The merger requires exactly one row from every public configuration, identical
source/runtime provenance, and a strict server-mode validator pass before it
atomically replaces the final file.

```bash
python workflows/merge_easyuuv_v2_qualification.py \
  --input source/results/koopman_phase6/rows/base.json \
  --input source/results/koopman_phase6/rows/long_body.json \
  --input source/results/koopman_phase6/rows/heavy_moderate.json \
  --input source/results/koopman_phase6/rows/asymmetric.json \
  --input source/results/koopman_phase6/rows/uuv6.json \
  --input source/results/koopman_phase6/rows/uuv6_angled.json \
  --input source/results/koopman_phase6/rows/uuv4.json \
  --input source/results/koopman_phase6/rows/uuv4_angled.json \
  --output source/results/koopman_phase6/qualification.json 2>&1 | tee source/results/koopman_phase6/merge.log

python workflows/validate_easyuuv_v2_qualification.py source/results/koopman_phase6/qualification.json --json 2>&1 | tee source/results/koopman_phase6/validator.json
sha256sum source/results/koopman_phase6/qualification.json | tee source/results/koopman_phase6/qualification.sha256
```

The validator must exit 0 and report `server_pass` with a configuration count of
8. This normal final command intentionally does not use the local-only flag.

## Pullback and Hash

From local Windows PowerShell, copy the complete evidence directory, not only the
passing aggregate:

```powershell
scp -r agentic-AUV:/root/EASYkoopman-phase6-v2/source/results/koopman_phase6 source/results/
Get-FileHash -Algorithm SHA256 source\results\koopman_phase6\qualification.json
Get-Content source\results\koopman_phase6\qualification.sha256
.\.venv\Scripts\python.exe workflows\validate_easyuuv_v2_qualification.py source\results\koopman_phase6\qualification.json --json
```

The local SHA-256 must equal the server `qualification.sha256` value. Record both
the source commit and artifact SHA-256 in Phase 6 server evidence before closing
the phase.

## Failure Handling

- Preserve every partial row, nonzero exit code, runner log, merge log and
  validator output as failure evidence.
- Never omit a failed row, rename another row to replace it, edit values to pass,
  or merge fewer than the exact eight public configurations.
- Report Isaac Sim distribution drift, IsaacLab distribution drift, missing exact
  `v2.2.1` release provenance, dirty refs and repository commit drift explicitly.
- The same unchanged command may be retried once for an infrastructure-only
  interruption. A code, parameter or environment change requires a new local
  commit, a new fully tested Git bundle and a new eight-process run.
- Do not write `qualification_gate: pass`, create final Phase 6 verification, or
  begin Phase 7 until exact-eight server validation and pullback hash comparison
  both pass.
