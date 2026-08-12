[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$PythonExecutable = "",
    [int]$MinimumCollectedTests = 532,
    [switch]$SkipTestsForContract
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail-Gate {
    param([string]$Name, [string]$Detail = "")
    Write-Error "${Name}_failed:$Detail"
    exit 1
}

function Invoke-Gate {
    param([string]$Name, [scriptblock]$Command)
    Write-Output "gate=$Name;status=running"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Fail-Gate $Name "exit=$LASTEXITCODE"
    }
    Write-Output "gate=$Name;status=pass"
}

function Invoke-GitText {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = @(& git @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        Fail-Gate "git_command" ($Arguments -join " ")
    }
    return ($output -join "`n").Trim()
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) {
    $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    Fail-Gate "python_executable" $PythonExecutable
}

$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repository

    # Gate identifiers are stable public output for dynamic tests and runbooks:
    # targeted_phase7_tests full_collect_only full_pytest compileall pip_check
    # bash_parse powershell_parse git_diff_check protected_diff worktree_clean
    # canonical_evidence_absent
    if (-not $SkipTestsForContract) {
        Invoke-Gate "targeted_phase7_tests" {
            & $PythonExecutable -m pytest -q `
                --basetemp .pytest-tmp/phase7-targeted `
                tests/test_koopman_schema_v2.py `
                tests/test_koopman_bridge_v2.py `
                tests/test_koopman_dataset_v2.py `
                tests/test_koopman_v1_compatibility.py `
                tests/test_phase7_server_evidence_contract.py
        }

        Write-Output "gate=full_collect_only;status=running"
        $collectOutput = @(
            & $PythonExecutable -m pytest --collect-only -q `
                --basetemp .pytest-tmp/phase7-collect 2>&1
        )
        if ($LASTEXITCODE -ne 0) {
            Fail-Gate "full_collect_only" "exit=$LASTEXITCODE"
        }
        $collectText = $collectOutput -join "`n"
        $matches = [regex]::Matches($collectText, '(\d+) tests? collected')
        if ($matches.Count -ne 1) {
            Fail-Gate "full_collect_only" "count_unavailable"
        }
        $collected = [int]$matches[0].Groups[1].Value
        if ($collected -lt $MinimumCollectedTests) {
            Fail-Gate "full_collect_only" "expected_min=$MinimumCollectedTests;actual=$collected"
        }
        Write-Output "gate=full_collect_only;status=pass;count=$collected;minimum=$MinimumCollectedTests"

        Invoke-Gate "full_pytest" {
            & $PythonExecutable -m pytest -q `
                --basetemp .pytest-tmp/phase7-full-suite
        }
        Invoke-Gate "compileall" {
            & $PythonExecutable -m compileall -q `
                koopman easyuuv_nc workflows scripts tests
        }
        Invoke-Gate "pip_check" { & $PythonExecutable -m pip check }
    }
    else {
        Write-Output "contract_skip=targeted_phase7_tests,full_collect_only,full_pytest,compileall,pip_check"
    }

    $bash = Get-Command bash -ErrorAction SilentlyContinue
    if (-not $bash) { Fail-Gate "bash_parse" "bash_unavailable" }
    Invoke-Gate "bash_parse" {
        & $bash.Source -n scripts/phase7_server_bootstrap.sh
        if ($LASTEXITCODE -eq 0) { & $bash.Source -n scripts/phase7_server_smoke.sh }
    }

    Write-Output "gate=powershell_parse;status=running"
    foreach ($script in @(
        "scripts/phase7_local_preflight.ps1",
        "scripts/phase7_prepare_bundle.ps1",
        "scripts/phase7_pullback.ps1"
    )) {
        $tokens = $null
        $errors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $repository $script), [ref]$tokens, [ref]$errors
        )
        if ($errors.Count -ne 0) {
            Fail-Gate "powershell_parse" $script
        }
    }
    Write-Output "gate=powershell_parse;status=pass"

    Invoke-Gate "git_diff_check" { & git diff --check }

    Write-Output "gate=protected_diff;status=running"
    $protected = Invoke-GitText diff --name-only v1.0 -- `
        .planning/milestones .planning/reports `
        koopman/model.py koopman/lifted_edmd.py koopman/mpc.py `
        koopman/mpc_controller.py source/results/koopman_phase6
    if ($protected) {
        Fail-Gate "protected_diff" $protected
    }
    Write-Output "gate=protected_diff;status=pass"

    Write-Output "gate=worktree_clean;status=running"
    $status = @(
        & git -c "core.excludesFile=" status --porcelain=v1 `
            --untracked-files=all 2>&1
    )
    if ($LASTEXITCODE -ne 0) {
        Fail-Gate "worktree_clean" "status_probe_failed"
    }
    $statusText = ($status -join "`n").Trim()
    if ($statusText) {
        Fail-Gate "worktree_clean" $statusText
    }
    Write-Output "gate=worktree_clean;status=pass"

    Write-Output "gate=canonical_evidence_absent;status=running"
    $canonicalEvidence = Join-Path $repository "source/results/koopman_phase7"
    if (Test-Path -LiteralPath $canonicalEvidence) {
        Fail-Gate "canonical_evidence_absent" $canonicalEvidence
    }
    Write-Output "gate=canonical_evidence_absent;status=pass"

    $head = Invoke-GitText rev-parse HEAD
    Write-Output "phase7_local_preflight=pass"
    Write-Output "tested_head=$head"
}
finally {
    Set-Location -LiteralPath $previousLocation
}
