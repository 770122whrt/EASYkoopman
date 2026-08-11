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

function Read-IsaacLabReleaseFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "isaaclab_release_tag_missing:$Path"
    }
    $value = (Get-Content -Raw -LiteralPath $Path).Trim()
    if ($value -notmatch '^v\d+\.\d+\.\d+$') {
        throw "isaaclab_release_tag_invalid"
    }
    return $value
}

function Read-Sha256File {
    param([string]$Path, [string]$Label)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "${Label}_missing:$Path"
    }
    $value = (Get-Content -Raw -LiteralPath $Path).Trim()
    if ($value -notmatch '^[0-9a-f]{64}$') {
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

$localHeadOutput = @(& git -C $repository rev-parse HEAD 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "local_head_probe_failed:$LASTEXITCODE"
}
$localHead = ($localHeadOutput -join "`n").Trim()
if ($localHead -ne $expectedCommit) {
    throw "local_head_mismatch:expected=$expectedCommit;actual=$localHead"
}

$worktreeStatusOutput = @(
    & git -C $repository status --porcelain=v1 2>&1
)
if ($LASTEXITCODE -ne 0) {
    throw "local_status_probe_failed:$LASTEXITCODE"
}
$worktreeStatus = ($worktreeStatusOutput -join "`n").Trim()
if ($worktreeStatus) {
    throw "worktree_dirty"
}

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
$isaacLabReleasePath = Join-Path $stagedEvidence "isaaclab_release_tag.txt"
$isaacLabReleaseCommitPath = Join-Path $stagedEvidence "isaaclab_release_commit.txt"
$isaacLabParentCommitPath = Join-Path $stagedEvidence "isaaclab_repo_parent_commit.txt"
$isaacLabPatchHashPath = Join-Path $stagedEvidence "isaaclab_repo_patch.sha256"
$isaacLabPatchPath = Join-Path $stagedEvidence "logs/isaaclab_repo_diff.patch"
$isaacLabDirtyFilesPath = Join-Path $stagedEvidence "isaaclab_repo_dirty_files.txt"

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
$releaseCommit = Read-CommitFile $isaacLabReleaseCommitPath "isaaclab_release_commit"
$parentCommit = Read-CommitFile $isaacLabParentCommitPath "isaaclab_repo_parent_commit"
if ($releaseCommit -ne $parentCommit) {
    throw "isaaclab_release_parent_mismatch"
}
$null = Read-IsaacLabReleaseFile $isaacLabReleasePath
$expectedPatchHash = Read-Sha256File $isaacLabPatchHashPath "isaaclab_patch_sha256"
if (-not (Test-Path -LiteralPath $isaacLabPatchPath -PathType Leaf)) {
    throw "isaaclab_patch_file_missing:$isaacLabPatchPath"
}
$pulledPatchHash = (
    Get-FileHash -Algorithm SHA256 -LiteralPath $isaacLabPatchPath
).Hash.ToLowerInvariant()
if ($pulledPatchHash -ne $expectedPatchHash) {
    throw "isaaclab_patch_sha256_mismatch:expected=$expectedPatchHash;actual=$pulledPatchHash"
}
if (-not (Test-Path -LiteralPath $isaacLabDirtyFilesPath -PathType Leaf)) {
    throw "isaaclab_dirty_files_missing:$isaacLabDirtyFilesPath"
}

$validator = Join-Path $repository "workflows/validate_easyuuv_v2_qualification.py"
$validatorOutput = @(
    & $PythonExecutable $validator $qualificationPath --json `
        --expected-source-commit-file $expectedCommitPath `
        --expected-isaaclab-commit-file $isaacLabCommitPath `
        --expected-isaaclab-release-file $isaacLabReleasePath `
        --expected-isaaclab-release-commit-file $isaacLabReleaseCommitPath `
        --expected-isaaclab-patch-sha256-file $isaacLabPatchHashPath `
        --expected-isaaclab-dirty-files-file $isaacLabDirtyFilesPath 2>&1
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
