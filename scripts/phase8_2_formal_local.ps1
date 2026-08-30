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
    $approval = "protocols/phase8_1/d23_approval.json"
    $role = "protocols/phase8_1/main_role_assignment_protocol.json"
    $policy = "protocols/phase8_1/analysis_policy.json"
    $dataset = "source/results/koopman_phase8_2/dataset"
    $evaluation = "source/results/koopman_phase8_2/evaluation"
    $selection = "source/results/koopman_phase8_2/selection"
    $inventory = "$dataset/dataset_inventory.json"
    $split = "$dataset/loco_split_manifest.json"
    $sourceCommitFile = ".pytest-tmp/phase8-2-transfer/expected-source-commit.txt"
    if (-not (Test-Path -LiteralPath $dataset -PathType Container)) { throw "phase8_2_dataset_missing" }
    foreach ($root in @($evaluation, $selection)) {
        if (Test-Path -LiteralPath $root) { throw "formal_output_exists:$root" }
    }
    if (-not (Test-Path -LiteralPath $sourceCommitFile -PathType Leaf)) { throw "source_commit_sidecar_missing" }
    $sourceCommit = (Get-Content -Raw -LiteralPath $sourceCommitFile).Trim()
    if ($sourceCommit -notmatch '^[0-9a-f]{40}$') { throw "source_commit_invalid" }
    & git cat-file -e "$sourceCommit`^{commit}"
    if ($LASTEXITCODE -ne 0) { throw "source_commit_unavailable" }
    $sourceDrift = (& git diff --name-only $sourceCommit HEAD -- . ':(exclude)source/results/koopman_phase8_2') -join "`n"
    if ($sourceDrift) { throw "post_collection_source_drift:$sourceDrift" }
    $status = (& git -c core.excludesFile= status --porcelain=v1 --untracked-files=all) -join "`n"
    if ($status) { throw "worktree_dirty:$status" }
    & $PythonExecutable workflows/validate_phase81_d23_approval.py `
        --approval-record $approval --role-protocol $role --analysis-policy $policy
    if ($LASTEXITCODE -ne 0) { throw "canonical_d23_validation_failed" }
    & $PythonExecutable workflows/validate_phase82_dataset_index.py `
        --dataset-root $dataset --role-protocol $role --inventory $inventory `
        --split $split --source-commit $sourceCommit
    if ($LASTEXITCODE -ne 0) { throw "phase8_2_dataset_validation_failed" }

    & $PythonExecutable workflows/run_koopman_v21_loco.py `
        --approval-record $approval --role-protocol $role --analysis-policy $policy `
        --dataset-root $dataset --inventory $inventory --split $split `
        --source-commit $sourceCommit --fold all --output-root $evaluation
    if ($LASTEXITCODE -ne 0) { throw "formal_loco_failed" }
    & $PythonExecutable workflows/select_koopman_v21.py `
        --approval-record $approval --role-protocol $role --analysis-policy $policy `
        --dataset-root $dataset --inventory $inventory --evaluation-root $evaluation `
        --source-commit $sourceCommit --output-root $selection
    if ($LASTEXITCODE -ne 0) { throw "formal_selection_failed" }
    Write-Output "phase8_2_formal_chain=complete"
    Write-Output "selection_result=$selection/selection_result.json"
}
finally { Set-Location -LiteralPath $previousLocation }
