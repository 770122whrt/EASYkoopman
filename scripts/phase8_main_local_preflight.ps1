[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$PythonExecutable = "",
    [int]$MinimumCollectedTests = 700,
    [switch]$SkipTestsForContract
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$phase8ExecutionBaseline = "25df865"
$runId = [Guid]::NewGuid().ToString("N")
$tempRoot = ".pytest-tmp/phase8-main-preflight-$runId"

if (-not $RepositoryRoot) { $RepositoryRoot = Join-Path (Split-Path -Parent $PSCommandPath) ".." }
$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe" }

function Fail-Gate { param([string]$Name, [string]$Detail = ""); throw "${Name}_failed:$Detail" }
function Invoke-Gate {
    param([string]$Name, [scriptblock]$Command)
    Write-Output "gate=$Name;status=running"
    & $Command
    if ($LASTEXITCODE -ne 0) { Fail-Gate $Name "exit=$LASTEXITCODE" }
    Write-Output "gate=$Name;status=pass"
}
function Git-Text {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { Fail-Gate "git_command" ($Arguments -join " ") }
    return ($output -join "`n").Trim()
}
function Resolve-Bash {
    $execPath = Git-Text --exec-path
    $gitRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $execPath))
    $candidate = Join-Path $gitRoot "bin/bash.exe"
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { Fail-Gate "bash_parse" "git_bash_unavailable" }
    return $candidate
}

$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repository
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { Fail-Gate "python_executable" $PythonExecutable }
    if (-not $SkipTestsForContract) {
        $null = New-Item -ItemType Directory -Path $tempRoot
        Invoke-Gate "targeted_phase8_tests" {
            & $PythonExecutable -m pytest -q --basetemp "$tempRoot/targeted" `
                tests/test_phase8_protocol_evidence.py `
                tests/test_phase8_main_server_contract.py `
                tests/test_koopman_collection_v2.py `
                tests/test_koopman_splits_v2.py `
                tests/test_koopman_model_v2.py `
                tests/test_koopman_metrics_v2.py `
                tests/test_koopman_loco_v2.py
        }
        $collect = & $PythonExecutable -m pytest --collect-only -q --basetemp "$tempRoot/collect" 2>&1
        if ($LASTEXITCODE -ne 0) { Fail-Gate "full_collect_only" "exit=$LASTEXITCODE" }
        $match = [regex]::Match(($collect -join "`n"), '(\d+) tests? collected')
        if (-not $match.Success -or [int]$match.Groups[1].Value -lt $MinimumCollectedTests) { Fail-Gate "full_collect_only" "minimum=$MinimumCollectedTests" }
        Write-Output "gate=full_collect_only;status=pass;count=$($match.Groups[1].Value)"
        Invoke-Gate "full_pytest" { & $PythonExecutable -m pytest -q --basetemp "$tempRoot/full" }
        Invoke-Gate "compileall" { & $PythonExecutable -m compileall -q koopman easyuuv_nc workflows scripts tests }
        Invoke-Gate "pip_check" { & $PythonExecutable -m pip check }
    }
    else { Write-Output "contract_skip=targeted_phase8_tests,full_collect_only,full_pytest,compileall,pip_check" }

    $bash = Resolve-Bash
    Invoke-Gate "bash_parse" {
        & $bash -n scripts/phase8_main_server_bootstrap.sh
        if ($LASTEXITCODE -eq 0) { & $bash -n scripts/phase8_main_server_run.sh }
    }
    foreach ($script in @("scripts/phase8_main_local_preflight.ps1","scripts/phase8_main_prepare_bundle.ps1","scripts/phase8_main_pullback.ps1")) {
        $tokens = $null; $errors = $null
        $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $repository $script), [ref]$tokens, [ref]$errors)
        if ($errors.Count) { Fail-Gate "powershell_parse" $script }
    }
    Write-Output "gate=powershell_parse;status=pass"
    $null = Git-Text diff --check
    Write-Output "gate=git_diff_check;status=pass"

    $null = Git-Text cat-file -e "${phase8ExecutionBaseline}^{commit}"
    $v1Protected = Git-Text diff --name-only v1.0 -- .planning/milestones .planning/reports koopman/model.py koopman/lifted_edmd.py koopman/mpc.py koopman/mpc_controller.py
    if ($v1Protected) { Fail-Gate "protected_diff" $v1Protected }
    $priorEvidence = Git-Text diff --name-only $phase8ExecutionBaseline -- source/results/koopman_phase6 source/results/koopman_phase7
    if ($priorEvidence) { Fail-Gate "protected_diff" $priorEvidence }
    $pilotEvidence = Git-Text diff --name-only 3cbba1e -- source/results/koopman_phase8_pilot
    if ($pilotEvidence) { Fail-Gate "pilot_evidence_preserved" $pilotEvidence }
    Write-Output "gate=pilot_evidence_preserved;status=pass"

    # The user-owned .gitignore edit and untracked AGENTS.md predate this task and are
    # explicitly excluded without modifying, staging or hiding them globally.
    $status = Git-Text -c "core.excludesFile=" status --porcelain=v1 --untracked-files=all -- . ':(exclude).gitignore' ':(exclude)AGENTS.md'
    if ($status) { Fail-Gate "worktree_clean" $status }
    Write-Output "gate=worktree_clean;status=pass;scope=task_files"

    foreach ($root in @("source/results/koopman_phase8_dataset","source/results/koopman_phase8_evaluation","source/results/koopman_phase8_selection")) {
        if (Test-Path -LiteralPath $root) { Fail-Gate "canonical_main_absent" $root }
    }
    Write-Output "gate=canonical_main_absent;status=pass"
    Write-Output "phase8_main_local_preflight=pass"
    Write-Output "tested_head=$(Git-Text rev-parse HEAD)"
}
finally { Set-Location -LiteralPath $previousLocation }
