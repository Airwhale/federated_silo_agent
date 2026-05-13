from __future__ import annotations

from pathlib import Path

from scripts.p0_cases import BENIGN_CASE, BLOCKED_CASES
from scripts.smoke_openrouter import DEFAULT_OPENROUTER_MODEL
from scripts.smoke_proxy import infer_required_key_env


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_p0_blocked_cases_are_broad_and_named() -> None:
    names = [case.name for case in BLOCKED_CASES]

    assert len(BLOCKED_CASES) >= 8
    assert len(names) == len(set(names))
    assert "instruction_override" in names
    assert "encoded_instruction" in names
    assert "phi_extraction" in names
    assert "data_exfiltration" in names


def test_p0_cases_have_expected_verdicts() -> None:
    assert BENIGN_CASE.expected_verdicts == ("ALLOW",)
    for case in BLOCKED_CASES:
        assert case.expected_verdicts == ("DENY",)
        assert case.prompt.strip()


def test_proxy_smoke_infers_provider_key_env() -> None:
    assert infer_required_key_env("gemini-narrator") == "GEMINI_API_KEY"
    assert infer_required_key_env(DEFAULT_OPENROUTER_MODEL) == "OPENROUTER_API_KEY"


def test_openrouter_litellm_config_declares_fallback_route() -> None:
    config = (REPO_ROOT / "infra" / "litellm_openrouter_config.yaml").read_text()

    assert f"model_name: {DEFAULT_OPENROUTER_MODEL}" in config
    assert "openrouter/google/gemini-2.5-flash" in config
    assert "os.environ/OPENROUTER_API_KEY" in config
    assert "GEMINI_API_KEY" not in config
