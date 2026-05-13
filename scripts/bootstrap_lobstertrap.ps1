param(
    [string]$RepoUrl = "https://github.com/veeainc/lobstertrap.git",
    [string]$Ref = "main",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$toolRoot = Join-Path $repoRoot ".tools\lobstertrap"
$srcDir = Join-Path $toolRoot "src"
$binDir = Join-Path $toolRoot "bin"
$exe = Join-Path $binDir "lobstertrap.exe"

function Resolve-Go {
    $cmd = Get-Command go -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $localGo = Join-Path $env:USERPROFILE ".local\go\go1.22.12\go\bin\go.exe"
    if (Test-Path -LiteralPath $localGo) {
        return $localGo
    }

    throw "Go 1.22+ is required. Install Go or run the previously installed user-local Go at $localGo."
}

$go = Resolve-Go
New-Item -ItemType Directory -Force -Path $toolRoot, $binDir | Out-Null

if (-not (Test-Path -LiteralPath $srcDir)) {
    git clone --depth 1 --branch $Ref $RepoUrl $srcDir
} else {
    git -C $srcDir fetch --depth 1 origin $Ref
    git -C $srcDir checkout FETCH_HEAD
}

Push-Location $srcDir
try {
    if (-not $SkipTests) {
        & $go test ./...
        if ($LASTEXITCODE -ne 0) {
            throw "Lobster Trap Go tests failed."
        }
    }

    & $go build -o $exe .
    if ($LASTEXITCODE -ne 0) {
        throw "Lobster Trap build failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Built Lobster Trap: $exe"
& $exe version
