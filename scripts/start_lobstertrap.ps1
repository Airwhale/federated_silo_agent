param(
    [int]$Port = 8080,
    [string]$Backend = "http://127.0.0.1:4000",
    [string]$Policy = "infra\lobstertrap\base_policy.yaml",
    [string]$AuditLog = "logs\lobstertrap.jsonl",
    [string]$LobsterTrapBin = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$policyPath = Join-Path $repoRoot $Policy
$auditPath = Join-Path $repoRoot $AuditLog

if (-not (Test-Path -LiteralPath $policyPath)) {
    throw "Policy file not found: $policyPath"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $auditPath) | Out-Null

if (-not $LobsterTrapBin) {
    if ($env:LOBSTERTRAP_BIN) {
        $LobsterTrapBin = $env:LOBSTERTRAP_BIN
    } else {
        $localBin = Join-Path $repoRoot ".tools\lobstertrap\bin\lobstertrap.exe"
        if (Test-Path -LiteralPath $localBin) {
            $LobsterTrapBin = $localBin
        }
    }
}

if (-not $LobsterTrapBin -or -not (Test-Path -LiteralPath $LobsterTrapBin)) {
    throw "Lobster Trap binary not found. Run scripts\bootstrap_lobstertrap.ps1 first, or set LOBSTERTRAP_BIN."
}

& $LobsterTrapBin serve `
    --policy $policyPath `
    --listen ":$Port" `
    --backend $Backend `
    --audit-log $auditPath
