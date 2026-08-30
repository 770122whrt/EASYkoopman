[CmdletBinding()]
param(
    [string]$RepositoryRoot = "",
    [string]$TransferDirectory = ".pytest-tmp/phase8-2-transfer",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not $RepositoryRoot) { $RepositoryRoot = Join-Path (Split-Path -Parent $PSCommandPath) ".." }
$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if (-not $PythonExecutable) { $PythonExecutable = Join-Path $repository ".venv/Scripts/python.exe" }
$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repository
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/phase8_2_local_preflight.ps1 `
        -RepositoryRoot $repository -PythonExecutable $PythonExecutable
    if ($LASTEXITCODE -ne 0) { throw "phase8_2_local_preflight_failed:$LASTEXITCODE" }
    $status = (& git -c core.excludesFile= status --porcelain=v1 --untracked-files=all) -join "`n"
    if ($status) { throw "worktree_dirty:$status" }
    $head = (& git rev-parse HEAD).Trim()
    $branch = (& git branch --show-current).Trim()
    if ($head -notmatch '^[0-9a-f]{40}$' -or -not $branch) { throw "source_identity_invalid" }
    $transfer = Join-Path $repository $TransferDirectory
    if (Test-Path -LiteralPath $transfer) { throw "transfer_directory_exists" }
    $null = New-Item -ItemType Directory -Path $transfer
    $bundle = Join-Path $transfer "EasyUUV-phase8-2-v1.bundle"
    & git bundle create $bundle $branch
    if ($LASTEXITCODE -ne 0) { throw "bundle_create_failed" }
    & git bundle verify $bundle
    if ($LASTEXITCODE -ne 0) { throw "bundle_verify_failed" }
    $bundleHead = (& git bundle list-heads $bundle "refs/heads/$branch") -join "`n"
    if ($bundleHead.Trim() -ne "$head refs/heads/$branch") { throw "bundle_ref_mismatch:$bundleHead" }

    $verifyRoot = Join-Path $repository ".pytest-tmp/phase8-2-bundle-verify-$([Guid]::NewGuid().ToString('N'))"
    try {
        & git clone --no-local $bundle $verifyRoot
        if ($LASTEXITCODE -ne 0) { throw "offline_bundle_clone_failed" }
        & git -C $verifyRoot checkout --detach $head
        if ($LASTEXITCODE -ne 0) { throw "offline_bundle_checkout_failed" }
        if ((& git -C $verifyRoot rev-parse HEAD).Trim() -ne $head) { throw "offline_bundle_head_mismatch" }
        $verifyStatus = (& git -C $verifyRoot -c core.excludesFile= status --porcelain=v1 --untracked-files=all) -join "`n"
        if ($verifyStatus) { throw "offline_bundle_clone_dirty:$verifyStatus" }
    }
    finally {
        if (Test-Path -LiteralPath $verifyRoot) { Remove-Item -LiteralPath $verifyRoot -Recurse -Force }
    }

    Set-Content -NoNewline -Encoding ascii (Join-Path $transfer "expected-source-commit.txt") "$head`n"
    Set-Content -NoNewline -Encoding ascii (Join-Path $transfer "expected-branch.txt") "$branch`n"
    foreach ($binding in @{
        "role-protocol.sha256" = "protocols/phase8_1/main_role_assignment_protocol.json"
        "analysis-policy.sha256" = "protocols/phase8_1/analysis_policy.json"
        "d23-approval.sha256" = "protocols/phase8_1/d23_approval.json"
    }.GetEnumerator()) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $binding.Value).Hash.ToLowerInvariant()
        Set-Content -NoNewline -Encoding ascii (Join-Path $transfer $binding.Key) "$hash`n"
    }
    $bundleHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $bundle).Hash.ToLowerInvariant()
    Set-Content -NoNewline -Encoding ascii (Join-Path $transfer "bundle.sha256") "$bundleHash`n"
    Copy-Item -LiteralPath scripts/phase8_2_server_bootstrap.sh -Destination (Join-Path $transfer "phase8_2_server_bootstrap.sh")
    Write-Output "phase8_2_offline_bundle=pass"
    Write-Output "source_commit=$head"
    Write-Output "bundle_path=$bundle"
    Write-Output "bundle_sha256=$bundleHash"
}
finally { Set-Location -LiteralPath $previousLocation }
