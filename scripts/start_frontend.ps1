param(
    [int]$Port = 5173,
    [string]$HostAddress = "127.0.0.1",
    [string]$ApiBase = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$FrontendDir = Join-Path $RepoRoot "frontend"

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Push-Location $FrontendDir
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}

Push-Location $FrontendDir
try {
    $env:VITE_API_BASE = $ApiBase
    Write-Host ("Starting frontend at http://{0}:{1} with VITE_API_BASE={2}" -f $HostAddress, $Port, $ApiBase)
    npm run dev -- --host $HostAddress --port $Port
}
finally {
    Pop-Location
}
