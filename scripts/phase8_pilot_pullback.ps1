[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$Remote = "agentic-AUV",
    [string]$RemoteEvidenceRoot = "/root/EASYkoopman-phase8-pilot-v2/source/results/koopman_phase8_pilot",
    [string]$RemoteStatusRoot = "/root/EASYkoopman-phase8-pilot-v2/source/results/koopman_phase8_pilot_status",
    [string]$TransferDirectory = ".pytest-tmp/phase8-pilot-transfer",
    [string]$CanonicalEvidenceDirectory = "source/results/koopman_phase8_pilot",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$expectedIsaacLabReleaseTag = "v2.2.1"
$expectedIsaacLabReleaseCommit = "0f00ca2b4b2d54d5f90006a92abb1b00a72b2f20"
$expectedIsaacLabRepoCommit = "c91a125c73c8b574878419a9583afc0b63b99f0a"
$expectedIsaacLabPatchSha256 = "d056adb8bb64fe7c9c34fffbd2478ef04155df8b60b071da942280952f829079"
$expectedIsaacLabDirtyFiles = @(
    "source/isaaclab_mimic/setup.py",
    "source/isaaclab_rl/setup.py"
)

$scriptPath = $PSCommandPath
if (-not $scriptPath) { $scriptPath = $MyInvocation.MyCommand.Path }
if (-not $RepositoryRoot) {
    if (-not $scriptPath) { throw "script_path_unavailable" }
    $RepositoryRoot = Join-Path (Split-Path -Parent $scriptPath) ".."
}

function Read-Exact {
    param([string]$Path, [string]$Label, [string]$Pattern)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "${Label}_missing:$Path" }
    $value = (Get-Content -Raw -LiteralPath $Path).Trim()
    if ($value -notmatch $Pattern) { throw "${Label}_invalid" }
    return $value
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

function Test-RemoteInventory {
    param([string]$Root, [string]$Inventory)
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw "inventory_root_missing" }
    if (-not (Test-Path -LiteralPath $Inventory -PathType Leaf)) { throw "inventory_missing" }
    $rootPath = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\', '/')
    $expected = @{}
    foreach ($line in Get-Content -LiteralPath $Inventory) {
        if ($line -notmatch '^([0-9a-f]{64})  \./(.+)$') { throw "inventory_line_invalid" }
        $expectedHash = $Matches[1]
        $relative = $Matches[2]
        if ($relative.Contains('\') -or $relative.StartsWith('/') -or $relative.Split('/') -contains '..') {
            throw "inventory_path_invalid:$relative"
        }
        if ($expected.ContainsKey($relative)) { throw "inventory_duplicate:$relative" }
        $candidate = Join-Path $rootPath ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "inventory_file_missing:$relative" }
        $item = Get-Item -LiteralPath $candidate -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "inventory_reparse_point:$relative"
        }
        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) { throw "inventory_hash_mismatch:$relative" }
        $expected[$relative] = $true
    }
    $actual = @{}
    foreach ($item in Get-ChildItem -LiteralPath $rootPath -File -Recurse -Force) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "inventory_reparse_point:$($item.FullName)"
        }
        $relative = $item.FullName.Substring($rootPath.Length).TrimStart('\', '/').Replace('\', '/')
        $actual[$relative] = $true
    }
    if ($expected.Count -ne $actual.Count) { throw "inventory_file_set_mismatch" }
    foreach ($relative in $actual.Keys) {
        if (-not $expected.ContainsKey($relative)) { throw "inventory_unexpected_file:$relative" }
    }
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe" }
$transferRoot = Join-Path $repository $TransferDirectory
$sidecar = Join-Path $transferRoot "expected-source-commit.txt"
$expectedCommit = Read-Exact $sidecar "expected_source_commit" '^[0-9a-f]{40}$'
$localHead = Invoke-Git -C $repository rev-parse HEAD
if ($localHead -ne $expectedCommit) { throw "local_head_mismatch" }
$status = Invoke-Git -c "core.excludesFile=" -C $repository status --porcelain=v1 --untracked-files=all
if ($status) { throw "worktree_dirty" }

$stagingRoot = Join-Path (Join-Path $repository ".pytest-tmp") "phase8-pilot-pullback-$([Guid]::NewGuid().ToString('N'))"
if (Test-Path -LiteralPath $stagingRoot) { throw "staging_directory_already_exists" }
$null = New-Item -ItemType Directory -Path $stagingRoot
& scp -r "${Remote}:$RemoteStatusRoot" $stagingRoot
if ($LASTEXITCODE -ne 0) { throw "scp_failed:status:$LASTEXITCODE;staging=$stagingRoot" }
& scp -r "${Remote}:$RemoteEvidenceRoot" $stagingRoot
if ($LASTEXITCODE -ne 0) { throw "scp_failed:evidence:$LASTEXITCODE;staging=$stagingRoot" }

$stagedEvidence = Join-Path $stagingRoot "koopman_phase8_pilot"
$stagedStatus = Join-Path $stagingRoot "koopman_phase8_pilot_status"
if (-not (Test-Path -LiteralPath $stagedEvidence -PathType Container)) { throw "staged_evidence_missing" }
if (-not (Test-Path -LiteralPath $stagedStatus -PathType Container)) { throw "staged_status_missing" }
foreach ($configuration in @("base","long_body","heavy_moderate","asymmetric","uuv6","uuv6_angled","uuv4","uuv4_angled")) {
    $native_status = Read-Exact (Join-Path $stagedStatus "$configuration.native_status") "native_status" '^0$'
    $tee_status = Read-Exact (Join-Path $stagedStatus "$configuration.tee_status") "tee_status" '^0$'
    $semantic_status = Read-Exact (Join-Path $stagedStatus "$configuration.semantic_status") "semantic_status" '^pass$'
    if ($native_status -ne "0" -or $tee_status -ne "0" -or $semantic_status -ne "pass") {
        throw "process_status_failed:$configuration"
    }
}

Test-RemoteInventory $stagedEvidence (Join-Path $stagedStatus "all_files.sha256")
$envelope = Join-Path $stagedEvidence "pilot_envelope.json"
$serverHashLine = (Get-Content -Raw -LiteralPath (Join-Path $stagedStatus "pilot_envelope.sha256")).Trim()
if ($serverHashLine -notmatch '^([0-9a-f]{64})\s+') { throw "server_sha256_invalid" }
$serverHash = $Matches[1]
$localHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $envelope).Hash.ToLowerInvariant()
if ($serverHash -ne $localHash) { throw "sha256_mismatch:server=$serverHash;local=$localHash" }

$pulledCommit = Read-Exact (Join-Path $stagedStatus "source_commit.txt") "source_commit" '^[0-9a-f]{40}$'
if ($pulledCommit -ne $expectedCommit) { throw "source_commit_mismatch" }
$labTag = Read-Exact (Join-Path $stagedStatus "isaaclab_release_tag.txt") "isaaclab_release_tag" '^v2\.2\.1$'
$labReleaseCommit = Read-Exact (Join-Path $stagedStatus "isaaclab_release_commit.txt") "isaaclab_release_commit" '^[0-9a-f]{40}$'
$labRepoCommit = Read-Exact (Join-Path $stagedStatus "isaaclab_repo_commit.txt") "isaaclab_repo_commit" '^[0-9a-f]{40}$'
$labRepoParentCommit = Read-Exact (Join-Path $stagedStatus "isaaclab_repo_parent_commit.txt") "isaaclab_repo_parent_commit" '^[0-9a-f]{40}$'
$labRepoPatchSha256 = Read-Exact (Join-Path $stagedStatus "isaaclab_repo_patch.sha256") "isaaclab_repo_patch" '^[0-9a-f]{64}$'
$labRepoDirtyFiles = Read-Exact (Join-Path $stagedStatus "isaaclab_repo_dirty_files.txt") "isaaclab_repo_dirty_files" '.+'
$simVersion = Read-Exact (Join-Path $stagedStatus "isaac_sim_version.txt") "isaac_sim_version" '^5\.0$'
$labVersion = Read-Exact (Join-Path $stagedStatus "isaaclab_version.txt") "isaaclab_version" '^2\.2\.1$'
if ($simVersion -ne "5.0" -or $labVersion -ne "2.2.1") { throw "runtime_version_mismatch" }
if (
    $labTag -ne $expectedIsaacLabReleaseTag -or
    $labReleaseCommit -ne $expectedIsaacLabReleaseCommit -or
    $labRepoCommit -ne $expectedIsaacLabRepoCommit -or
    $labRepoParentCommit -ne $expectedIsaacLabReleaseCommit -or
    $labRepoPatchSha256 -ne $expectedIsaacLabPatchSha256 -or
    $labRepoDirtyFiles -ne ($expectedIsaacLabDirtyFiles -join "`n")
) { throw "isaaclab_provenance_mismatch" }

$policyValidator = Join-Path $repository "workflows/validate_phase8_pilot_policy.py"
$policy = Join-Path $stagedEvidence "pilot_collection_policy.json"
$policyValidatorStdout = [IO.Path]::GetTempFileName()
$policyValidatorStderr = [IO.Path]::GetTempFileName()
try {
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $PythonExecutable $policyValidator `
            --policy $policy `
            --json 1> $policyValidatorStdout 2> $policyValidatorStderr
        $policyValidatorExitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
    $policyValidatorOutput = [IO.File]::ReadAllText($policyValidatorStdout)
    $policyValidatorError = [IO.File]::ReadAllText($policyValidatorStderr).Trim()
}
finally {
    Remove-Item -LiteralPath $policyValidatorStdout, $policyValidatorStderr -Force -ErrorAction SilentlyContinue
}
if ($policyValidatorExitCode -ne 0) {
    throw "pilot_policy_validator_failed:$policyValidatorExitCode;staging=$stagingRoot;$policyValidatorError"
}
$policyValidatorResult = $policyValidatorOutput | ConvertFrom-Json
$policyHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $policy).Hash.ToLowerInvariant()
if (
    $policyValidatorResult.validation_gate -ne "phase8_pilot_operational_policy_valid" -or
    $policyValidatorResult.policy_sha256 -ne $policyHash
) { throw "pilot_policy_validator_result_invalid" }

$validator = Join-Path $repository "workflows/validate_phase8_evidence.py"
$validatorStdout = [IO.Path]::GetTempFileName()
$validatorStderr = [IO.Path]::GetTempFileName()
try {
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $PythonExecutable $validator `
            --envelope $envelope `
            --qualification server_isaac_identification_pilot `
            --json 1> $validatorStdout 2> $validatorStderr
        $validatorExitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
    $validatorOutput = [IO.File]::ReadAllText($validatorStdout)
    $validatorError = [IO.File]::ReadAllText($validatorStderr).Trim()
}
finally {
    Remove-Item -LiteralPath $validatorStdout, $validatorStderr -Force -ErrorAction SilentlyContinue
}
if ($validatorExitCode -ne 0) {
    throw "validator_failed:$validatorExitCode;staging=$stagingRoot;$validatorError"
}
$validatorResult = $validatorOutput | ConvertFrom-Json
if (
    $validatorResult.validation_gate -ne "phase8_external_evidence_valid" -or
    $validatorResult.qualification_level -ne "server_isaac_identification_pilot" -or
    $validatorResult.source_commit -ne $expectedCommit
) { throw "validator_result_invalid" }

$canonicalEvidence = Join-Path $repository $CanonicalEvidenceDirectory
if (Test-Path -LiteralPath $canonicalEvidence) { throw "canonical_evidence_already_exists:$canonicalEvidence" }
$null = New-Item -ItemType Directory -Path (Split-Path -Parent $canonicalEvidence) -Force
Move-Item -LiteralPath $stagedEvidence -Destination $canonicalEvidence
Write-Output "validation_gate=phase8_external_evidence_valid"
Write-Output "qualification_level=server_isaac_identification_pilot"
Write-Output "source_commit=$expectedCommit"
Write-Output "artifact_sha256=$localHash"
Write-Output "canonical_evidence=$canonicalEvidence"
