param(
    [int]$Port = 4000,
    [string]$HostAddress = "127.0.0.1",
    [string]$Config = "",
    [switch]$OpenRouter
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $Config) {
    if ($OpenRouter) {
        $Config = "infra\litellm_openrouter_config.yaml"
    } else {
        $Config = "infra\litellm_config.yaml"
    }
}

$configPath = Join-Path $repoRoot $Config

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "LiteLLM config not found: $configPath"
}

# Load `.env` at the repo root if present, so the user only has to set the
# key once (matches the python-dotenv loading in scripts/smoke_proxy.py).
$envPath = Join-Path $repoRoot ".env"
if (Test-Path -LiteralPath $envPath) {
    Get-Content -LiteralPath $envPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $name, $value = $line.Split("=", 2)
            $name = $name.Trim()
            $value = $value.Trim().Trim("'", '"')
            if ($name) {
                Set-Item -Path "env:$name" -Value $value
            }
        }
    }
}

$usesOpenRouter = $OpenRouter -or ((Split-Path -Leaf $configPath) -eq "litellm_openrouter_config.yaml")
if ($usesOpenRouter) {
    if (-not $env:OPENROUTER_API_KEY) {
        throw "OPENROUTER_API_KEY is required for LiteLLM OpenRouter routing. Copy .env.example to .env and add your key."
    }
} elseif (-not $env:GEMINI_API_KEY) {
    throw "GEMINI_API_KEY is required for LiteLLM Gemini routing. Copy .env.example to .env and add your key (https://aistudio.google.com/apikey)."
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Set-Location $repoRoot
uv run litellm --config $configPath --host $HostAddress --port $Port
