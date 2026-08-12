# Phase 8 Koopman Identification Pilot Runbook

## Evidence Vocabulary

Every transition keeps the frozen Phase 7 origin `server_isaac_smoke`. Phase 8 uses a separate external envelope whose `qualification_level` may be `server_isaac_identification_pilot` only after the independent validator re-reads every referenced byte. A local builder can emit only `local_contract`.

## Pilot Policy

`protocols/phase8/pilot_collection_policy.json` is immutable collection intent: 8 configurations, 2 episodes per configuration and 128 transitions per episode. `axis_pulse` uses seed 8101 and `bounded_multisine` uses seed 8102. Raw commands are bounded by 0.25. The file has no collected hashes or model results and its hash must predate every pilot episode.

## Local Pilot Preflight

From the repository root the agent runs:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\phase8_pilot_local_preflight.ps1
```

The command runs Phase 8 targeted tests, full collection/full pytest, compileall, `pip check`, native Bash/PowerShell parsing, protected-diff checks, clean tracked+untracked status and canonical pilot absence at one committed HEAD.

## Offline Bundle

After the clean preflight, the agent runs:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\phase8_pilot_prepare_bundle.ps1
```

The output is `.pytest-tmp/phase8-pilot-transfer/EasyUUV-phase8-pilot-v2.bundle`, a verified branch head, `expected-source-commit.txt` and an LF bootstrap script. The sidecar must equal the tested HEAD.

## Server Exact-Eight Pilot

The user only powers on and confirms the unchanged server is SSH-reachable. The agent performs SCP, SSH and every server command. The agent transfers the three bundle files to `/root`, then runs:

```bash
bash /root/phase8_pilot_server_bootstrap.sh
```

The bootstrap creates only `/root/EASYkoopman-phase8-pilot-v2`, checks the exact commit and clean checkout, and calls the server runner. The runner uses `/root/IsaacLab/isaaclab.sh -p`, unchanged Isaac Sim 5.0 / Isaac Lab 2.2.1, offline install flags, and one process per configuration. Each process resets and collects its two policy episodes independently.

## Pilot Health Audit

All 16 episodes must have exactly 128 contiguous strict rows, one manifest and complete log/status evidence. The model-free auditor checks exact inventory, source/runtime agreement, bounded signed coverage on every controllable channel, and nonzero raw yaw with zero virtual yaw for both `uuv4*` configurations. It writes `pilot_inventory.json`, `pilot_health_decision.json` and `pilot_envelope.json` atomically only after all inputs pass.

## Pullback

The agent runs:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\phase8_pilot_pullback.ps1
```

Pullback requires the same clean local HEAD and sidecar, retrieves native/tee/semantic status and evidence into a fresh staging root, verifies exact file inventory/hash/source/runtime and runs the tested local envelope validator. Only then may it atomically move the staging directory to the previously absent `source/results/koopman_phase8_pilot` root.

## Failure Handling

Any failed configuration, missing/extra/stale episode, policy/source/runtime/log/hash mismatch, modeling output, SCP failure or validator failure yields `pilot_insufficient`. Failure evidence stays outside canonical success and the checkpoint remains open. Never replace a failed episode, reuse an old canonical directory, relax a validator or fabricate a pass.

## Main Protocol Checkpoint

Pilot health does not approve the main experiment. A later checkpoint presents and freezes the exact main role/action matrix and analysis policy before main collection. Pilot trajectories never choose model feature, horizon, backend, rank/condition threshold or prediction gate.

## Claim Boundary

A pass proves collection health for the exact eight configurations at one tested source/runtime. It does not prove identification, does not prove OOD prediction, and does not prove MPC or closed-loop effectiveness. No fit, model, feature, horizon, rank, condition, prediction-error or rollout output belongs in the pilot artifact.
