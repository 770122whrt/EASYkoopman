[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$PythonExecutable = "",
    [switch]$SkipTestsForContract
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$phase81Baseline = "5fd7a995e2fc1abfcc85b8921ab98096dafc3ee7"
$expectedRole = "083d5eae3729e9939287345ab258dbfe4b4c8ca71ab769c2fd8616431a649417"
$expectedPolicy = "7a790b43d0f1581b8995ccdcbd9b6d259cb09bc8fe2268201400243d05f1e18c"
$runId = [Guid]::NewGuid().ToString("N")
$tempRoot = ".pytest-tmp/phase8-2-preflight-$runId"

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
    $value = (& git @Arguments 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) { Fail-Gate "git_command" ($Arguments -join " ") }
    return $value.Trim()
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
    $role = "protocols/phase8_1/main_role_assignment_protocol.json"
    $policy = "protocols/phase8_1/analysis_policy.json"
    $approval = "protocols/phase8_1/d23_approval.json"
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $role).Hash.ToLowerInvariant() -ne $expectedRole) { Fail-Gate "role_protocol_hash" }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $policy).Hash.ToLowerInvariant() -ne $expectedPolicy) { Fail-Gate "analysis_policy_hash" }
    Invoke-Gate "canonical_d23_approval" {
        & $PythonExecutable workflows/validate_phase81_d23_approval.py `
            --approval-record $approval --role-protocol $role --analysis-policy $policy
    }

    if (-not $SkipTestsForContract) {
        $null = New-Item -ItemType Directory -Path $tempRoot
        Invoke-Gate "targeted_phase8_2_operational_contract" {
            & $PythonExecutable -m pytest -q --basetemp "$tempRoot/targeted" `
                tests/test_phase82_operational_contract.py `
                tests/test_phase81_d23_approval.py `
                tests/test_phase81_protocol_contract.py
        }
        Invoke-Gate "relevant_phase8_1_regression" {
            & $PythonExecutable -m pytest -q --basetemp "$tempRoot/relevant" `
                tests/test_thruster_dynamics.py `
                tests/test_koopman_actuator_memory_v21.py `
                tests/test_koopman_schema_v21.py `
                tests/test_koopman_bridge_v21.py `
                tests/test_koopman_dataset_v21.py `
                tests/test_koopman_so3_v21.py `
                tests/test_koopman_platform_features_v21.py `
                tests/test_koopman_model_v21.py `
                tests/test_koopman_metrics_v21.py `
                tests/test_koopman_loco_v21.py `
                tests/test_koopman_evaluation_v21.py `
                tests/test_koopman_selection_v21.py `
                tests/test_phase81_collector_provenance.py `
                tests/test_phase81_entrypoints.py `
                tests/test_phase81_formal_chain.py
        }
        Invoke-Gate "compileall" {
            & $PythonExecutable -m compileall -q koopman easyuuv_nc workflows tests
        }
    }
    else { Write-Output "contract_skip=targeted_phase8_2_operational_contract,relevant_phase8_1_regression,compileall" }

    $bash = Resolve-Bash
    Invoke-Gate "bash_parse" {
        & $bash -n scripts/phase8_2_server_bootstrap.sh
        if ($LASTEXITCODE -eq 0) { & $bash -n scripts/phase8_2_server_collect.sh }
    }
    foreach ($script in @(
        "scripts/phase8_2_local_preflight.ps1",
        "scripts/phase8_2_prepare_bundle.ps1",
        "scripts/phase8_2_pullback.ps1",
        "scripts/phase8_2_formal_local.ps1",
        "scripts/phase8_2_closeout_local.ps1"
    )) {
        $tokens = $null; $errors = $null
        $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $repository $script), [ref]$tokens, [ref]$errors)
        if ($errors.Count) { Fail-Gate "powershell_parse" $script }
    }
    Write-Output "gate=powershell_parse;status=pass"
    $null = Git-Text diff --check
    Write-Output "gate=git_diff_check;status=pass"

    $protected = Git-Text diff --name-only $phase81Baseline -- `
        protocols/phase8 `
        source/results/koopman_phase8_dataset `
        source/results/koopman_phase8_evaluation `
        source/results/koopman_phase8_selection `
        .planning/phases/08-multi-configuration-koopman-identification-and-ood-gate
    if ($protected) { Fail-Gate "frozen_phase8_preserved" $protected }
    Write-Output "gate=frozen_phase8_preserved;status=pass"

    $status = Git-Text -c "core.excludesFile=" status --porcelain=v1 --untracked-files=all
    if ($status) { Fail-Gate "worktree_clean" $status }
    Write-Output "gate=worktree_clean;status=pass"

    foreach ($root in @(
        "source/results/koopman_phase8_2",
        ".pytest-tmp/phase8-2-transfer"
    )) {
        if (Test-Path -LiteralPath $root) { Fail-Gate "phase8_2_canonical_absent" $root }
    }
    Write-Output "gate=phase8_2_canonical_absent;status=pass"
    Write-Output "phase8_2_local_preflight=pass"
    Write-Output "tested_head=$(Git-Text rev-parse HEAD)"
}
finally { Set-Location -LiteralPath $previousLocation }
