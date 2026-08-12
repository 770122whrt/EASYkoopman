[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$Remote = "agentic-AUV",
    [string]$RemoteEvidenceRoot = "/root/EASYkoopman-phase7-v2/source/results/koopman_phase7",
    [string]$TransferDirectory = ".pytest-tmp/phase7-transfer",
    [string]$CanonicalEvidenceDirectory = "source/results/koopman_phase7",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$phase7ScriptPath = $PSCommandPath
if (-not $phase7ScriptPath) { $phase7ScriptPath = $MyInvocation.MyCommand.Path }
if (-not $RepositoryRoot) {
    if (-not $phase7ScriptPath) { throw "script_path_unavailable" }
    $RepositoryRoot = Join-Path (Split-Path -Parent $phase7ScriptPath) ".."
}

function Read-Exact {
    param([string]$Path, [string]$Label, [string]$Pattern)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "${Label}_missing:$Path" }
    $value = (Get-Content -Raw -LiteralPath $Path).Trim()
    if ($value -notmatch $Pattern) { throw "${Label}_invalid" }
    return $value
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe" }
$transferRoot = Join-Path $repository $TransferDirectory
$sidecar = Join-Path $transferRoot "expected-source-commit.txt"
$expectedCommit = Read-Exact $sidecar "expected_source_commit" '^[0-9a-f]{40}$'

$localHead = (& git -C $repository rev-parse HEAD 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "local_head_probe_failed" }
if ($localHead.Trim() -ne $expectedCommit) { throw "local_head_mismatch" }
$status = @(& git -c "core.excludesFile=" -C $repository status --porcelain=v1 --untracked-files=all 2>&1)
if ($LASTEXITCODE -ne 0) { throw "local_status_probe_failed" }
if (($status -join "`n").Trim()) { throw "worktree_dirty" }

$stagingRoot = Join-Path (Join-Path $repository ".pytest-tmp") "phase7-pullback-$([Guid]::NewGuid().ToString('N'))"
if (Test-Path -LiteralPath $stagingRoot) { throw "staging_directory_already_exists" }
$null = New-Item -ItemType Directory -Path $stagingRoot
& scp -r "${Remote}:$RemoteEvidenceRoot" $stagingRoot
if ($LASTEXITCODE -ne 0) { throw "scp_failed:$LASTEXITCODE;staging=$stagingRoot" }

$stagedEvidence = Join-Path $stagingRoot "koopman_phase7"
if (-not (Test-Path -LiteralPath $stagedEvidence -PathType Container)) { throw "staged_evidence_missing" }
$aggregate = Join-Path $stagedEvidence "evidence.json"
$serverHashLine = (Get-Content -Raw -LiteralPath (Join-Path $stagedEvidence "evidence.sha256")).Trim()
if ($serverHashLine -notmatch '^([0-9a-f]{64})\s+') { throw "server_sha256_invalid" }
$serverHash = $Matches[1]
$localHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $aggregate).Hash.ToLowerInvariant()
if ($serverHash -ne $localHash) { throw "sha256_mismatch:server=$serverHash;local=$localHash" }

$pulledCommit = Read-Exact (Join-Path $stagedEvidence "source_commit.txt") "source_commit" '^[0-9a-f]{40}$'
if ($pulledCommit -ne $expectedCommit) { throw "source_commit_mismatch" }
$labTag = Read-Exact (Join-Path $stagedEvidence "isaaclab_release_tag.txt") "isaaclab_release_tag" '^v2\.2\.1$'
$null = Read-Exact (Join-Path $stagedEvidence "isaaclab_release_commit.txt") "isaaclab_release_commit" '^[0-9a-f]{40}$'
$null = Read-Exact (Join-Path $stagedEvidence "isaaclab_repo_commit.txt") "isaaclab_repo_commit" '^[0-9a-f]{40}$'
$simVersion = Read-Exact (Join-Path $stagedEvidence "isaac_sim_version.txt") "isaac_sim_version" '^5\.0$'
$labVersion = Read-Exact (Join-Path $stagedEvidence "isaaclab_version.txt") "isaaclab_version" '^2\.2\.1$'
if ($simVersion -ne "5.0" -or $labVersion -ne "2.2.1" -or $labTag -ne "v2.2.1") {
    throw "runtime_version_mismatch"
}

$validator = Join-Path $repository "workflows/validate_koopman_v2.py"
$validatorOutput = @(& $PythonExecutable $validator --aggregate $aggregate --json 2>&1)
$validatorExitCode = $LASTEXITCODE
[IO.File]::WriteAllText(
    (Join-Path $stagedEvidence "pullback_validator.json"),
    ($validatorOutput -join "`n") + "`n",
    [Text.UTF8Encoding]::new($false)
)
if ($validatorExitCode -ne 0) { throw "validator_failed:$validatorExitCode;staging=$stagingRoot" }
$validatorResult = ($validatorOutput -join "`n") | ConvertFrom-Json
if (
    $validatorResult.validation_gate -ne "koopman_v2_exact_three_server_evidence_valid" -or
    $validatorResult.configuration_count -ne 3 -or
    $validatorResult.source_commit -ne $expectedCommit
) { throw "validator_result_invalid" }

$canonicalEvidence = Join-Path $repository $CanonicalEvidenceDirectory
if (Test-Path -LiteralPath $canonicalEvidence) { throw "canonical_evidence_already_exists:$canonicalEvidence" }
$null = New-Item -ItemType Directory -Path (Split-Path -Parent $canonicalEvidence) -Force
Move-Item -LiteralPath $stagedEvidence -Destination $canonicalEvidence
Write-Output "validation_gate=koopman_v2_exact_three_server_evidence_valid"
Write-Output "configuration_count=3"
Write-Output "source_commit=$expectedCommit"
Write-Output "artifact_sha256=$localHash"
Write-Output "canonical_evidence=$canonicalEvidence"
