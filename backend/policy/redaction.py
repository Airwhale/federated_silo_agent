"""Demo-grade AML redaction helpers."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend import BACKEND_ROOT


POLICY_ROOT = BACKEND_ROOT / "policy"
DEFAULT_AML_TERMS_PATH = POLICY_ROOT / "dictionaries" / "aml_terms.json"
REDACTION_TOKEN = "[REDACTED_NAME]"
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AmlTermsDictionary(BaseModel):
    """Validated demo dictionary for AML policy evaluation."""

    typology_codes: list[NonEmptyStr] = Field(min_length=1)
    ml_tf_keywords: list[NonEmptyStr] = Field(min_length=1)
    synthetic_customer_name_patterns: list[NonEmptyStr] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class RedactionResult(BaseModel):
    """Redacted text plus a count of replaced customer-name matches."""

    text: str
    redaction_count: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class CustomerNameRedactor:
    """Redacts known demo customer-name surfaces from policy-scanned text."""

    def __init__(self, terms: AmlTermsDictionary) -> None:
        self._pattern = _compile_customer_name_pattern(
            terms.synthetic_customer_name_patterns
        )

    def redact(self, value: str) -> RedactionResult:
        text, count = self._pattern.subn(REDACTION_TOKEN, value)
        return RedactionResult(text=text, redaction_count=count)


def load_aml_terms(path: Path = DEFAULT_AML_TERMS_PATH) -> AmlTermsDictionary:
    """Load the AML policy dictionary once per process."""
    return _load_aml_terms_from_resolved_path(_resolve_terms_path(path))


@lru_cache(maxsize=8)
def _load_aml_terms_from_resolved_path(path: Path) -> AmlTermsDictionary:
    return AmlTermsDictionary.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_customer_name_redactor(
    path: Path = DEFAULT_AML_TERMS_PATH,
) -> CustomerNameRedactor:
    """Load a customer-name redactor from the validated AML terms file."""
    return _load_customer_name_redactor_from_resolved_path(_resolve_terms_path(path))


@lru_cache(maxsize=8)
def _load_customer_name_redactor_from_resolved_path(path: Path) -> CustomerNameRedactor:
    return CustomerNameRedactor(_load_aml_terms_from_resolved_path(path))


def _resolve_terms_path(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (POLICY_ROOT / path).resolve()


def _compile_customer_name_pattern(names: list[str]) -> re.Pattern[str]:
    escaped_names = sorted((re.escape(name) for name in names), key=len, reverse=True)
    known_name_pattern = rf"(?i:{'|'.join(escaped_names)})"
    organization_word_pattern = r"(?:[A-Z][A-Za-z0-9&.,'-]*|[A-Z]{2,})"
    connector_word_pattern = r"(?i:of|and|for)"
    subsequent_word_pattern = rf"(?:{organization_word_pattern}|{connector_word_pattern})"
    organization_suffix_pattern = (
        rf"{organization_word_pattern}(?:\s+{subsequent_word_pattern}){{0,3}}\s+"
        r"(?i:LLC|Inc|Ltd|Co|Group|Holdings|Trading|Logistics|"
        r"Consulting|Ventures|Investments|Capital|Partners)\b"
    )
    return re.compile(
        rf"\b(?:(?:{known_name_pattern})\b|{organization_suffix_pattern})",
    )


def dictionary_as_json(terms: AmlTermsDictionary) -> str:
    """Serialize terms deterministically for diagnostics and tests."""
    return json.dumps(terms.model_dump(mode="json"), sort_keys=True)
