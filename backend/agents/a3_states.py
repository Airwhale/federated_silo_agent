"""Pydantic state models for the A3 silo responder."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from shared.messages import (
    LocalSiloContributionRequest,
    PrimitiveCallRecord,
    ResponseValue,
    Sec314bQuery,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class A3Model(BaseModel):
    """Strict Pydantic base for A3 state objects."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


A3Request: TypeAlias = Annotated[
    Sec314bQuery | LocalSiloContributionRequest,
    Field(discriminator="message_type"),
]


class A3TurnInput(A3Model):
    """One A3 request turn."""

    request: A3Request


class A3PrimitiveBundle(A3Model):
    """Primitive results made available to optional LLM response composition."""

    route_kind: Literal["peer_314b", "local_contribution"]
    field_values: dict[str, ResponseValue]
    provenance: list[PrimitiveCallRecord]
    refusal_reason: str | None = None

    @model_validator(mode="after")
    def success_or_refusal(self) -> A3PrimitiveBundle:
        if self.refusal_reason is not None and (self.field_values or self.provenance):
            raise ValueError("refusal bundles cannot include values or provenance")
        if self.refusal_reason is None and not self.field_values:
            raise ValueError("successful bundles require field_values")
        return self
