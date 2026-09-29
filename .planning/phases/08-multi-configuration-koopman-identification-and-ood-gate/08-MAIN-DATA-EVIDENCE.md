# Phase 8 Main Identification Dataset Evidence

**Evidence scope:** real-server main identification dataset readiness only

**Qualification:** `server_isaac_identification_dataset`

**Experiment ID:** `phase8-main-identification-v2-proposal`

**Successful source commit:** `a7e819848ffc1c621fbeeff971063f1cdbeac0b3`

**Server completion:** `2026-08-29T14:19:54Z`

**Canonical local root:** `source/results/koopman_phase8_dataset/`

## D-23 frozen inputs

The user explicitly approved the following exact file bytes before the successful
main collection. The protocol files were not edited after approval, so the JSON
field `approval_status=pending_d23` remains part of the approved immutable bytes;
approval is recorded externally here rather than by changing either frozen file.

| Frozen artifact | Approved SHA-256 |
|---|---|
| `protocols/phase8/main_role_assignment_protocol.json` | `499b79089a4bfb0769ce6a902ad676f09e9c64190069a0bf5b51cd76f1d6cf26` |
| `protocols/phase8/analysis_policy.json` | `4083e6ef7c63aaf44c0eba98e13b40ceb8d6387ef818d3f90a88ac96aa6d0090` |

The successful server checkout, inventory and envelope all bind source commit
`a7e819848ffc1c621fbeeff971063f1cdbeac0b3`. The final offline bundle SHA-256 was
`50417e356c19e31f46e4674a5a1440834ab3954e17db09c42334e1cdab0708e5`.

## Commands and gates

The successful attempt used the tested operational chain:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\phase8_main_prepare_bundle.ps1 `
  -RepositoryRoot "E:\code for project\Agentic AUV\EasyUUV" `
  -TransferDirectory ".pytest-tmp\phase8-main-transfer-postprocess-fix"
```

The server bundle was SHA-checked and `git bundle verify` passed before the
isolated bootstrap launched with `TRANSFER_ROOT=/root/phase8-main-transfer`.
Collection ran only under `/root/EASYkoopman-phase8-main-v2`; `/root/IsaacLab`
was not edited. After server completion, the following validator returned zero:

```bash
/opt/conda/envs/isaaclab/bin/python workflows/validate_phase8_evidence.py \
  --envelope source/results/koopman_phase8_dataset/dataset_envelope.json \
  --qualification server_isaac_identification_dataset --json
```

The tested `scripts/phase8_main_pullback.ps1` copied the remote dataset and
status tree into a random local staging directory, checked the exact file
inventory and all status/protocol/source/runtime/envelope gates, ran the same
validator locally, and only then moved the dataset into the previously absent
canonical root.

Final local preflight evidence at the successful commit:

| Gate | Result |
|---|---|
| Targeted Phase 8 tests | `118 passed` |
| Full pytest | `743 passed, 1 skipped` |
| `compileall`, `pip check`, Bash parse, PowerShell parse | pass |
| Task-file clean tree, pilot preservation, canonical-main absence | pass |
| Bundle completeness and remote transfer verification | pass |

## Exact dataset

Each of the eight public configurations has six fit, three validation and three
test episodes. Every episode contains exactly 512 contiguous transitions and is
independently reset, logged, finalized and manifested.

| Configuration | Fit | Validation | Test | Episodes | Transitions |
|---|---:|---:|---:|---:|---:|
| `base` | 6 | 3 | 3 | 12 | 6,144 |
| `long_body` | 6 | 3 | 3 | 12 | 6,144 |
| `heavy_moderate` | 6 | 3 | 3 | 12 | 6,144 |
| `asymmetric` | 6 | 3 | 3 | 12 | 6,144 |
| `uuv6` | 6 | 3 | 3 | 12 | 6,144 |
| `uuv6_angled` | 6 | 3 | 3 | 12 | 6,144 |
| `uuv4` | 6 | 3 | 3 | 12 | 6,144 |
| `uuv4_angled` | 6 | 3 | 3 | 12 | 6,144 |
| **Total** | **48** | **24** | **24** | **96** | **49,152** |

Server and pullback file/status gates:

| Check | Result |
|---|---:|
| Episode JSONL / manifests / episode logs | `96 / 96 / 96` |
| Retained `.part` files | `0` |
| Configuration native status `0` | `8 / 8` |
| Configuration tee status `0` | `8 / 8` |
| Configuration semantic status `pass` | `8 / 8` |
| Canonical files covered by server inventory | `294 / 294` |
| External-envelope referenced files | `293` |
| Validator warnings | `[]` |

## Frozen scenario and seed matrix

The same role/family/repetition seed pairing is reused across configurations as
pre-registered. `excitation_seed` drives the action waveform; `seed` drives the
environment reset/reference stream under the frozen nominal environment.

| Role | Excitation family | Excitation seeds | Environment seeds | Episodes per configuration |
|---|---|---|---|---:|
| fit | `independent_prbs` | `8201, 8202` | `9211, 9212` | 2 |
| fit | `bounded_multisine` | `8201, 8202` | `9221, 9222` | 2 |
| fit | `coupled_chirp` | `8201, 8202` | `9231, 9232` | 2 |
| validation | `independent_prbs` | `8301` | `9311` | 1 |
| validation | `bounded_multisine` | `8301` | `9321` | 1 |
| validation | `coupled_chirp` | `8301` | `9331` | 1 |
| test | `independent_prbs` | `8401` | `9411` | 1 |
| test | `bounded_multisine` | `8401` | `9421` | 1 |
| test | `coupled_chirp` | `8401` | `9431` | 1 |

## Runtime and immutable hashes

| Artifact/fact | Value |
|---|---|
| Isaac Sim distribution | `5.0.0.0` |
| Isaac Lab version file / release tag | `2.2.1` / `v2.2.1` |
| Isaac Lab repo / parent | `c91a125c73c8b574878419a9583afc0b63b99f0a` / `0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20` |
| Locked Isaac Lab patch SHA-256 | `d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079` |
| Runtime object SHA-256 | `1d5afae47ae18524a3cd9645dfb9b94adc81346d143684a6584c23e2e09591c2` |
| Inventory semantic SHA-256 | `41e23460b4e86b5f9748c9030bb5b1d9e33abd5222958adfa132bcb8ea8b613d` |
| Inventory file SHA-256 | `cfac12d15f062c9f330d2acf6381d341769e989dc35cd00ae29759a6f94f395b` |
| LOCO split semantic SHA-256 | `4581427d0d63eac9b1fea038dd8f8068c363a457816141c8098ef91df85346bb` |
| LOCO split file SHA-256 | `0e245dfa238df252145e99751be8dcc9ed6a1ef340f382428f6fd3c86db5d8ed` |
| Dataset envelope SHA-256 | `46d02531457123f2a1dfda3b16159b359a6caff2d90b14283094a349647a1b04` |
| `all_files.sha256` sidecar SHA-256 | `a7d3633498b93ed9308dd61eafed84d15fc3500d9ec400c57b39532294cf0a0a` |

The split manifest contains eight LOCO folds, each holding out exactly one whole
configuration. The main inventory contains 96 unique episode IDs. Comparison
against the retained 16-episode pilot inventory found zero episode-ID overlap
and zero transition-hash overlap; pilot rows were not copied or relabelled.

## Failure preservation and deviations

No failed attempt was appended into or promoted as the successful dataset:

1. `25b3ba2` failed before collection because the non-interactive server shell
   did not activate the locked Conda runtime. Its failed checkout/transfer were
   preserved under names ending `failed-25b3ba2-python-runtime`.
2. `01e9da6` reached the environment's native three-second boundary and retained
   eight 178-row `.part` files with zero finalized episodes. Its failed roots
   were preserved under names ending `failed-01e9da6-native-timeout`.
3. `647b65f` collected 96 complete episodes, but evidence packaging failed closed
   because the Isaac launcher banner contaminated the captured runtime hash.
   Those 96 rows were not resumed or promoted; the complete failed attempt was
   preserved under names ending `failed-647b65f-postprocess-runtime-hash`.
4. `a7e8198` reran the unchanged approved protocol from a fresh checkout and
   fresh result root. It completed collection and packaging with
   `bootstrap.exit=0`.

The deterministic fixes changed orchestration only: the main collector owns the
512-step boundary, each configuration must produce exactly 12 finalized artifact
triples with no `.part`, and non-SimulationApp postprocessing uses the locked
Conda Python directly. The D-23 experiment ID, role/action matrix and analysis
policy were not expanded or changed.

## Requirement and claim boundary

| Requirement | Evidence from 08-04 | Status at this boundary |
|---|---|---|
| `KID-01` | Exact-eight whole-episode fit/validation/test inventory and eight configuration-held-out LOCO folds | **data portion PASS** |
| `KID-02` | Frozen common analysis policy and immutable dataset/split inputs exist | **data prerequisite PASS; model comparison not run** |
| `KID-03` | Frozen held-out test episodes and horizon policy exist | **data prerequisite PASS; prediction metrics not run** |
| `KID-05` | Frozen gate template and provenance-bound inputs exist | **data prerequisite PASS; selection/no-selection not run** |

Allowed claims are limited to `exact_eight_main_dataset_ready`,
`immutable_role_inventory_ready` and `loco_split_ready`.

This evidence does **not** prove that a Koopman model has been identified, that
any feature/horizon/model has been selected, that held-out prediction or OOD
generalization is good, that Koopman outperforms persistence/linear baselines,
or that MPC, closed-loop control, environment adaptation, Agentic behavior or
Sim2Real succeeds. Those conclusions require the separately frozen 08-05
fit/validation/freeze-before-test/evaluation chain.
