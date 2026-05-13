# P0 Proxy Chain

P0 proves the LLM governance path before any product logic depends on it.

```text
smoke_proxy.py
  -> http://127.0.0.1:8080/v1/chat/completions
  -> Lobster Trap
  -> LiteLLM
  -> Gemini API
```

## Prerequisites

- Python environment installed with `uv sync`
- Go 1.22+ for building Lobster Trap
- `GEMINI_API_KEY` in your shell or `.env`

Docker is optional. The verified Windows path is local-first because Docker is
not required for P0.

## Local Run

Build Lobster Trap:

```powershell
.\scripts\bootstrap_lobstertrap.ps1
```

If Windows blocks local script execution, use a process-scoped bypass:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap_lobstertrap.ps1
```

Start LiteLLM in one terminal:

```powershell
$env:GEMINI_API_KEY = "<your key>"
.\scripts\start_litellm.ps1
```

Start Lobster Trap in a second terminal:

```powershell
.\scripts\start_lobstertrap.ps1
```

On Windows systems with script execution disabled, use the same
`powershell -NoProfile -ExecutionPolicy Bypass -File ...` wrapper for these
PowerShell scripts.

Run local policy smoke without Gemini:

```powershell
uv run python scripts/smoke_lobstertrap.py
```

Run the full proxy-chain smoke:

```powershell
uv run python scripts/smoke_proxy.py
```

## Expected Results

The benign prompt should return a Gemini response with Lobster Trap
`_lobstertrap` metadata and an `ALLOW` verdict.

Blocked prompts should return Lobster Trap denial text and a `DENY` verdict.
The blocked smoke suite covers:

- instruction override
- fake system tags
- DAN-style jailbreak
- encoded instruction evasion
- PHI / PII extraction
- data exfiltration
- dangerous commands
- sensitive file paths

## Optional Docker Path

When Docker is available:

```powershell
docker compose -f infra/docker-compose.yml up --build
uv run python scripts/smoke_proxy.py
```

## Fallback

If direct LiteLLM-to-Gemini routing blocks, use OpenRouter's OpenAI-compatible
Gemini route as a short-term fallback. The primary demo story should remain
Gemini via Google AI Studio / Gemini API for Track 4 clarity.
