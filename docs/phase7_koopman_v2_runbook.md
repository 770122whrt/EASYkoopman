# Phase 7 Koopman v2 Three-Topology Server Runbook

This runbook moves one clean, fully tested commit to the unchanged Isaac
server, collects three independent runtime episodes, and validates every byte
before canonical local promotion. The user only powers on the server when
asked. The agent connects, transfers, runs, diagnoses, and pulls evidence back.

## Evidence Levels

- `local_contract` proves pure schema, Bridge mocks, topology semantics, U=4
  dataset behavior, v1 non-promotion, and workflow failure handling.
- `server_isaac_smoke` is admitted only after the unchanged Isaac Sim 5.0 /
  Isaac Lab 2.2.1 runtime produces three real episodes at the tested commit.
- A JSON label alone is not origin proof. Native process, tee, semantic,
  runtime, source, log, hash, pullback, and strict-validator gates must agree.

## Local Preflight

From the repository root the agent runs exactly:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\phase7_local_preflight.ps1
```

This executes targeted Phase 7 tests, full collection with the committed
minimum, full pytest under a unique leaf of
`.pytest-tmp/phase7-full-suite`, compileall, pip check,
native shell parsing, diff/protected-path checks, a tracked plus unignored
untracked clean-tree check, and the canonical-evidence-absence check. Any
failure stops the handoff. No file under `source/results/koopman_phase7` exists
at this point.

## Offline Bundle

Only at the same clean committed HEAD, the agent runs:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\phase7_prepare_bundle.ps1
```

The prepare script calls the same local preflight first. It then creates
`.pytest-tmp/phase7-transfer/EasyUUV-phase7-v2.bundle`, verifies that it is a
complete bundle, writes the identical 40-hex HEAD to
`expected-source-commit.txt`, and exports the bootstrap from that commit.

When the server is powered on, the agent transfers the three files directly:

```powershell
scp .pytest-tmp/phase7-transfer/EasyUUV-phase7-v2.bundle agentic-AUV:/root/
scp .pytest-tmp/phase7-transfer/expected-source-commit.txt agentic-AUV:/root/
scp .pytest-tmp/phase7-transfer/phase7_server_bootstrap.sh agentic-AUV:/root/
```

## Server Bootstrap

The agent runs:

```powershell
ssh agentic-AUV "bash /root/phase7_server_bootstrap.sh"
```

The bootstrap rejects an existing target, verifies the complete bundle and
sidecar, clones to the new isolated `/root/EASYkoopman-phase7-v2`, and checks
server HEAD and the complete tracked/unignored tree before execution. It never
modifies `/root/IsaacLab` or any Phase 6 checkout/result.

## Server Three-Topology Smoke

`phase7_server_smoke.sh` uses `/root/IsaacLab/isaaclab.sh -p` for every Python
command and runs exactly three isolated processes: `base`, `uuv6`, and `uuv4`.
Each process performs create/reset and records at least 8 transitions. The
`uuv4` deterministic sequence includes nonzero raw yaw and the strict artifact
must contain zero post-mask virtual yaw.

Conceptually, each process runs this contract-bound command (the script fills
the configuration-specific paths and episode id):

```bash
/root/IsaacLab/isaaclab.sh -p -u workflows/collect_koopman_v2_smoke.py \
  --task EasyUUV-Direct-v1 --configuration base --steps 8 --seed 0 \
  --scenario phase7-server-smoke --episode-id phase7-base-<utc> --headless \
  --result-root source/results/koopman_phase7 \
  --output-jsonl source/results/koopman_phase7/episodes/base.jsonl \
  --output-manifest source/results/koopman_phase7/manifests/base.manifest.json \
  --failure-json source/results/koopman_phase7/failures/base.failure.json
```

The server first sources `/opt/conda/etc/profile.d/conda.sh`, activates the
locked `isaaclab` environment, and verifies that `python` resolves to
`/opt/conda/envs/isaaclab/bin/python` before any `isaaclab.sh -p` command. It
then records actual/expected runtime versions and validates the
unchanged Isaac Lab checkout against the Phase 6 lock: `VERSION=2.2.1`, fixed
repository HEAD and release-parent commit, the exact two dirty files, and the
binary patch SHA-256. The release tag is a provenance label; the server clone
does not need to contain a Git tag object. It then probes setuptools and
performs only an offline editable install using `--no-deps
--no-build-isolation --no-index`. Python status, tee status, and semantic
validation status are separate gates. A failed topology prevents merge.

## Merge/Validate/Hash

After all three topology gates pass, the script invokes:

```bash
/root/IsaacLab/isaaclab.sh -p workflows/merge_koopman_v2_evidence.py \
  --manifest source/results/koopman_phase7/manifests/base.manifest.json \
  --manifest source/results/koopman_phase7/manifests/uuv6.manifest.json \
  --manifest source/results/koopman_phase7/manifests/uuv4.manifest.json \
  --log base=source/results/koopman_phase7/logs/base.log \
  --log uuv6=source/results/koopman_phase7/logs/uuv6.log \
  --log uuv4=source/results/koopman_phase7/logs/uuv4.log \
  --output source/results/koopman_phase7/evidence.json --require-server
/root/IsaacLab/isaaclab.sh -p workflows/validate_koopman_v2.py \
  --aggregate source/results/koopman_phase7/evidence.json --json
```

The exact-three merger binds source commit, Isaac versions, runtime provenance,
episode/manifest/log hashes, and record counts. The validator independently
reopens all referenced bytes. `sha256sum` writes the aggregate and full file
inventory hashes.

## Pullback

The agent runs the tested local pullback command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\phase7_pullback.ps1
```

Pullback first requires local HEAD equal to the bundle sidecar and a completely
clean local tree. It copies into a fresh `.pytest-tmp/phase7-pullback-*` staging
directory, compares remote/local hashes and exact source/runtime/Lab
tag/HEAD/parent/patch/dirty-file sidecars, runs
the tested aggregate validator, and only then moves the staged directory into
canonical `source/results/koopman_phase7`. Existing canonical evidence is never
overwritten.

## Failure Handling

- Preflight or bundle failure: no bundle is created; correct and commit the
  source, then rerun the entire preflight.
- Server version/install failure: preserve `preflight_failure.txt` and logs;
  do not merge.
- Native, tee, telemetry, semantic, or topology failure: preserve the partial
  server tree outside canonical success; do not substitute local fixtures.
- SCP, sidecar, hash, validator, or promotion failure: preserve the unique
  staging directory for diagnosis; canonical evidence remains absent.
- Never reuse stale server results or an existing isolated checkout.

## Claim Boundary

A successful run proves schema/Bridge integration with real EasyUUV telemetry
for 8/6/4-thruster representatives. It does not prove Koopman effect,
cross-configuration prediction quality, held-out OOD performance, or MPC use of
4D virtual control. Those claims belong to later phases.
