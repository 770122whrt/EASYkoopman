# Phase 8 Exact-Eight Pilot Evidence

**Evidence date:** 2026-08-13

**Gate:** `pilot_health_gate: pass`

**Decision:** `collection_chain_ready`

**Qualification:** `server_isaac_identification_pilot`
**Scope:** collection-health only

## Execution Identity

The agent used explicit SSH identity `root@183.147.142.40:31348` with BatchMode and strict host-key checking. The successful pilot ran from the isolated server checkout `/root/EASYkoopman-phase8-pilot-v2` and was pulled into a fresh ignored staging directory before atomic promotion to `source/results/koopman_phase8_pilot`.

| Fact | Value |
|---|---|
| Tested local, bundle sidecar and server HEAD | `e7672fb54ca310797484ae5a6723bf1193ebaf0c` |
| Server collection window (UTC, file mtimes) | 2026-08-13T04:16:38.941Z to 2026-08-13T04:18:35.495Z |
| Server envelope mtime | 2026-08-13T04:18:38.283Z |
| Canonical server evidence root | `/root/EASYkoopman-phase8-pilot-v2/source/results/koopman_phase8_pilot` |
| Canonical server status root | `/root/EASYkoopman-phase8-pilot-v2/source/results/koopman_phase8_pilot_status` |
| Local canonical evidence root | `source/results/koopman_phase8_pilot` |
| Preserved failed target | `/root/EASYkoopman-phase8-pilot-v2-failed-f5de721-missing-logs` |
| Isaac Sim / Isaac Lab | `5.0` / `2.2.1` |
| Isaac Lab release tag / commit | `v2.2.1` / `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| Isaac Lab repository commit / parent | `c91a125c73c8b574878419a9583afc0b63b99f0a` / `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| Locked Isaac Lab patch SHA-256 | `d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079` |
| Server Python / setuptools | `/opt/conda/envs/isaaclab/bin/python3.11` / `80.9.0` |

The locked runtime dirty-file set was exactly `source/isaaclab_mimic/setup.py` and `source/isaaclab_rl/setup.py`. Each of the eight configuration processes recorded native status `0`, tee status `0`, and semantic status `pass`.

## Commands and Validation Chain

The server chain used the committed bootstrap and runner:

```text
bash /root/phase8_pilot_server_bootstrap.sh
/root/IsaacLab/isaaclab.sh -p scripts/phase8_pilot_server_run.sh
```

Pullback used committed `scripts/phase8_pilot_pullback.ps1` with the explicit remote, remote evidence/status roots, transfer directory, canonical directory and local `.venv` Python. The command copied into a fresh `.pytest-tmp/phase8-pilot-pullback-<uuid>` staging root; it did not write directly to canonical evidence. It then rechecked local HEAD/sidecar, every native/tee/semantic status, the self-excluding relative-path inventory, every SHA-256, source/runtime provenance, operational policy and external envelope before the atomic move.

Fresh local validation after promotion returned:

```text
validation_gate=phase8_pilot_operational_policy_valid
validation_gate=phase8_external_evidence_valid
qualification_level=server_isaac_identification_pilot
artifact_origin_level=server_isaac_smoke
referenced_file_count=51
warnings=[]
```

## Artifact Hashes

| Artifact | SHA-256 |
|---|---|
| `pilot_collection_policy.json` | `d437e3f3040714469951fcf50d9f3d9bd47a117f6b61c7236be545ba7402ab93` |
| Runtime provenance object | `21cfb69aafb3f04f338af6211cf87646176f49ab86abb2448f36702226f3a62a` |
| `pilot_inventory.json` | `d25d2fb3ba6d13284e1e03b30eeb8ac7d8d7d8350c1da432b1ba34e7810cab2d` |
| `pilot_health_decision.json` | `a26c05f597768c1b2eac375d89e771a84cfc6100d362cd599b27f02971279a3d` |
| `pilot_envelope.json` | `6052570ebf24f14d1ef39b057bd2aee8796ad7d5b7e5ffd70622778281b82155` |

The canonical root contains exactly 52 files: 16 JSONL episodes, 16 manifests, 16 logs, and the four pilot policy/inventory/decision/envelope JSON files. The envelope references and revalidates the 51 files other than itself.

## Exact 8 x 2 x 128 Inventory

Every episode contains exactly 128 contiguous strict `easyuuv-koopman-transition-v2` rows. Every row and manifest retains the Phase 7 origin `server_isaac_smoke`.

| Configuration | Policy / seed | Rows | Episode SHA-256 | Manifest SHA-256 | Log SHA-256 |
|---|---|---:|---|---|---|
| base | axis_pulse / 8101 | 128 | `15f560b173c3ef8dfac92e0fff439e7ae1681f09ac6b7846c45c3a3a8f0d291f` | `41a76f910384acff75c6319dce068053378ac3bce3796c84842564762fea2e03` | `c439f1a6ff7ada41ff81f2af6fc81e2a86605af1861eaa171224b8d7750e205a` |
| base | bounded_multisine / 8102 | 128 | `f94a897d92df4fe425efb955bff4aa16b96efb5a92b72772408e1d274700cfb3` | `4dea8c5314d368535f77cac3b0a1b011319f9735ab85555bd3f58af9f2240ce2` | `cfb1bb246921c4f4fc51bb9c15038ce3888f282398a7072bf53c683484b91b11` |
| long_body | axis_pulse / 8101 | 128 | `7bb784abcfd18e8ca59d6eca9a6a670e204d6e8392ad25cd1ea3bee03fc57f9d` | `4b557ff259580c772418a78161aa16de0b208a79eec004b10a8d30748a4cdfbe` | `2076323abdcb4693d229f7ac3c4d909cd17411d5ec183a693f5820a88d8e08c3` |
| long_body | bounded_multisine / 8102 | 128 | `66024270898b25563c7626dbe7e257293b146551a2229d99509fe02378a1f70f` | `5e0a5a8e97794f856c61ab822f8867d8ce2c19d4517b5bf2ddd9953c545699c9` | `cc6db5283bb43d2e5daf3fb4dddd97948e3b4291b25b82ca6c8dc6bad6e11e32` |
| heavy_moderate | axis_pulse / 8101 | 128 | `c75dee171de1a0b277d065549b53a85fea5426730c101d717e020dbd0481e833` | `80da3552cab94e17c03992bd0f8900bba15e33f8f48bfebfb36041052c2488bd` | `f03761b89d43ceea1f1a115fcaed1a6e69599d78f2d1f533e599a0b1c0445339` |
| heavy_moderate | bounded_multisine / 8102 | 128 | `0a64251b2a57ed853d945fe6f31d54842b25dce5454d30277b5b9b6dacc899f5` | `1969e1ea4732789031799a575374f8a7586c805e5761a3f2b77a3e50bbd25cc1` | `dd92c9eafb238ae7b67cb302f0eaf9590b57a4d914b0189439d2516a8834c54e` |
| asymmetric | axis_pulse / 8101 | 128 | `4a55845330a7dbd7c61a642ba5015654472b6a2ad31a861d677e35738f691c81` | `c954683bb40a6989e1b6a12d2d9c2a679e26678c88509513539846c99eb167e5` | `98ced682f75cc1d844072fbc428740f226d63b6252d3be3062bf15c0663bca22` |
| asymmetric | bounded_multisine / 8102 | 128 | `1990858af4c574fca9efe36288a0fa86af709ee9a85e16946d0f1099f4405883` | `db7bb9ec2cdb6f4d15b22aa525ba6596058d9eae0383d50cba287089a1463e72` | `3197ca662e456f600a33e5dcf0a1e865ffd5dbb147e69934c28a687152fc4595` |
| uuv6 | axis_pulse / 8101 | 128 | `8dd645bc326a2281d2ea96f6c32d141fcb801fe734ad023e5a48ed255dd2a71a` | `bf7aab486913fcb27b710e1079f56ba869246ac91e8df7f6f362715052c03b8e` | `0fa822c911a96586c71377b55f107b270af78d9328ae8c15b670f7bee64c8c0d` |
| uuv6 | bounded_multisine / 8102 | 128 | `11ec9fb2d72980711f20e902790ffa66bcee6f09b4233536133b7807a54293b3` | `c3b1b89cfaabc2b33d67e2a6a7ede9971382b4993ca9d606ddce92bfa1a29c40` | `b21da69545c80d1c6900b87491631f2c60639c9907186ec84d8cb3cfafeb3635` |
| uuv6_angled | axis_pulse / 8101 | 128 | `2384f944658ca4f641e3f20a7771bcd1f0fcd5ab5c0694840420390293076f50` | `b3eef29794505fb64d59c0c4c1c13b5c82c8dfb41198b07b0e4d95cfcc06f807` | `c2018acab64909eb9f8fa3ce14d5efa525b1120942c9c52e376e4e69ec22b020` |
| uuv6_angled | bounded_multisine / 8102 | 128 | `2322f62b8948f350ee4fa8d7fce3781c4968849bd94e7ddcc116a87a25efc149` | `1ff40ea4ccd6ea440059b48ac9e961d47be30ee00cc947043ef6691134415b59` | `d41a7a72c36512458c0f760d870f53548b1c536f1d4fdae3909d6ae1e7beb8db` |
| uuv4 | axis_pulse / 8101 | 128 | `a54fde3bddb2c7a8daf22de1f40d107c6365cbe89edc28dd583e31afba64e336` | `fc45704b42278d5d32901adb8c5bef7374ffc15f490628edc38be935f770f341` | `65eb5c52947b8914596f84d7ae4ccba1b66a555bd72be5fb2a4a10609e9690a9` |
| uuv4 | bounded_multisine / 8102 | 128 | `251343d56f4a40e2b200cc31a4003ee527a53eb8e6793fc484aa46a1f6e00a44` | `cc09fedf5465987172ab8be7732c8c269c68845e232f4f3bb0b2f59f67dfa0ef` | `37ed2377e4d3fd89e6f4aabb24f249e711a07ce1445117fade651f8fdcfc761f` |
| uuv4_angled | axis_pulse / 8101 | 128 | `9d09e2f1dfbf209a179e91070c3cab8c33172924484c6df2119f8707dcb4ea3b` | `3d598ca37f4151272eb21a26fc6c1f26d2a395b01efc034e710d7d009d17ca42` | `a767f3a3a19458fff876ca2961432fbd3afad7971c9684864b2fe043606928c0` |
| uuv4_angled | bounded_multisine / 8102 | 128 | `a40e6081857a3323468371472278ea55a1ab331999940f03ecccf54d2708425b` | `876be0632b972116aec5744ae238522f3270ee313c2c1ff357ea063fb9f9e480` | `0a2198f44b974ef6f047a4e9ca7bf3d2fd7e9455b3a5ec546d93ac0104c4c7f2` |

## Channel and Underactuation Health

All controllable virtual channels have both positive and negative predeclared excitation coverage. For each fully actuated configuration, the aggregate negative counts were `[87,79,78,78]` and positive counts were `[73,81,82,82]` across 256 transitions.

| Configuration | Raw-yaw nonzero | Virtual-yaw nonzero | Negative virtual counts | Positive virtual counts |
|---|---:|---:|---|---|
| uuv4 | 160 | 0 | `[87,79,0,78]` | `[73,81,0,82]` |
| uuv4_angled | 160 | 0 | `[87,79,0,78]` | `[73,81,0,82]` |

This is real-runtime evidence that the two underactuated configurations received nonzero raw-yaw probes while the catalog mask kept virtual yaw at zero before TAM allocation. It is not yaw-control-performance evidence.

## Failure History and Recovery

Two fail-closed attempts were preserved rather than relabelled as success:

1. Bundle verification initially ran outside an isolated Git context. RED commit `39a754e` reproduced it and GREEN fix `f5de721` verified the bundle in an isolated Git context.
2. The first successful simulation data run lacked final episode log artifacts. The failed target remains at `/root/EASYkoopman-phase8-pilot-v2-failed-f5de721-missing-logs`. RED commit `50f7ca5` reproduced the finalization defect and GREEN fix `e7672fb` finalized all 16 logs before inventory and envelope generation. The simulation was not rerun during pullback.

## Claim Boundary

Allowed conclusions:

- the exact-eight policy completed at this one tested source/runtime;
- all 16 policy episodes, manifests and logs are complete, contiguous and hash-revalidated;
- the collection chain is ready for a separately approved main protocol.

Disallowed conclusions:

- Koopman identifiability or model quality;
- feature, horizon, backend, rank or condition selection;
- prediction error, rollout performance or OOD generalization;
- MPC or closed-loop effectiveness.

No model, fit, rank, condition, prediction-error or rollout artifact exists in this pilot root. This artifact provides partial evidence toward KID-01 and KID-05 by proving collection/provenance health only; neither requirement is marked complete by Plan 08-01.
