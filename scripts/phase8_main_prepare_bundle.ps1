[CmdletBinding()]
param([string]$RepositoryRoot = "", [string]$TransferDirectory = ".pytest-tmp/phase8-main-transfer")
$ErrorActionPreference = "Stop"; Set-StrictMode -Version Latest
if (-not $RepositoryRoot) { $RepositoryRoot = Join-Path (Split-Path -Parent $PSCommandPath) ".." }
$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
Set-Location -LiteralPath $repository
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/phase8_main_local_preflight.ps1 -RepositoryRoot $repository
if ($LASTEXITCODE -ne 0) { throw "main_preflight_failed" }
$status = (& git -c core.excludesFile= status --porcelain=v1 --untracked-files=all -- . ':(exclude).gitignore' ':(exclude)AGENTS.md') -join "`n"
if ($status) { throw "worktree_dirty:$status" }
$head = (& git rev-parse HEAD).Trim(); if ($head -notmatch '^[0-9a-f]{40}$') { throw "source_commit_invalid" }
$transfer = Join-Path $repository $TransferDirectory
if (Test-Path -LiteralPath $transfer) { throw "transfer_directory_exists" }
$null = New-Item -ItemType Directory -Path $transfer
$bundle = Join-Path $transfer "EasyUUV-phase8-main-v2.bundle"
& git bundle create $bundle HEAD; if ($LASTEXITCODE -ne 0) { throw "bundle_create_failed" }
& git bundle verify $bundle; if ($LASTEXITCODE -ne 0) { throw "incomplete_bundle" }
Set-Content -NoNewline -Encoding ascii (Join-Path $transfer "expected-source-commit.txt") "$head`n"
Copy-Item -LiteralPath scripts/phase8_main_server_bootstrap.sh -Destination (Join-Path $transfer "phase8_main_server_bootstrap.sh")
foreach ($name in @("main_role_assignment_protocol.json","analysis_policy.json")) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repository "protocols/phase8/$name")).Hash.ToLowerInvariant()
    Set-Content -NoNewline -Encoding ascii (Join-Path $transfer "$name.sha256") "$hash`n"
}
Write-Output "phase8_main_bundle=pass"; Write-Output "source_commit=$head"; Write-Output "bundle=$bundle"
