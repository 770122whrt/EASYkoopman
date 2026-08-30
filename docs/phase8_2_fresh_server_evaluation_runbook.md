# Phase 8.2 Fresh Server Evaluation Runbook

This runbook operates the D-23-approved Phase 8.1 experiment without changing its protocol semantics. It stops at each evidence boundary and never treats local checks as Isaac evidence.

## Fixed identities

- experiment: `phase8.1-main-identification-v1`
- role SHA-256: `083d5eae3729e9939287345ab258dbfe4b4c8ca71ab769c2fd8616431a649417`
- analysis SHA-256: `7a790b43d0f1581b8995ccdcbd9b6d259cb09bc8fe2268201400243d05f1e18c`
- local transfer: `.pytest-tmp/phase8-2-transfer`
- server checkout: `/root/EASYkoopman-phase8-2-v1`
- server result: `/root/EASYkoopman-phase8-2-results-v1`
- local result: `source/results/koopman_phase8_2`

## Gate 1 — Local readiness, before server request

Run from the EasyUUV Git root on a clean committed HEAD:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/phase8_2_local_preflight.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/phase8_2_prepare_bundle.ps1
```

Expected terminal markers:

```text
phase8_2_local_preflight=pass
phase8_2_offline_bundle=pass
```

The prepare script reruns preflight, verifies the bundle, clones it offline into a disposable directory, verifies clean detached HEAD and writes exact source/protocol/approval/bundle sidecars. Only after this gate passes should the user be asked to start the existing server.

## Gate 2 — Transfer and fresh server collection

The user must explicitly confirm that the unchanged server is running. Then transfer the already verified artifacts:

```powershell
scp .pytest-tmp/phase8-2-transfer/EasyUUV-phase8-2-v1.bundle agentic-AUV:/root/
scp .pytest-tmp/phase8-2-transfer/expected-source-commit.txt agentic-AUV:/root/
scp .pytest-tmp/phase8-2-transfer/expected-branch.txt agentic-AUV:/root/
scp .pytest-tmp/phase8-2-transfer/bundle.sha256 agentic-AUV:/root/
scp .pytest-tmp/phase8-2-transfer/role-protocol.sha256 agentic-AUV:/root/
scp .pytest-tmp/phase8-2-transfer/analysis-policy.sha256 agentic-AUV:/root/
scp .pytest-tmp/phase8-2-transfer/d23-approval.sha256 agentic-AUV:/root/
scp .pytest-tmp/phase8-2-transfer/phase8_2_server_bootstrap.sh agentic-AUV:/root/
ssh agentic-AUV "bash /root/phase8_2_server_bootstrap.sh"
```

Bootstrap refuses existing checkout/result roots. Collection writes outside the Git checkout, runs 8 independent configuration collectors and blocks inventory creation unless all 96 episode/manifests/log triplets pass.

## Gate 3 — Staged pullback

Do not manually create `source/results/koopman_phase8_2`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/phase8_2_pullback.ps1
```

The script checks native/tee/semantic statuses, relative SHA-256 inventory, exact canonical protocol/approval hashes, all v2.1 artifacts and exact LOCO split before atomically moving the staged `dataset/` and `collection_status/` roots. Commit this pulled evidence separately before formal evaluation.

## Gate 4 — Formal local evaluation

Formal evaluation requires the pulled dataset to be committed and the worktree clean. Source code must remain byte-equivalent to the bundle commit outside `source/results/koopman_phase8_2`.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/phase8_2_formal_local.ps1
```

This runs the approved exact-eight evaluator and only then the outer selector. It does not accept a candidate ID, test metrics or threshold override. The terminal result is either a valid `SELECTION` publication or a pathless `NO_SELECTION`.

## Gate 5 — Independent closeout

Do not enter Phase 9. Commit the evaluation/selection evidence, return to a clean worktree, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/phase8_2_closeout_local.ps1
```

The independent closeout revalidates canonical D-23, all 96 dataset bindings, evaluation and selection envelopes, the exact fold set, terminal model-path semantics and claim boundary. A Phase 9 handoff exists only if the final status is `SELECTION` and this closeout passes.

## Failure handling

- Preserve failed server roots; never append or relabel them as canonical success evidence.
- Rebuild from a fresh bundle/checkout/result root after fixing a genuine implementation defect.
- Do not change frozen candidates, metrics, thresholds or protocols in response to held-out results.
- A valid `NO_SELECTION` closes Phase 8.2 without a model handoff.
