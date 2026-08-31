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
    $foldWorkRoot = ".pytest-tmp/phase8-2-formal-folds"
    $telemetryRoot = Join-Path $foldWorkRoot "_telemetry"
    $configurations = @(
        "base",
        "long_body",
        "heavy_moderate",
        "asymmetric",
        "uuv6",
        "uuv6_angled",
        "uuv4",
        "uuv4_angled"
    )
    if (-not (Test-Path -LiteralPath $dataset -PathType Container)) { throw "phase8_2_dataset_missing" }
    foreach ($root in @($evaluation, $selection)) {
        if (Test-Path -LiteralPath $root) { throw "formal_output_exists:$root" }
    }
    if (-not (Test-Path -LiteralPath $sourceCommitFile -PathType Leaf)) { throw "source_commit_sidecar_missing" }
    $sourceCommit = (Get-Content -Raw -LiteralPath $sourceCommitFile).Trim()
    if ($sourceCommit -notmatch '^[0-9a-f]{40}$') { throw "source_commit_invalid" }
    & git cat-file -e "$sourceCommit`^{commit}"
    if ($LASTEXITCODE -ne 0) { throw "source_commit_unavailable" }
    $evaluatorCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $evaluatorCommit -notmatch '^[0-9a-f]{40}$') { throw "evaluator_commit_invalid" }
    $allowedPostCollectionRepairPaths = @(
        ".planning/phases/08.2-phase-8-1-fresh-server-evaluation-and-closeout/08.2-03-PLAN.md",
        ".planning/phases/08.2-phase-8-1-fresh-server-evaluation-and-closeout/08.2-SPEC.md",
        "docs/phase8_2_fresh_server_evaluation_runbook.md",
        "scripts/phase8_2_formal_local.ps1",
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
    & $PythonExecutable workflows/validate_phase81_d23_approval.py `
        --approval-record $approval --role-protocol $role --analysis-policy $policy
    if ($LASTEXITCODE -ne 0) { throw "canonical_d23_validation_failed" }
    & $PythonExecutable workflows/validate_phase82_dataset_index.py `
        --dataset-root $dataset --role-protocol $role --inventory $inventory `
        --split $split --source-commit $sourceCommit
    if ($LASTEXITCODE -ne 0) { throw "phase8_2_dataset_validation_failed" }

    New-Item -ItemType Directory -Force -Path $foldWorkRoot, $telemetryRoot | Out-Null
    foreach ($configuration in $configurations) {
        $foldOutput = Join-Path $foldWorkRoot $configuration
        $foldEnvelope = Join-Path $foldOutput "fold_envelope.json"
        if (Test-Path -LiteralPath $foldOutput) {
            if (-not (Test-Path -LiteralPath $foldEnvelope -PathType Leaf)) {
                throw "formal_fold_existing_invalid:$configuration"
            }
            Write-Output "formal_fold_resume=$configuration"
            continue
        }
        $startedAt = [DateTimeOffset]::UtcNow
        & $PythonExecutable workflows/run_koopman_v21_loco.py `
            --approval-record $approval --role-protocol $role --analysis-policy $policy `
            --dataset-root $dataset --inventory $inventory --split $split `
            --source-commit $sourceCommit --evaluator-commit $evaluatorCommit `
            --fold $configuration --output-root $foldOutput
        $foldExitCode = $LASTEXITCODE
        $finishedAt = [DateTimeOffset]::UtcNow
        [ordered]@{
            configuration = $configuration
            duration_seconds = [Math]::Round(($finishedAt - $startedAt).TotalSeconds, 3)
            evaluator_commit = $evaluatorCommit
            exit_code = $foldExitCode
            finished_at = $finishedAt.ToString("o")
            source_commit = $sourceCommit
            started_at = $startedAt.ToString("o")
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $telemetryRoot "$configuration.json") -Encoding utf8
        if ($foldExitCode -ne 0) { throw "formal_loco_fold_failed:$configuration`:$foldExitCode" }
        if (-not (Test-Path -LiteralPath $foldEnvelope -PathType Leaf)) {
            throw "formal_loco_fold_publication_missing:$configuration"
        }
        Write-Output "formal_fold_complete=$configuration"
    }
    & $PythonExecutable workflows/run_koopman_v21_loco.py `
        --approval-record $approval --role-protocol $role --analysis-policy $policy `
        --inventory $inventory --split $split --source-commit $sourceCommit `
        --evaluator-commit $evaluatorCommit --fold assemble --fold-root $foldWorkRoot `
        --output-root $evaluation
    if ($LASTEXITCODE -ne 0) { throw "formal_loco_assembly_failed" }
    & $PythonExecutable workflows/select_koopman_v21.py `
        --approval-record $approval --role-protocol $role --analysis-policy $policy `
        --dataset-root $dataset --inventory $inventory --evaluation-root $evaluation `
        --source-commit $sourceCommit --output-root $selection
    if ($LASTEXITCODE -ne 0) { throw "formal_selection_failed" }
    Write-Output "phase8_2_formal_chain=complete"
    Write-Output "selection_result=$selection/selection_result.json"
}
finally { Set-Location -LiteralPath $previousLocation }
