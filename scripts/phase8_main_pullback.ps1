[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$Remote = "agentic-AUV",
    [string]$RemoteEvidenceRoot = "/root/EASYkoopman-phase8-main-v2/source/results/koopman_phase8_dataset",
    [string]$RemoteStatusRoot = "/root/EASYkoopman-phase8-main-v2/source/results/koopman_phase8_main_status",
    [string]$TransferDirectory = ".pytest-tmp/phase8-main-transfer",
    [string]$CanonicalEvidenceDirectory = "source/results/koopman_phase8_dataset",
    [string]$PythonExecutable = ""
)
$ErrorActionPreference = "Stop"; Set-StrictMode -Version Latest
if (-not $RepositoryRoot) { $RepositoryRoot = Join-Path (Split-Path -Parent $PSCommandPath) ".." }
$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe" }
function Read-Exact { param([string]$Path,[string]$Pattern,[string]$Reason); if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Reason`:missing" }; $value=(Get-Content -Raw -LiteralPath $Path).Trim(); if ($value -notmatch $Pattern) { throw "$Reason`:invalid" }; return $value }
function Test-Inventory {
    param([string]$Root,[string]$Inventory)
    $expected=@{}; foreach($line in Get-Content -LiteralPath $Inventory) {
        if($line -notmatch '^([0-9a-f]{64})  \./(.+)$'){throw "inventory_line_invalid"}
        $relative=$Matches[2]; $candidate=Join-Path $Root $relative
        if(-not(Test-Path -LiteralPath $candidate -PathType Leaf)){throw "inventory_file_missing:$relative"}
        if((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $Matches[1]){throw "inventory_hash_mismatch:$relative"}
        $expected[$relative]=$true
    }
    $actual=@{}; foreach($item in Get-ChildItem -LiteralPath $Root -File -Recurse -Force){$actual[$item.FullName.Substring($Root.Length).TrimStart('\','/').Replace('\','/')]=$true}
    if($actual.Count -ne $expected.Count){throw "inventory_file_set_mismatch"}; foreach($key in $actual.Keys){if(-not $expected.ContainsKey($key)){throw "inventory_file_set_mismatch:$key"}}
}

$expectedCommit=Read-Exact (Join-Path $repository "$TransferDirectory/expected-source-commit.txt") '^[0-9a-f]{40}$' 'expected_source_commit'
$localHead=(& git -C $repository rev-parse HEAD).Trim(); if($localHead -ne $expectedCommit){throw "source_commit_mismatch"}
$status=(& git -c core.excludesFile= -C $repository status --porcelain=v1 --untracked-files=all -- . ':(exclude).gitignore' ':(exclude)AGENTS.md') -join "`n"; if($status){throw "worktree_dirty:$status"}
$canonical=Join-Path $repository $CanonicalEvidenceDirectory; if(Test-Path -LiteralPath $canonical){throw "canonical_evidence_already_exists"}
$staging=Join-Path $repository ".pytest-tmp/phase8-main-pullback-$([Guid]::NewGuid().ToString('N'))"; $null=New-Item -ItemType Directory -Path $staging
& scp -r "${Remote}:$RemoteEvidenceRoot" $staging; if($LASTEXITCODE -ne 0){throw "scp_failed:evidence"}
& scp -r "${Remote}:$RemoteStatusRoot" $staging; if($LASTEXITCODE -ne 0){throw "scp_failed:status"}
$evidence=Join-Path $staging "koopman_phase8_dataset"; $statusRoot=Join-Path $staging "koopman_phase8_main_status"
foreach($configuration in @('base','long_body','heavy_moderate','asymmetric','uuv6','uuv6_angled','uuv4','uuv4_angled')){
    if((Read-Exact (Join-Path $statusRoot "$configuration.native_status") '^0$' 'native_status') -ne '0'){throw "native_status_failed"}
    if((Read-Exact (Join-Path $statusRoot "$configuration.tee_status") '^0$' 'tee_status') -ne '0'){throw "tee_status_failed"}
    if((Read-Exact (Join-Path $statusRoot "$configuration.semantic_status") '^pass$' 'semantic_status') -ne 'pass'){throw "semantic_status_failed"}
}
Test-Inventory $evidence (Join-Path $statusRoot "all_files.sha256")
$roleHash=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $evidence "main_role_assignment_protocol.json")).Hash.ToLowerInvariant()
$analysisHash=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $evidence "analysis_policy.json")).Hash.ToLowerInvariant()
$expectedRole=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repository "protocols/phase8/main_role_assignment_protocol.json")).Hash.ToLowerInvariant()
$expectedAnalysis=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repository "protocols/phase8/analysis_policy.json")).Hash.ToLowerInvariant()
if($roleHash -ne $expectedRole){throw "role_protocol_sha256_mismatch"}; if($analysisHash -ne $expectedAnalysis){throw "analysis_policy_sha256_mismatch"}
$serverEnvelopeHash=(Read-Exact (Join-Path $statusRoot "dataset_envelope.sha256") '^([0-9a-f]{64})\s+' 'server_sha256').Split(' ')[0]
$localEnvelopeHash=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $evidence "dataset_envelope.json")).Hash.ToLowerInvariant(); if($serverEnvelopeHash -ne $localEnvelopeHash){throw "sha256_mismatch"}
& $PythonExecutable workflows/validate_phase8_evidence.py --envelope (Join-Path $evidence "dataset_envelope.json") --qualification server_isaac_identification_dataset --json
if($LASTEXITCODE -ne 0){throw "local_validator_failed"}
$inventory=Get-Content -Raw (Join-Path $evidence "dataset_inventory.json") | ConvertFrom-Json
$envelope=Get-Content -Raw (Join-Path $evidence "dataset_envelope.json") | ConvertFrom-Json
if($inventory.source_commit -ne $expectedCommit -or $envelope.source_commit -ne $expectedCommit){throw "source_commit_mismatch"}
if($inventory.role_protocol_sha256 -ne $roleHash){throw "role_protocol_sha256_mismatch"}
if($envelope.runtime_sha256 -ne $inventory.runtime_sha256){throw "runtime_version_mismatch"}
$null=New-Item -ItemType Directory -Path (Split-Path -Parent $canonical) -Force
Move-Item -LiteralPath $evidence -Destination $canonical
Write-Output "validation_gate=phase8_external_evidence_valid"; Write-Output "qualification_level=server_isaac_identification_dataset"; Write-Output "canonical_evidence=$canonical"
