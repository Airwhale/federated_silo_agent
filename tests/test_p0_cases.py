from __future__ import annotations

from scripts.p0_cases import BENIGN_CASE, BLOCKED_CASES


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
