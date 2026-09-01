[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not $RepositoryRoot) { $RepositoryRoot = Join-Path (Split-Path -Parent $PSCommandPath) ".." }
$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe" }
$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repository
    $sourceCommitFile = ".pytest-tmp/phase8-2-transfer/expected-source-commit.txt"
    if (-not (Test-Path -LiteralPath $sourceCommitFile -PathType Leaf)) { throw "source_commit_sidecar_missing" }
    $sourceCommit = (Get-Content -Raw -LiteralPath $sourceCommitFile).Trim()
    if ($sourceCommit -notmatch '^[0-9a-f]{40}$') { throw "source_commit_invalid" }
    $allowedPostCollectionRepairPaths = @(
        ".planning/phases/08.2-phase-8-1-fresh-server-evaluation-and-closeout/08.2-03-PLAN.md",
        ".planning/phases/08.2-phase-8-1-fresh-server-evaluation-and-closeout/08.2-SPEC.md",
        "docs/phase8_2_fresh_server_evaluation_runbook.md",
        "scripts/phase8_2_formal_local.ps1",
        "scripts/phase8_2_closeout_local.ps1",
        "tests/test_phase81_entrypoints.py",
        "tests/test_phase81_formal_chain.py",
        "tests/test_phase82_operational_contract.py",
        "workflows/run_koopman_v21_loco.py"
    )
    $sourceDriftPaths = @(& git diff --name-only $sourceCommit HEAD -- . ':(exclude)source/results/koopman_phase8_2')
    if ($LASTEXITCODE -ne 0) { throw "post_collection_source_drift_check_failed" }
    $unexpectedDrift = @($sourceDriftPaths | Where-Object { $_ -and $_ -notin $allowedPostCollectionRepairPaths })
    if ($unexpectedDrift.Count -ne 0) {
        throw "post_collection_repair_scope_violation:$($unexpectedDrift -join ',')"
    }
    $status = (& git -c core.excludesFile= status --porcelain=v1 --untracked-files=all) -join "`n"
    if ($status) { throw "worktree_dirty:$status" }
    $root = "source/results/koopman_phase8_2"
    $closeout = "source/results/koopman_phase8_2/closeout"
    if (Test-Path -LiteralPath $closeout) { throw "closeout_output_exists" }
    & $PythonExecutable workflows/close_phase82.py `
        --approval-record protocols/phase8_1/d23_approval.json `
        --role-protocol protocols/phase8_1/main_role_assignment_protocol.json `
        --analysis-policy protocols/phase8_1/analysis_policy.json `
        --dataset-root "$root/dataset" `
        --inventory "$root/dataset/dataset_inventory.json" `
        --split "$root/dataset/loco_split_manifest.json" `
        --evaluation-root "$root/evaluation" `
        --selection-root "$root/selection" `
        --source-commit $sourceCommit --output-root $closeout
    if ($LASTEXITCODE -ne 0) { throw "phase8_2_closeout_failed" }
    Write-Output "phase8_2_closeout=pass"
    Write-Output "closeout=$closeout/closeout.json"
}
finally { Set-Location -LiteralPath $previousLocation }
