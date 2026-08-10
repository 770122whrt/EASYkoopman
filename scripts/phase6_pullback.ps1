[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Remote = "agentic-AUV",
    [string]$RemoteEvidenceRoot = "/root/EASYkoopman-phase6-v2/source/results/koopman_phase6",
    [string]$TransferDirectory = ".pytest-tmp/phase6-transfer",
    [string]$CanonicalEvidenceDirectory = "source/results/koopman_phase6",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Read-CommitFile {
    param([string]$Path, [string]$Label)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "${Label}_missing:$Path"
    }
    $value = (Get-Content -Raw -LiteralPath $Path).Trim()
    if ($value -notmatch '^[0-9a-f]{40}$') {
        throw "${Label}_invalid"
    }
    return $value
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) {
    $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe"
}
$transferRoot = Join-Path $repository $TransferDirectory
$expectedCommitPath = Join-Path $transferRoot "expected-source-commit.txt"
$expectedCommit = Read-CommitFile $expectedCommitPath "expected_source_commit"
$stagingName = "phase6-pullback-$([Guid]::NewGuid().ToString('N'))"
$stagingRoot = Join-Path (Join-Path $repository ".pytest-tmp") $stagingName
if (Test-Path -LiteralPath $stagingRoot) {
    throw "staging_directory_already_exists:$stagingRoot"
}
$null = New-Item -ItemType Directory -Path $stagingRoot

$remoteSource = "${Remote}:$RemoteEvidenceRoot"
& scp -r $remoteSource $stagingRoot
if ($LASTEXITCODE -ne 0) {
    throw "scp_failed:$LASTEXITCODE;staging=$stagingRoot"
}

$stagedEvidence = Join-Path $stagingRoot "koopman_phase6"
if (-not (Test-Path -LiteralPath $stagedEvidence -PathType Container)) {
    throw "staged_evidence_missing:$stagedEvidence"
}
$qualificationPath = Join-Path $stagedEvidence "qualification.json"
$serverHashPath = Join-Path $stagedEvidence "qualification.sha256"
$sourceCommitPath = Join-Path $stagedEvidence "source_commit.txt"
$isaacLabCommitPath = Join-Path $stagedEvidence "isaaclab_repo_commit.txt"

$hashLines = @(Get-Content -LiteralPath $serverHashPath)
if ($hashLines.Count -ne 1 -or $hashLines[0] -notmatch '^[0-9a-f]{64}\s+') {
    throw "server_sha256_invalid"
}
$serverHash = ($hashLines[0] -split '\s+', 2)[0]
$localHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $qualificationPath).Hash.ToLowerInvariant()
if ($localHash -ne $serverHash) {
    throw "sha256_mismatch:server=$serverHash;local=$localHash"
}

$pulledSourceCommit = Read-CommitFile $sourceCommitPath "source_commit"
if ($pulledSourceCommit -ne $expectedCommit) {
    throw "source_commit_mismatch:expected=$expectedCommit;pulled=$pulledSourceCommit"
}
$null = Read-CommitFile $isaacLabCommitPath "isaaclab_repo_commit"

$validator = Join-Path $repository "workflows/validate_easyuuv_v2_qualification.py"
$validatorOutput = @(
    & $PythonExecutable $validator $qualificationPath --json `
        --expected-source-commit-file $expectedCommitPath `
        --expected-isaaclab-commit-file $isaacLabCommitPath 2>&1
)
$validatorExitCode = $LASTEXITCODE
$validatorText = ($validatorOutput -join "`n") + "`n"
[IO.File]::WriteAllText(
    (Join-Path $stagedEvidence "pullback_validator.json"),
    $validatorText,
    [Text.UTF8Encoding]::new($false)
)
if ($validatorExitCode -ne 0) {
    throw "validator_failed:$validatorExitCode;staging=$stagingRoot"
}
$validatorResult = $validatorText | ConvertFrom-Json
if (
    $validatorResult.qualification_gate -ne "server_pass" -or
    $validatorResult.configuration_count -ne 8
) {
    throw "validator_result_invalid"
}

$canonicalEvidence = Join-Path $repository $CanonicalEvidenceDirectory
if (Test-Path -LiteralPath $canonicalEvidence) {
    throw "canonical_evidence_already_exists:$canonicalEvidence"
}
$canonicalParent = Split-Path -Parent $canonicalEvidence
$null = New-Item -ItemType Directory -Path $canonicalParent -Force
Move-Item -LiteralPath $stagedEvidence -Destination $canonicalEvidence

Write-Output "qualification_gate=server_pass"
Write-Output "configuration_count=8"
Write-Output "source_commit=$expectedCommit"
Write-Output "artifact_sha256=$localHash"
Write-Output "canonical_evidence=$canonicalEvidence"
