"""Deterministic typology signals for F2 graph analysis."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shared.enums import BankId, PatternClass
from shared.messages import BankAggregate, CrossBankHashToken


SUB_CTR_BUCKET_INDEX = 2
MID_VALUE_BUCKET_INDEX = 3
HIGH_VALUE_BUCKET_INDEX = 4
REPEATED_EDGE_BUCKET_INDEXES = (2, 3)
DEFAULT_HIGH_CONFIDENCE = 0.88
DEFAULT_NONE_CONFIDENCE = 0.18


class TypologySignals(BaseModel):
    """DP-noised aggregate features used by F2 rule gates."""

    active_banks: list[BankId]
    candidate_entity_hashes: list[CrossBankHashToken]
    total_edge_buckets: int
    repeated_edge_buckets: int
    total_flow_buckets: int
    sub_ctr_flow_buckets: int
    mid_value_flow_buckets: int
    high_value_flow_buckets: int
    structuring_score: float = Field(ge=0.0, le=1.0)
    layering_score: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class TypologyMatch(BaseModel):
    """Optional deterministic classification for a clear aggregate pattern."""

    pattern_class: PatternClass
    confidence: float = Field(ge=0.0, le=1.0)
    suspect_entity_hashes: list[CrossBankHashToken] = Field(default_factory=list)
    narrative: str
    bypass_name: str

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


def extract_signals(aggregates: list[BankAggregate]) -> TypologySignals:
    """Summarize the noised histograms without inspecting raw transactions."""
    active_banks: list[BankId] = []
    candidate_entity_hashes: list[CrossBankHashToken] = []
    total_edge_buckets = 0
    repeated_edge_buckets = 0
    total_flow_buckets = 0
    sub_ctr_flow_buckets = 0
    mid_value_flow_buckets = 0
    high_value_flow_buckets = 0

    for aggregate in aggregates:
        edge_total = sum(aggregate.edge_count_distribution)
        flow_total = sum(aggregate.bucketed_flow_histogram)
        if edge_total > 0 or flow_total > 0:
            active_banks.append(aggregate.bank_id)

        total_edge_buckets += edge_total
        repeated_edge_buckets += sum(
            aggregate.edge_count_distribution[index]
            for index in REPEATED_EDGE_BUCKET_INDEXES
            if index < len(aggregate.edge_count_distribution)
        )
        total_flow_buckets += flow_total
        sub_ctr_flow_buckets += _bucket_value(
            aggregate.bucketed_flow_histogram,
            SUB_CTR_BUCKET_INDEX,
        )
        mid_value_flow_buckets += _bucket_value(
            aggregate.bucketed_flow_histogram,
            MID_VALUE_BUCKET_INDEX,
        )
        high_value_flow_buckets += _bucket_value(
            aggregate.bucketed_flow_histogram,
            HIGH_VALUE_BUCKET_INDEX,
        )
        for entity_hash in aggregate.candidate_entity_hashes:
            if entity_hash not in candidate_entity_hashes:
                candidate_entity_hashes.append(entity_hash)

    active_bank_count = len(active_banks)
    candidate_count = len(candidate_entity_hashes)
    repeated_edge_ratio = _ratio(repeated_edge_buckets, total_edge_buckets)
    sub_ctr_ratio = _ratio(sub_ctr_flow_buckets, total_flow_buckets)
    high_value_ratio = _ratio(high_value_flow_buckets, total_flow_buckets)

    structuring_score = _clamp(
        0.18
        + 0.20 * min(active_bank_count / 3.0, 1.0)
        + 0.18 * min(candidate_count / 5.0, 1.0)
        + 0.22 * sub_ctr_ratio
        + 0.14 * repeated_edge_ratio
        + 0.08 * min(sub_ctr_flow_buckets / 60.0, 1.0)
    )
    layering_score = _clamp(
        0.16
        + 0.18 * min(active_bank_count / 3.0, 1.0)
        + 0.16 * min(candidate_count / 4.0, 1.0)
        + 0.25 * high_value_ratio
        + 0.10 * _ratio(mid_value_flow_buckets + high_value_flow_buckets, total_flow_buckets)
        + 0.15 * min(high_value_flow_buckets / 20.0, 1.0)
    )

    return TypologySignals(
        active_banks=active_banks,
        candidate_entity_hashes=candidate_entity_hashes,
        total_edge_buckets=total_edge_buckets,
        repeated_edge_buckets=repeated_edge_buckets,
        total_flow_buckets=total_flow_buckets,
        sub_ctr_flow_buckets=sub_ctr_flow_buckets,
        mid_value_flow_buckets=mid_value_flow_buckets,
        high_value_flow_buckets=high_value_flow_buckets,
        structuring_score=structuring_score,
        layering_score=layering_score,
    )


def deterministic_match(signals: TypologySignals) -> TypologyMatch | None:
    """Return a deterministic match for clear positives or clear negatives."""
    if _is_structuring_ring(signals):
        return TypologyMatch(
            pattern_class=PatternClass.STRUCTURING_RING,
            confidence=max(DEFAULT_HIGH_CONFIDENCE, signals.structuring_score),
            suspect_entity_hashes=signals.candidate_entity_hashes,
            narrative=(
                f"DP-noised aggregates across {len(signals.active_banks)} banks show "
                f"repeated sub-CTR flow consistent with a structuring ring over "
                f"{len(signals.candidate_entity_hashes)} hash tokens."
            ),
            bypass_name="F2-B1",
        )
    if _is_layering_chain(signals):
        return TypologyMatch(
            pattern_class=PatternClass.LAYERING_CHAIN,
            confidence=max(DEFAULT_HIGH_CONFIDENCE, signals.layering_score),
            suspect_entity_hashes=signals.candidate_entity_hashes,
            narrative=(
                f"DP-noised aggregates across {len(signals.active_banks)} banks show "
                f"high-value staged flows consistent with a layering chain over "
                f"{len(signals.candidate_entity_hashes)} hash tokens."
            ),
            bypass_name="F2-B2",
        )
    if _is_clear_negative(signals):
        return TypologyMatch(
            pattern_class=PatternClass.NONE,
            confidence=DEFAULT_NONE_CONFIDENCE,
            suspect_entity_hashes=[],
            narrative="DP-noised aggregates do not show a clear cross-bank graph pattern.",
            bypass_name="F2-B0",
        )
    return None


def _is_structuring_ring(signals: TypologySignals) -> bool:
    return (
        len(signals.active_banks) >= 2
        and len(signals.candidate_entity_hashes) >= 3
        and signals.sub_ctr_flow_buckets >= 25
        and _ratio(signals.sub_ctr_flow_buckets, signals.total_flow_buckets) >= 0.45
        and signals.sub_ctr_flow_buckets > signals.high_value_flow_buckets
        and signals.repeated_edge_buckets >= 3
    )


def _is_layering_chain(signals: TypologySignals) -> bool:
    return (
        len(signals.active_banks) >= 2
        and len(signals.candidate_entity_hashes) >= 3
        and signals.high_value_flow_buckets >= 8
        and _ratio(signals.high_value_flow_buckets, signals.total_flow_buckets) >= 0.35
        and signals.high_value_flow_buckets > signals.sub_ctr_flow_buckets
    )


def _is_clear_negative(signals: TypologySignals) -> bool:
    return (
        len(signals.active_banks) < 2
        or len(signals.candidate_entity_hashes) < 3
        or signals.total_flow_buckets < 15
        or max(signals.structuring_score, signals.layering_score) < 0.50
    )


def _bucket_value(values: list[int], index: int) -> int:
    if index >= len(values):
        return 0
    return values[index]


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
