[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$Branch = "v2.0-multi-configuration",
    [string]$TransferDirectory = ".pytest-tmp/phase8-pilot-transfer",
    [string]$CanonicalEvidenceDirectory = "source/results/koopman_phase8_pilot",
    [string]$PythonExecutable = "",
    [switch]$SkipTestsForContract
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$scriptPath = $PSCommandPath
if (-not $scriptPath) { $scriptPath = $MyInvocation.MyCommand.Path }
if (-not $RepositoryRoot) {
    if (-not $scriptPath) { throw "script_path_unavailable" }
    $RepositoryRoot = Join-Path (Split-Path -Parent $scriptPath) ".."
}

function Invoke-GitCapture {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $stdoutPath = [IO.Path]::GetTempFileName()
    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $previous = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & git @Arguments 1> $stdoutPath 2> $stderrPath
            $nativeExitCode = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $previous }
        return [pscustomobject]@{
            ExitCode = $nativeExitCode
            Stdout = ([IO.File]::ReadAllText($stdoutPath)).Trim()
            Stderr = ([IO.File]::ReadAllText($stderrPath)).Trim()
        }
    }
    finally { Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue }
}

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $result = Invoke-GitCapture @Arguments
    if ($result.Stderr) { Write-Warning $result.Stderr }
    if ($result.ExitCode -ne 0) { throw "git_failed:$($Arguments -join ' ')" }
    return $result.Stdout
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repository
    $status = Invoke-Git -c "core.excludesFile=" status --porcelain=v1 --untracked-files=all
    if ($status) { throw "worktree_dirty" }

    $preflight = Join-Path $repository "scripts/phase8_pilot_local_preflight.ps1"
    $arguments = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $preflight,
        "-RepositoryRoot", $repository
    )
    if ($PythonExecutable) { $arguments += @("-PythonExecutable", $PythonExecutable) }
    if ($SkipTestsForContract) { $arguments += "-SkipTestsForContract" }
    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "local_preflight_failed:$LASTEXITCODE" }

    $head = Invoke-Git rev-parse HEAD
    if ($head -notmatch '^[0-9a-f]{40}$') { throw "head_invalid" }
    $currentBranch = Invoke-Git branch --show-current
    if ($currentBranch -ne $Branch) { throw "branch_mismatch:expected=$Branch;actual=$currentBranch" }
    $branchCommit = Invoke-Git rev-parse "$Branch^{commit}"
    if ($head -ne $branchCommit) { throw "tested_head_not_branch_tip" }
    $status = Invoke-Git -c core.excludesFile= status --porcelain=v1 --untracked-files=all
    if ($status) { throw "worktree_dirty" }

    $canonical = Join-Path $repository $CanonicalEvidenceDirectory
    if (Test-Path -LiteralPath $canonical) { throw "canonical_evidence_already_exists:$canonical" }
    $transferRoot = Join-Path $repository $TransferDirectory
    if (Test-Path -LiteralPath $transferRoot) { throw "transfer_directory_already_exists:$transferRoot" }
    $null = New-Item -ItemType Directory -Path $transferRoot
    $bundlePath = Join-Path $transferRoot "EasyUUV-phase8-pilot-v2.bundle"
    $sidecarPath = Join-Path $transferRoot "expected-source-commit.txt"
    $bootstrapPath = Join-Path $transferRoot "phase8_pilot_server_bootstrap.sh"

    $null = Invoke-Git bundle create $bundlePath $Branch
    $null = Invoke-Git bundle verify $bundlePath
    $bundleHead = Invoke-Git bundle list-heads $bundlePath "refs/heads/$Branch"
    $parts = $bundleHead -split '\s+', 2
    if ($parts.Count -ne 2 -or $parts[0] -ne $head -or $parts[1] -ne "refs/heads/$Branch") {
        throw "bundle_ref_mismatch:$bundleHead"
    }
    [IO.File]::WriteAllText($sidecarPath, "$head`n", [Text.UTF8Encoding]::new($false))
    $bootstrap = Invoke-Git show "${head}:scripts/phase8_pilot_server_bootstrap.sh"
    [IO.File]::WriteAllText(
        $bootstrapPath,
        ($bootstrap -replace "`r`n", "`n") + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    Write-Output "tested_head=$head"
    Write-Output "bundle_path=$bundlePath"
    Write-Output "bundle_sha256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $bundlePath).Hash.ToLowerInvariant())"
    Write-Output "expected_commit_sidecar=$sidecarPath"
    Write-Output "server_bootstrap=$bootstrapPath"
}
finally { Set-Location -LiteralPath $previousLocation }
