# Phase 8 Koopman Identification Pilot Runbook

## Main Experiment D-23 Proposal

The two canonical proposal files are `protocols/phase8/main_role_assignment_protocol.json` and `protocols/phase8/analysis_policy.json`. Their status is `pending_d23`: they are a **pre-registered engineering design**, not a statistical optimality claim. No bundle, server collection, model fit or held-out test may begin until the user explicitly approves the exact current hashes.

The collection matrix covers `base`, `long_body`, `heavy_moderate`, `asymmetric`, `uuv6`, `uuv6_angled`, `uuv4` and `uuv4_angled`. Every configuration receives the same 12 whole episodes:

| Role | Episodes/config | Excitation families | Excitation seeds/family | Environment reset seeds by family | Length |
|---|---:|---|---|---|---:|
| fit | 6 | `independent_prbs`, `bounded_multisine`, `coupled_chirp` | 8201, 8202 | 9211/9212, 9221/9222, 9231/9232 | 512 |
| validation | 3 | same three | 8301 | 9311, 9321, 9331 | 512 |
| test | 3 | same three | 8401 | 9411, 9421, 9431 | 512 |

This is `8 × 12 × 512 = 49,152` transitions. `excitation_seed` controls only the deterministic bounded four-channel command. The separate environment `seed` is matched across configurations for the same role/family/repetition and controls reset/reference randomness; it is never reused across distinct family/repetition episode blocks. Main collection enforces `eval_mode=true`, no domain randomization, no sensor noise and no disturbance. Episode IDs, paths and roles are unique and disjoint from the pilot. The collector has no CLI flags that can override role, either seed, scenario, length or family.

The proposed analysis grid is fixed before the bytes exist:

| Item | Exact proposal |
|---|---|
| Fit-episode prefixes | `2, 4, 6` complete fit episodes/source configuration |
| Observables | `identity_v1`, `auv_kinematic_v1` |
| Ridge | `1e-8, 1e-6, 1e-4, 1e-2` |
| Normalization | `none`, `standard_v1` |
| Platform descriptors | `none`, `platform_physical_compact_v1`, `platform_physical_core_v1` |
| Rollout horizons | `5, 20, 60, full` without truth resets |
| Official orientation | sign-invariant SO(3) geodesic radians; invalid/projection events are reason-coded |
| Bootstrap | paired episode-block within configuration, fixed exact-eight configurations, equal-configuration macro, alpha `0.05`, seed `80304`, `2000` resamples; no broader platform-population inference |
| Aggregation | per-configuration, equal-configuration macro, worst configuration; row-weighted is diagnostic only |
| Gates | improvement `0.01`, conditional margin `0.05`, non-inferiority `0.10`, zero nonfinite/divergence/invalid-quaternion events |

Primary selection forbids reference, PWM, thruster mask, applied wrench, environment oracle/estimate, configuration identity and held-out statistics. The reference-conditioned diagnostic and held-out expert are explicitly non-promoting. Pilot health merely showed that real collection worked; it did not choose any value above.

Each outer fold holds out one complete configuration. Candidate selection and normalization read only the other seven configurations' fit/validation episodes. The selected primary model artifact must be fit and hash-frozen before the held-out test is opened; the held-out configuration is then used only for final scoring. The expert remains a separate non-promoting diagnostic namespace.

At D-23 the user either approves both exact SHA-256 values, or requests changes. A change creates a new experiment ID and requires a new commit plus the full preflight. Silence and earlier general approval do not count.

## Main Local Gate and Server Chain

Before D-23, run only:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\phase8_main_local_preflight.ps1
```

After explicit approval, the agent reruns that gate through `phase8_main_prepare_bundle.ps1`, verifies the offline bundle and hashes, transfers it, and runs in isolated `/root/EASYkoopman-phase8-main-v2`. `/root/IsaacLab` remains unchanged. The eight Isaac processes run serially by configuration; total time depends on server startup and simulation throughput, so the operational estimate is several hours rather than a guaranteed deadline.

The server will create inventory and LOCO split only after all exact 96 episodes, manifests and logs exist. Pullback stages and revalidates every byte before promoting into an absent `source/results/koopman_phase8_dataset` directory.

## Main Failure and Claim Boundary

Any interrupted, failed, partial, stale, role-drifted or provenance-mismatched run is `data_insufficient`. Resume means a **fresh experiment** in a new empty server directory; never append or patch a partial run. The main artifact supports the `dataset-not-model` claim only: dataset readiness does not prove an identified model, OOD transfer, selection, MPC or closed-loop effectiveness.

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
