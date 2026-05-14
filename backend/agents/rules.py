"""Deterministic rule objects used by agent runtimes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel


InT = TypeVar("InT", bound=BaseModel)
OutT = TypeVar("OutT", bound=BaseModel)


def _require_non_empty(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class BypassRule(Generic[InT, OutT]):
    """Rule that returns a deterministic output without calling the LLM."""

    name: str
    trigger: Callable[[InT], bool]
    force_output: Callable[[InT], OutT]
    reason: str

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")
        _require_non_empty(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class ConstraintRule(Generic[InT, OutT]):
    """Rule that validates LLM output and can request one repair attempt."""

    name: str
    check: Callable[[InT, OutT], bool]
    violation_msg: Callable[[InT, OutT], str]

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "name")
