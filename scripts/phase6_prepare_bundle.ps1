[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$Branch = "v2.0-multi-configuration",
    [string]$TransferDirectory = ".pytest-tmp/phase6-transfer"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $output = & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git_failed:$($Arguments -join ' ')"
    }
    return ($output -join "`n").Trim()
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$previousLocation = Get-Location
try {
    Set-Location -LiteralPath $repository
    $currentBranch = Invoke-Git branch --show-current
    if ($currentBranch -ne $Branch) {
        throw "branch_mismatch:expected=$Branch;actual=$currentBranch"
    }

    $trackedStatus = Invoke-Git status --porcelain=v1 --untracked-files=no
    if ($trackedStatus) {
        throw "tracked_worktree_dirty"
    }

    $head = Invoke-Git rev-parse HEAD
    $branchCommit = Invoke-Git rev-parse "$Branch^{commit}"
    if ($head -ne $branchCommit) {
        throw "tested_head_not_branch_tip:head=$head;branch=$branchCommit"
    }

    $transferRoot = Join-Path $repository $TransferDirectory
    if (Test-Path -LiteralPath $transferRoot) {
        throw "transfer_directory_already_exists:$transferRoot"
    }
    $null = New-Item -ItemType Directory -Path $transferRoot
    $bundlePath = Join-Path $transferRoot "EasyUUV-phase6-v2.bundle"
    $sidecarPath = Join-Path $transferRoot "expected-source-commit.txt"
    $bootstrapPath = Join-Path $transferRoot "phase6_server_bootstrap.sh"

    $null = Invoke-Git bundle create $bundlePath $Branch
    $null = Invoke-Git bundle verify $bundlePath
    $bundleHead = Invoke-Git bundle list-heads $bundlePath "refs/heads/$Branch"
    $parts = $bundleHead -split "\s+", 2
    if ($parts.Count -ne 2 -or $parts[0] -ne $head -or $parts[1] -ne "refs/heads/$Branch") {
        throw "bundle_ref_mismatch:$bundleHead"
    }

    [IO.File]::WriteAllText($sidecarPath, "$head`n", [Text.UTF8Encoding]::new($false))
    $bootstrapSpec = "${head}:scripts/phase6_server_bootstrap.sh"
    $bootstrapContent = Invoke-Git show $bootstrapSpec
    [IO.File]::WriteAllText(
        $bootstrapPath,
        ($bootstrapContent -replace "`r`n", "`n") + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    Write-Output "tested_head=$head"
    Write-Output "bundle_path=$bundlePath"
    Write-Output "expected_commit_sidecar=$sidecarPath"
    Write-Output "server_bootstrap=$bootstrapPath"
}
finally {
    Set-Location -LiteralPath $previousLocation
}
