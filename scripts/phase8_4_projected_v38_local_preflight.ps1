param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $RepositoryRoot
try {
    & $Python -X utf8 -B -m workflows.package_projected_v38 preflight --root $RepositoryRoot --python $Python --directory $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw "v38 local preflight failed with native exit $LASTEXITCODE" }
} finally {
    Pop-Location
}
