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
    $sourceDrift = (& git diff --name-only $sourceCommit HEAD -- . ':(exclude)source/results/koopman_phase8_2') -join "`n"
    if ($sourceDrift) { throw "post_collection_source_drift:$sourceDrift" }
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
