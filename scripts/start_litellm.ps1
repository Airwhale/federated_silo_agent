param(
    [int]$Port = 4000,
    [string]$HostAddress = "127.0.0.1",
    [string]$Config = "infra\litellm_config.yaml"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = Join-Path $repoRoot $Config

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "LiteLLM config not found: $configPath"
}

if (-not $env:GEMINI_API_KEY) {
    throw "GEMINI_API_KEY is required for LiteLLM Gemini routing."
}

Set-Location $repoRoot
uv run litellm --config $configPath --host $HostAddress --port $Port
