[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$Remote = "agentic-AUV",
    [string]$RemoteDatasetRoot = "/root/EASYkoopman-phase8-2-results-v2/dataset",
    [string]$RemoteStatusRoot = "/root/EASYkoopman-phase8-2-results-v2/status",
    [string]$TransferDirectory = ".pytest-tmp/phase8-2-transfer",
    [string]$CanonicalRoot = "source/results/koopman_phase8_2",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$canonicalDatasetContract = "source/results/koopman_phase8_2/dataset"
if (-not $RepositoryRoot) { $RepositoryRoot = Join-Path (Split-Path -Parent $PSCommandPath) ".." }
$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe" }

function Read-Exact {
    param([string]$Path, [string]$Pattern, [string]$Reason)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Reason`:missing" }
    $value = (Get-Content -Raw -LiteralPath $Path).Trim()
    if ($value -notmatch $Pattern) { throw "$Reason`:invalid" }
    return $value
}
function Test-Inventory {
    param([string]$Root, [string]$Inventory)
    $expected = @{}
    foreach ($line in Get-Content -LiteralPath $Inventory) {
        if ($line -notmatch '^([0-9a-f]{64})  \./(.+)$') { throw "inventory_line_invalid" }
        $relative = $Matches[2]
        if ($relative.Contains('..') -or [IO.Path]::IsPathRooted($relative)) { throw "inventory_path_invalid:$relative" }
        $candidate = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "inventory_file_missing:$relative" }
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $Matches[1]) { throw "inventory_hash_mismatch:$relative" }
        if ($expected.ContainsKey($relative)) { throw "inventory_duplicate:$relative" }
        $expected[$relative] = $true
    }
    $actual = @{}
    foreach ($item in Get-ChildItem -LiteralPath $Root -File -Recurse -Force) {
        $relative = $item.FullName.Substring($Root.Length).TrimStart('\','/').Replace('\','/')
        $actual[$relative] = $true
    }
    if ($actual.Count -ne $expected.Count) { throw "inventory_file_set_mismatch" }
    foreach ($key in $actual.Keys) { if (-not $expected.ContainsKey($key)) { throw "inventory_file_set_mismatch:$key" } }
}

$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repository
    $expectedCommit = Read-Exact (Join-Path $TransferDirectory "expected-source-commit.txt") '^[0-9a-f]{40}$' 'expected_source_commit'
    $localHead = (& git rev-parse HEAD).Trim()
    if ($localHead -ne $expectedCommit) { throw "source_commit_mismatch" }
    $status = (& git -c core.excludesFile= status --porcelain=v1 --untracked-files=all) -join "`n"
    if ($status) { throw "worktree_dirty:$status" }
    if (Test-Path -LiteralPath $CanonicalRoot) { throw "canonical_phase8_2_root_exists" }
    $staging = Join-Path $repository ".pytest-tmp/phase8-2-pullback-$([Guid]::NewGuid().ToString('N'))"
    $null = New-Item -ItemType Directory -Path $staging
    & scp -r "${Remote}:$RemoteDatasetRoot" $staging
    if ($LASTEXITCODE -ne 0) { throw "scp_failed:dataset" }
    & scp -r "${Remote}:$RemoteStatusRoot" $staging
    if ($LASTEXITCODE -ne 0) { throw "scp_failed:status" }
    $dataset = Join-Path $staging "dataset"
    $statusRoot = Join-Path $staging "status"
    foreach ($configuration in @('base','long_body','heavy_moderate','asymmetric','uuv6','uuv6_angled','uuv4','uuv4_angled')) {
        if ((Read-Exact (Join-Path $statusRoot "$configuration.native_status") '^0$' 'native_status') -ne '0') { throw "native_status_failed" }
        if ((Read-Exact (Join-Path $statusRoot "$configuration.tee_status") '^0$' 'tee_status') -ne '0') { throw "tee_status_failed" }
        if ((Read-Exact (Join-Path $statusRoot "$configuration.semantic_status") '^pass$' 'semantic_status') -ne 'pass') { throw "semantic_status_failed" }
    }
    if ((Read-Exact (Join-Path $statusRoot "collection_complete.status") '^pass$' 'collection_complete') -ne 'pass') { throw "collection_incomplete" }
    if ((Read-Exact (Join-Path $statusRoot "source_commit.txt") '^[0-9a-f]{40}$' 'server_source_commit') -ne $expectedCommit) { throw "source_commit_mismatch" }
    Test-Inventory $dataset (Join-Path $statusRoot "all_files.sha256")

    $role = "protocols/phase8_1/main_role_assignment_protocol.json"
    $policy = "protocols/phase8_1/analysis_policy.json"
    $approval = "protocols/phase8_1/d23_approval.json"
    $protocolBindings = [ordered]@{
        "role_protocol.sha256" = $role
        "analysis_policy.sha256" = $policy
        "d23_approval.sha256" = $approval
    }
    foreach ($binding in $protocolBindings.GetEnumerator()) {
        $remoteHash = Read-Exact (Join-Path $statusRoot $binding.Key) '^[0-9a-f]{64}$' 'server_protocol_hash'
        $localHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $binding.Value).Hash.ToLowerInvariant()
        if ($remoteHash -ne $localHash) { throw "protocol_hash_mismatch:$($binding.Value)" }
    }
    & $PythonExecutable workflows/validate_phase81_d23_approval.py `
        --approval-record $approval --role-protocol $role --analysis-policy $policy
    if ($LASTEXITCODE -ne 0) { throw "canonical_d23_validation_failed" }
    & $PythonExecutable workflows/validate_phase82_dataset_index.py `
        --dataset-root $dataset --role-protocol $role `
        --inventory (Join-Path $dataset "dataset_inventory.json") `
        --split (Join-Path $dataset "loco_split_manifest.json") `
        --source-commit $expectedCommit
    if ($LASTEXITCODE -ne 0) { throw "phase8_2_dataset_validation_failed" }

    $promotion = Join-Path $staging "promotion/koopman_phase8_2"
    $null = New-Item -ItemType Directory -Path $promotion
    Move-Item -LiteralPath $dataset -Destination (Join-Path $promotion "dataset")
    Move-Item -LiteralPath $statusRoot -Destination (Join-Path $promotion "collection_status")
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent (Join-Path $repository $CanonicalRoot)) -Force
    Move-Item -LiteralPath $promotion -Destination (Join-Path $repository $CanonicalRoot)
    Write-Output "phase8_2_pullback=pass"
    if ($CanonicalRoot -eq "source/results/koopman_phase8_2") {
        Write-Output "canonical_dataset=$(Join-Path $repository $canonicalDatasetContract)"
    }
    else { Write-Output "canonical_dataset=$(Join-Path $repository "$CanonicalRoot/dataset")" }
}
finally { Set-Location -LiteralPath $previousLocation }
