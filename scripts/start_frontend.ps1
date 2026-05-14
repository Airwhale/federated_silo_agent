param(
    [int]$Port = 5173,
    [string]$HostAddress = "127.0.0.1",
    [string]$ApiBase = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontend = Join-Path $repoRoot "frontend"

if (-not (Test-Path -LiteralPath $frontend)) {
    throw "frontend directory not found: $frontend"
}

# Cheap check for `npm`; fail loud rather than a cryptic exec error.
$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    throw "npm not found on PATH. Install Node.js 20+ from https://nodejs.org and reopen the shell."
}

Set-Location $frontend

# Cold start: install once. Subsequent runs reuse node_modules so dev startup
# is fast. Delete node_modules manually if you need to refresh.
if (-not (Test-Path -LiteralPath "node_modules")) {
    Write-Host "node_modules missing — running 'npm install' (this can take a minute)..." -ForegroundColor Yellow
    npm install --no-audit --no-fund --loglevel=error
    if ($LASTEXITCODE -ne 0) {
        throw "npm install failed (exit $LASTEXITCODE)"
    }
}

# Vite reads VITE_API_BASE at dev/build time. Default points at the local
# `uv run uvicorn backend.ui.server:app --port 8000`.
$env:VITE_API_BASE = $ApiBase

Write-Host "Starting Vite dev server on http://${HostAddress}:${Port} (API base: $ApiBase)..." -ForegroundColor Green
npm run dev -- --host $HostAddress --port $Port
