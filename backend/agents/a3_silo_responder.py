"""A3 bank-silo responder agent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from backend import BACKEND_ROOT
from backend.agents.a3_states import A3PrimitiveBundle, A3TurnInput
from backend.agents.base import Agent, AuditEmitter, ConstraintViolation, InvalidAgentInput
from backend.agents.llm_client import LLMClient
from backend.runtime.context import AgentRuntimeContext
from backend.security import (
    PrincipalAllowlist,
    PrincipalNotAllowed,
    ReplayCache,
    ReplayDetected,
    SecurityEnvelopeError,
    SignatureInvalid,
    approved_body_hash,
    sign_message,
)
from backend.silos.budget import RequesterKey
from backend.silos.stats_primitives import (
    BankStatsPrimitives,
)
from shared.enums import AgentRole, AuditEventKind, BankId, QueryShape, RouteKind
from shared.messages import (
    A3_RESPONSE_NONCE_SUFFIX,
    AggregateActivityPayload,
    HashListResponseValue,
    HistogramResponseValue,
    IntResponseValue,
    LocalSiloContributionRequest,
    PrimitiveCallRecord,
    ResponseValue,
    RouteApproval,
    Sec314bQuery,
    Sec314bResponse,
)


PROMPT_PATH = BACKEND_ROOT / "agents" / "prompts" / "a3_system.md"
PATTERN_AGGREGATE_METRICS = {"pattern_aggregate", "pattern_aggregate_for_f2"}
METRIC_ALERT_COUNT = "alert_count"
METRIC_FLOW_HISTOGRAM = "flow_histogram"
REFUSAL_BUDGET_EXHAUSTED = "budget_exhausted"
REFUSAL_ENVELOPE_INVALID = "envelope_invalid"
REFUSAL_INVALID_RHO = "invalid_rho"
REFUSAL_PRINCIPAL_NOT_ALLOWED = "principal_not_allowed"
REFUSAL_UNSUPPORTED_METRIC = "unsupported_metric"
REFUSAL_UNSUPPORTED_METRIC_COMBINATION = "unsupported_metric_combination"
REFUSAL_UNSUPPORTED_QUERY_SHAPE = "unsupported_query_shape"


def load_prompt(path: Path = PROMPT_PATH) -> str:
    """Load the versioned A3 prompt."""
    return path.read_text(encoding="utf-8")


class A3SiloResponderAgent(Agent[A3TurnInput, Sec314bResponse]):
    """Inside-bank responder that gates every local primitive invocation."""

    role = AgentRole.A3
    input_schema = A3TurnInput
    output_schema = Sec314bResponse
    declared_intent = "bank_silo_response"

    def __init__(
        self,
        *,
        bank_id: BankId,
        runtime: AgentRuntimeContext,
        primitives: BankStatsPrimitives | None = None,
        principal_allowlist: PrincipalAllowlist,
        replay_cache: ReplayCache | None = None,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
        compose_with_llm: bool = False,
        response_private_key: str | None = None,
        response_signing_key_id: str | None = None,
    ) -> None:
        if bank_id == BankId.FEDERATION:
            raise ValueError("A3 must belong to a bank, not the federation")
        if (response_private_key is None) != (response_signing_key_id is None):
            raise ValueError(
                "response_private_key and response_signing_key_id must be set together"
            )
        primitives = primitives or BankStatsPrimitives(bank_id=bank_id)
        if primitives.bank_id != bank_id:
            raise ValueError("A3 primitives handle must belong to the same bank")
        self.bank_id = bank_id
        self.agent_id = f"{bank_id.value}.A3"
        self.system_prompt = load_prompt()
        self.primitives = primitives
        self.principal_allowlist = principal_allowlist
        self.replay_cache = replay_cache or ReplayCache()
        self.compose_with_llm = compose_with_llm
        self.response_private_key = response_private_key
        self.response_signing_key_id = response_signing_key_id
        super().__init__(runtime=runtime, llm=llm, audit=audit)
        if self.response_private_key is None:
            self._emit(
                kind=AuditEventKind.CONSTRAINT_VIOLATION,
                phase="configuration",
                status="warning",
                detail="A3 response signing is disabled for this runtime",
                rule_name="response_signature_disabled",
            )

    def run(self, input_data: A3TurnInput | object) -> Sec314bResponse:
        """Run one A3 turn after deterministic envelope and policy checks."""
        validated_input = self._validate_input(input_data)
        request = validated_input.request

        try:
            self._validate_inbound(request)
        except ReplayDetected as exc:
            return self._refusal(request, "replay_detected", str(exc), "replay")
        except SignatureInvalid as exc:
            return self._refusal(
                request,
                "signature_invalid",
                str(exc),
                "signature",
                sign_response=False,
            )
        except PrincipalNotAllowed as exc:
            return self._refusal(
                request,
                REFUSAL_PRINCIPAL_NOT_ALLOWED,
                str(exc),
                "principal",
                sign_response=False,
            )
        except SecurityEnvelopeError as exc:
            return self._refusal(request, REFUSAL_ENVELOPE_INVALID, str(exc), "envelope")
        except InvalidAgentInput as exc:
            return self._refusal(request, "route_violation", str(exc), "routing")

        bundle = self._invoke_primitives(request)
        if bundle.refusal_reason is not None:
            return self._refusal(
                request,
                bundle.refusal_reason,
                bundle.refusal_reason,
                "primitive",
            )

        deterministic = self._build_response(
            request,
            fields=bundle.field_values,
            provenance=bundle.provenance,
        )
        response = (
            self._compose_with_llm(request, bundle, deterministic)
            if self.compose_with_llm
            else deterministic
        )
        status = "blocked" if response.refusal_reason is not None else "ok"
        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="return",
            status=status,
            detail=f"A3 returned {len(response.fields)} field(s)",
            model_name=(
                self.llm.config.default_model
                if self.compose_with_llm
                else "deterministic_compose"
            ),
        )
        return self._sign_response(response, request)

    def _validate_inbound(
        self,
        request: Sec314bQuery | LocalSiloContributionRequest,
    ) -> None:
        verified = self.principal_allowlist.verify_message(
            request,
            replay_cache=self.replay_cache,
        )
        if verified.principal.role != AgentRole.F1:
            raise InvalidAgentInput("A3 only accepts signed requests from F1")
        if verified.principal.bank_id != BankId.FEDERATION:
            raise InvalidAgentInput("F1 request must come from federation")
        if request.recipient_agent_id != self.agent_id:
            raise InvalidAgentInput("request must be addressed to this A3")
        if request.route_approval is None:
            raise InvalidAgentInput("request requires a RouteApproval")

        self.principal_allowlist.verify_route_approval(request.route_approval)
        self._validate_route_approval_binding(request, request.route_approval)

    def _validate_route_approval_binding(
        self,
        request: Sec314bQuery | LocalSiloContributionRequest,
        route_approval: RouteApproval,
    ) -> None:
        if route_approval.responding_bank_id != self.bank_id:
            raise InvalidAgentInput("route approval does not target this bank")
        if route_approval.approved_query_body_hash != approved_body_hash(request):
            raise InvalidAgentInput("approved query body hash mismatch")

        if isinstance(request, Sec314bQuery):
            if route_approval.route_kind != RouteKind.PEER_314B:
                raise InvalidAgentInput("Sec314bQuery requires peer_314b route kind")
            if request.requesting_bank_id == self.bank_id:
                raise InvalidAgentInput("same-bank Sec314bQuery must use local contribution")
            if self.bank_id not in request.target_bank_ids:
                raise InvalidAgentInput("this bank is not a target of the query")
            return

        if route_approval.route_kind != RouteKind.LOCAL_CONTRIBUTION:
            raise InvalidAgentInput(
                "LocalSiloContributionRequest requires local_contribution route kind"
            )
        if request.requesting_bank_id != self.bank_id:
            raise InvalidAgentInput("local contribution must target requester bank")

    def _invoke_primitives(
        self,
        request: Sec314bQuery | LocalSiloContributionRequest,
    ) -> A3PrimitiveBundle:
        route_kind = request.route_approval.route_kind
        requester = RequesterKey(
            requesting_investigator_id=request.requesting_investigator_id,
            requesting_bank_id=request.requesting_bank_id,
            responding_bank_id=self.bank_id,
        )

        if request.query_shape == QueryShape.ENTITY_PRESENCE:
            if (
                request.query_payload.window_start is not None
                or request.query_payload.window_end is not None
            ):
                return _refusal_bundle(route_kind, REFUSAL_UNSUPPORTED_QUERY_SHAPE)
            result = self.primitives.count_entities_by_name_hash(
                name_hashes=list(request.query_payload.name_hashes),
                requester=requester,
                rho=0.0,
            )
            if result.refusal_reason is not None:
                return _refusal_bundle(route_kind, result.refusal_reason)
            return A3PrimitiveBundle(
                route_kind=route_kind.value,
                field_values={"entity_count": IntResponseValue(int=int(result.value))},
                provenance=result.records,
            )

        if request.query_shape == QueryShape.COUNTERPARTY_LINKAGE:
            if request.query_payload.max_hops != 1:
                return _refusal_bundle(route_kind, REFUSAL_UNSUPPORTED_QUERY_SHAPE)
            result = self.primitives.counterparty_edge_existence(
                counterparty_hashes=list(request.query_payload.counterparty_hashes),
                window=(request.query_payload.window_start, request.query_payload.window_end),
                requester=requester,
                rho=0.0,
            )
            if result.refusal_reason is not None:
                return _refusal_bundle(route_kind, result.refusal_reason)
            edge_map = _expect_dict_bool(result.value)
            present = [hash_value for hash_value, exists in edge_map.items() if exists]
            return A3PrimitiveBundle(
                route_kind=route_kind.value,
                field_values={
                    "counterparty_edges": HashListResponseValue(hash_list=present)
                },
                provenance=result.records,
            )

        if request.query_shape == QueryShape.AGGREGATE_ACTIVITY:
            return self._aggregate_activity_bundle(
                request.query_payload,
                requester,
                request.requested_rho_per_primitive,
                route_kind,
            )

        raise ConstraintViolation(f"unsupported query shape: {request.query_shape}")

    def _aggregate_activity_bundle(
        self,
        payload: AggregateActivityPayload,
        requester: RequesterKey,
        rho: float,
        route_kind: RouteKind,
    ) -> A3PrimitiveBundle:
        metrics = set(payload.metrics)
        supported_metrics = PATTERN_AGGREGATE_METRICS | {
            METRIC_ALERT_COUNT,
            METRIC_FLOW_HISTOGRAM,
        }
        unsupported = sorted(metrics - supported_metrics)
        if unsupported:
            return _refusal_bundle(route_kind, REFUSAL_UNSUPPORTED_METRIC)
        if not metrics:
            return _refusal_bundle(route_kind, REFUSAL_UNSUPPORTED_METRIC)
        if rho <= 0.0:
            return _refusal_bundle(route_kind, REFUSAL_INVALID_RHO)
        metric_refusal = _aggregate_metric_refusal(metrics, payload)
        if metric_refusal is not None:
            return _refusal_bundle(route_kind, metric_refusal)

        if metrics & PATTERN_AGGREGATE_METRICS:
            result = self.primitives.pattern_aggregate_for_f2(
                window=(payload.window_start, payload.window_end),
                requester=requester,
                candidate_entity_hashes=payload.name_hashes,
                rho=rho,
            )
            if result.refusal_reason is not None:
                return _refusal_bundle(route_kind, result.refusal_reason)
            aggregate = result.value
            return A3PrimitiveBundle(
                route_kind=route_kind.value,
                field_values={
                    "edge_count_distribution": HistogramResponseValue(
                        histogram=aggregate.edge_count_distribution
                    ),
                    "bucketed_flow_histogram": HistogramResponseValue(
                        histogram=aggregate.bucketed_flow_histogram
                    ),
                    "candidate_entity_hashes": HashListResponseValue(
                        hash_list=aggregate.candidate_entity_hashes
                    ),
                },
                provenance=result.records,
            )

        field_values: dict[str, ResponseValue] = {}
        provenance: list[PrimitiveCallRecord] = []

        if METRIC_FLOW_HISTOGRAM in metrics:
            result = self.primitives.flow_histogram(
                name_hashes=list(payload.name_hashes),
                window=(payload.window_start, payload.window_end),
                requester=requester,
                rho=rho,
            )
            if result.refusal_reason is not None:
                return _refusal_bundle(route_kind, result.refusal_reason)
            field_values["flow_histogram"] = HistogramResponseValue(
                histogram=list(result.value)
            )
            provenance.extend(result.records)

        if METRIC_ALERT_COUNT in metrics:
            result = self.primitives.alert_count_for_entity(
                name_hash=payload.name_hashes[0],
                window=(payload.window_start, payload.window_end),
                requester=requester,
                rho=rho,
            )
            if result.refusal_reason is not None:
                return _refusal_bundle(route_kind, result.refusal_reason)
            field_values[METRIC_ALERT_COUNT] = IntResponseValue(int=int(result.value))
            provenance.append(
                result.record.model_copy(update={"field_name": METRIC_ALERT_COUNT})
            )

        if not field_values:
            return _refusal_bundle(route_kind, REFUSAL_UNSUPPORTED_METRIC)

        return A3PrimitiveBundle(
            route_kind=route_kind.value,
            field_values=field_values,
            provenance=provenance,
        )

    def _compose_with_llm(
        self,
        request: Sec314bQuery | LocalSiloContributionRequest,
        bundle: A3PrimitiveBundle,
        deterministic: Sec314bResponse,
    ) -> Sec314bResponse:
        candidate = self._call_structured(
            system_prompt=self.system_prompt,
            input_model=bundle,
            output_schema=A3PrimitiveBundle,
            phase="compose_response",
        )
        violation = _bundle_mismatch(candidate, bundle)
        if violation is None:
            return deterministic

        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase="compose_response",
            status="retry",
            detail=violation,
            rule_name="a3_bundle_matches_primitives",
        )
        retried = self._call_structured(
            system_prompt=(
                self.system_prompt
                + "\n\nYour previous response did not exactly match primitive "
                "values and provenance. Return only the supplied bundle."
            ),
            input_model=bundle,
            output_schema=A3PrimitiveBundle,
            phase="compose_response",
        )
        retry_violation = _bundle_mismatch(retried, bundle)
        if retry_violation is None:
            return deterministic
        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase="compose_response",
            status="blocked",
            detail=retry_violation,
            rule_name="a3_bundle_matches_primitives",
            retry_count=1,
        )
        return self._build_response(
            request,
            fields={},
            provenance=[],
            refusal_reason="provenance_violation",
        )

    def _build_response(
        self,
        request: Sec314bQuery | LocalSiloContributionRequest,
        *,
        fields: dict[str, ResponseValue],
        provenance: list[PrimitiveCallRecord],
        refusal_reason: str | None = None,
    ) -> Sec314bResponse:
        created_at, expires_at = _response_times(request)
        return Sec314bResponse(
            sender_agent_id=self.agent_id,
            sender_role=AgentRole.A3,
            sender_bank_id=self.bank_id,
            recipient_agent_id="federation.F1",
            created_at=created_at,
            expires_at=expires_at,
            nonce=(
                f"{request.nonce}{A3_RESPONSE_NONCE_SUFFIX}"
                if request.nonce
                else None
            ),
            in_reply_to=_query_id(request),
            responding_bank_id=self.bank_id,
            fields=fields,
            provenance=provenance,
            rho_debited_total=sum(record.rho_debited for record in provenance),
            refusal_reason=refusal_reason,
        )

    def _refusal(
        self,
        request: Sec314bQuery | LocalSiloContributionRequest,
        reason: str,
        detail: str,
        phase: str,
        *,
        sign_response: bool = True,
    ) -> Sec314bResponse:
        self._emit(
            kind=_refusal_audit_kind(reason),
            phase=phase,
            status="blocked",
            detail=detail,
            rule_name=reason,
        )
        response = self._build_response(
            request,
            fields={},
            provenance=[],
            refusal_reason=reason,
        )
        if sign_response:
            response = self._sign_response(response, request)
        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="return",
            status="blocked",
            detail=f"A3 returned refusal: {reason}",
            model_name="deterministic_refusal",
        )
        return response

    def _sign_response(
        self,
        response: Sec314bResponse,
        _request: Sec314bQuery | LocalSiloContributionRequest,
    ) -> Sec314bResponse:
        if self.response_private_key is None or self.response_signing_key_id is None:
            return response
        return sign_message(
            response,
            private_key=self.response_private_key,
            signing_key_id=self.response_signing_key_id,
        )


def _refusal_bundle(route_kind: RouteKind, reason: str) -> A3PrimitiveBundle:
    return A3PrimitiveBundle(
        route_kind=route_kind.value,
        field_values={},
        provenance=[],
        refusal_reason=reason,
    )


def _refusal_audit_kind(reason: str) -> AuditEventKind:
    if reason == REFUSAL_BUDGET_EXHAUSTED:
        return AuditEventKind.BUDGET_EXHAUSTED
    return AuditEventKind.CONSTRAINT_VIOLATION


def _aggregate_metric_refusal(
    metrics: set[str],
    payload: AggregateActivityPayload,
) -> str | None:
    if metrics & PATTERN_AGGREGATE_METRICS:
        if metrics - PATTERN_AGGREGATE_METRICS or len(metrics) != 1:
            return REFUSAL_UNSUPPORTED_METRIC_COMBINATION
        return None
    if METRIC_FLOW_HISTOGRAM in metrics and len(metrics) != 1:
        return REFUSAL_UNSUPPORTED_METRIC_COMBINATION
    if METRIC_ALERT_COUNT in metrics:
        if len(metrics) != 1 or len(payload.name_hashes) > 1:
            return REFUSAL_UNSUPPORTED_METRIC_COMBINATION
    return None


def _query_id(request: Sec314bQuery | LocalSiloContributionRequest) -> UUID:
    if isinstance(request, Sec314bQuery):
        return request.query_id
    return request.source_query_id


def _expect_dict_bool(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise TypeError("counterparty primitive must return a dict")
    return {str(key): bool(item) for key, item in value.items()}


def _bundle_mismatch(
    candidate: A3PrimitiveBundle,
    expected: A3PrimitiveBundle,
) -> str | None:
    if candidate.route_kind != expected.route_kind:
        return "bundle route_kind must match the approved route"
    if candidate.field_values != expected.field_values:
        return "bundle field_values must exactly match primitive values"
    if candidate.provenance != expected.provenance:
        return "bundle provenance must exactly match primitive records"
    if candidate.refusal_reason != expected.refusal_reason:
        return "bundle refusal_reason must match primitive outcome"
    return None


def _response_times(
    request: Sec314bQuery | LocalSiloContributionRequest,
) -> tuple[datetime, datetime]:
    now = utc_now()
    if request.expires_at is not None and request.expires_at > now:
        return now, max(request.expires_at, now + timedelta(seconds=10))
    return now, now + timedelta(minutes=5)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)
