[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$PythonExecutable = "",
    [int]$MinimumCollectedTests = 580,
    [switch]$SkipTestsForContract
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$phase8ExecutionBaseline = "02138133417e3a2fa08caf4fad68350b07833fcc"
$phase8RunId = [Guid]::NewGuid().ToString('N')
$phase8TempRoot = ".pytest-tmp/phase8-pilot-preflight-$phase8RunId"

$phase8ScriptPath = $PSCommandPath
if (-not $phase8ScriptPath) { $phase8ScriptPath = $MyInvocation.MyCommand.Path }
if (-not $RepositoryRoot) {
    if (-not $phase8ScriptPath) { throw "script_path_unavailable" }
    $RepositoryRoot = Join-Path (Split-Path -Parent $phase8ScriptPath) ".."
}

function Fail-Gate {
    param([string]$Name, [string]$Detail = "")
    Write-Error "${Name}_failed:$Detail"
    exit 1
}

function Invoke-Gate {
    param([string]$Name, [scriptblock]$Command)
    Write-Output "gate=$Name;status=running"
    & $Command
    if ($LASTEXITCODE -ne 0) { Fail-Gate $Name "exit=$LASTEXITCODE" }
    Write-Output "gate=$Name;status=pass"
}

function Invoke-GitCapture {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & git @Arguments 1> $stdoutPath 2> $stderrPath
            $nativeExitCode = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $previousErrorActionPreference }
        return [pscustomobject]@{
            ExitCode = $nativeExitCode
            Stdout = ([IO.File]::ReadAllText($stdoutPath)).Trim()
            Stderr = ([IO.File]::ReadAllText($stderrPath)).Trim()
        }
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-GitText {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $result = Invoke-GitCapture @Arguments
    if ($result.Stderr) { Write-Warning $result.Stderr }
    if ($result.ExitCode -ne 0) { Fail-Gate "git_command" ($Arguments -join " ") }
    return $result.Stdout
}

function Resolve-Phase8Bash {
    $isWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
    if (-not $isWindows) {
        $native = Get-Command bash -ErrorAction SilentlyContinue
        if (-not $native) { Fail-Gate "bash_parse" "bash_unavailable" }
        return $native.Source
    }
    $candidates = [System.Collections.Generic.List[string]]::new()
    $exec = Invoke-GitCapture --exec-path
    if ($exec.Stderr) { Write-Warning $exec.Stderr }
    if ($exec.ExitCode -eq 0 -and $exec.Stdout) {
        $gitRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $exec.Stdout))
        $candidates.Add((Join-Path $gitRoot "bin/bash.exe"))
    }
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if ($gitCommand -and $gitCommand.Source) {
        $gitRoot = Split-Path -Parent (Split-Path -Parent $gitCommand.Source)
        $candidates.Add((Join-Path $gitRoot "bin/bash.exe"))
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $resolved = (Resolve-Path -LiteralPath $candidate).Path
            if ($resolved -notmatch '(?i)[\/]System32[\/]') { return $resolved }
        }
    }
    Fail-Gate "bash_parse" "git_bash_unavailable"
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe" }
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    Fail-Gate "python_executable" $PythonExecutable
}

$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repository
    # targeted_phase8_tests full_collect_only full_pytest compileall pip_check
    # bash_parse powershell_parse git_diff_check protected_diff worktree_clean
    # canonical_pilot_absent
    if (-not $SkipTestsForContract) {
        $null = New-Item -ItemType Directory -Path $phase8TempRoot
        Invoke-Gate "targeted_phase8_tests" {
            & $PythonExecutable -m pytest -q `
                --basetemp "$phase8TempRoot/targeted" `
                tests/test_phase8_protocol_evidence.py `
                tests/test_phase8_pilot_server_contract.py `
                tests/test_koopman_schema_v2.py `
                tests/test_koopman_bridge_v2.py `
                tests/test_phase7_server_evidence_contract.py
        }
        Write-Output "gate=full_collect_only;status=running"
        $collectOutput = @(
            & $PythonExecutable -m pytest --collect-only -q `
                --basetemp "$phase8TempRoot/collect" 2>&1
        )
        if ($LASTEXITCODE -ne 0) { Fail-Gate "full_collect_only" "exit=$LASTEXITCODE" }
        $collectText = $collectOutput -join "`n"
        $matches = [regex]::Matches($collectText, '(\d+) tests? collected')
        if ($matches.Count -ne 1) { Fail-Gate "full_collect_only" "count_unavailable" }
        $collected = [int]$matches[0].Groups[1].Value
        if ($collected -lt $MinimumCollectedTests) {
            Fail-Gate "full_collect_only" "expected_min=$MinimumCollectedTests;actual=$collected"
        }
        Write-Output "gate=full_collect_only;status=pass;count=$collected;minimum=$MinimumCollectedTests"
        Invoke-Gate "full_pytest" {
            & $PythonExecutable -m pytest -q --basetemp "$phase8TempRoot/full-suite"
        }
        Invoke-Gate "compileall" {
            & $PythonExecutable -m compileall -q koopman easyuuv_nc workflows scripts tests
        }
        Invoke-Gate "pip_check" { & $PythonExecutable -m pip check }
    }
    else {
        Write-Output "contract_skip=targeted_phase8_tests,full_collect_only,full_pytest,compileall,pip_check"
    }

    $bashPath = Resolve-Phase8Bash
    Invoke-Gate "bash_parse" {
        & $bashPath -n scripts/phase8_pilot_server_bootstrap.sh
        if ($LASTEXITCODE -eq 0) { & $bashPath -n scripts/phase8_pilot_server_run.sh }
    }
    Write-Output "gate=powershell_parse;status=running"
    foreach ($script in @(
        "scripts/phase8_pilot_local_preflight.ps1",
        "scripts/phase8_pilot_prepare_bundle.ps1",
        "scripts/phase8_pilot_pullback.ps1"
    )) {
        $tokens = $null
        $errors = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $repository $script), [ref]$tokens, [ref]$errors
        )
        if ($errors.Count -ne 0) { Fail-Gate "powershell_parse" $script }
    }
    Write-Output "gate=powershell_parse;status=pass"

    Write-Output "gate=git_diff_check;status=running"
    $null = Invoke-GitText diff --check
    Write-Output "gate=git_diff_check;status=pass"

    Write-Output "gate=protected_diff;status=running"
    $null = Invoke-GitText -Arguments @(
        "cat-file", "-e", "${phase8ExecutionBaseline}^{commit}"
    )
    $ancestor = Invoke-GitCapture merge-base --is-ancestor $phase8ExecutionBaseline HEAD
    if ($ancestor.Stderr) { Write-Warning $ancestor.Stderr }
    if ($ancestor.ExitCode -ne 0) { Fail-Gate "protected_diff" "phase8_execution_baseline_not_ancestor" }
    $v1Protected = Invoke-GitText diff --name-only v1.0 -- `
        .planning/milestones .planning/reports `
        koopman/model.py koopman/lifted_edmd.py koopman/mpc.py koopman/mpc_controller.py
    if ($v1Protected) { Fail-Gate "protected_diff" $v1Protected }
    $priorEvidence = Invoke-GitText diff --name-only $phase8ExecutionBaseline -- `
        source/results/koopman_phase6 source/results/koopman_phase7
    if ($priorEvidence) { Fail-Gate "protected_diff" $priorEvidence }
    $schemaDrift = Invoke-GitText diff --name-only $phase8ExecutionBaseline -- koopman/schema_v2.py
    if ($schemaDrift) { Fail-Gate "protected_diff" $schemaDrift }
    Write-Output "gate=protected_diff;status=pass"

    Write-Output "gate=worktree_clean;status=running"
    $statusText = Invoke-GitText -c "core.excludesFile=" status --porcelain=v1 --untracked-files=all
    if ($statusText) { Fail-Gate "worktree_clean" $statusText }
    Write-Output "gate=worktree_clean;status=pass"

    Write-Output "gate=canonical_pilot_absent;status=running"
    $canonicalPilot = Join-Path $repository "source/results/koopman_phase8_pilot"
    if (Test-Path -LiteralPath $canonicalPilot) { Fail-Gate "canonical_pilot_absent" $canonicalPilot }
    Write-Output "gate=canonical_pilot_absent;status=pass"

    $head = Invoke-GitText rev-parse HEAD
    Write-Output "phase8_pilot_local_preflight=pass"
    Write-Output "tested_head=$head"
}
finally { Set-Location -LiteralPath $previousLocation }
