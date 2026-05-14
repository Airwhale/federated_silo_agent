"""F1 federation coordinator agent."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel

from backend.agents.base import Agent, AuditEmitter, InvalidAgentInput
from backend.agents.f1_states import (
    F1AggregationInput,
    F1InboundQueryInput,
    F1NegotiationNote,
    F1RoutePlan,
    F1RoutedRequest,
    F1TurnInput,
    F1TurnResult,
)
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
    sign_model_signature,
)
from shared.enums import AgentRole, AuditEventKind, BankId, QueryShape, RouteKind, TypologyCode
from shared.messages import (
    A3_RESPONSE_NONCE_SUFFIX,
    AggregateActivityPayload,
    CounterpartyLinkagePayload,
    EntityPresencePayload,
    LocalSiloContributionRequest,
    PrimitiveCallRecord,
    PurposeDeclaration,
    ResponseValue,
    ResponseRefusalNote,
    RouteApproval,
    SanctionsCheckRequest,
    Sec314bQuery,
    Sec314bResponse,
    utc_now,
)


FEDERATION_AGENT_ID = "federation.F1"
F3_AGENT_ID = "federation.F3"
MIN_RETRY_RHO = 0.01
DEFAULT_RETRY_RHO = 0.02
MAX_NEGOTIATION_RETRIES = 2
TERMINAL_SECURITY_REFUSALS = {
    "signature_invalid",
    "principal_not_allowed",
    "envelope_invalid",
    "replay_detected",
    "route_violation",
    "provenance_violation",
}
TERMINAL_CAPABILITY_REFUSALS = {
    "unsupported_query_shape",
    "unsupported_metric",
}
NEGOTIABLE_REFUSALS = {
    "invalid_rho",
    "budget_exhausted",
    "unsupported_metric_combination",
}
ModelT = TypeVar("ModelT", bound=BaseModel)


class F1CoordinatorAgent(Agent[F1TurnInput, F1TurnResult]):
    """Federation coordinator that signs routes and aggregates verified A3 output."""

    role = AgentRole.F1
    bank_id = BankId.FEDERATION
    input_schema = F1TurnInput
    output_schema = F1TurnResult
    declared_intent = "federation_route_and_aggregate"

    def __init__(
        self,
        *,
        runtime: AgentRuntimeContext,
        principal_allowlist: PrincipalAllowlist,
        private_key: str,
        signing_key_id: str,
        replay_cache: ReplayCache | None = None,
        llm: LLMClient | None = None,
        audit: AuditEmitter | None = None,
    ) -> None:
        """Construct the F1 coordinator.

        Lifecycle contract for the orchestrator (P15):

        - This agent MUST be instantiated once per federation node and reused
          across all turns. The `replay_cache` and `principal_allowlist`
          fields are stateful and must be shared between the routing turn
          (which burns the A2 query's nonce) and any later aggregation turn
          (which burns each A3 response's nonce). A per-turn agent would
          construct a fresh `ReplayCache()` and lose replay protection.
        - `principal_allowlist` is the runtime trust registry; reloading it
          mid-session would invalidate in-flight signed envelopes.
        - `private_key` / `signing_key_id` must match an allowlisted F1
          principal entry; both are signed onto every routed request and
          aggregate response.
        """
        self.agent_id = FEDERATION_AGENT_ID
        self.system_prompt = ""
        self.principal_allowlist = principal_allowlist
        self.private_key = private_key
        self.signing_key_id = signing_key_id
        self.replay_cache = replay_cache or ReplayCache()
        super().__init__(runtime=runtime, llm=llm, audit=audit)

    def run(self, input_data: F1TurnInput | object) -> F1TurnResult:
        """Run one F1 state-machine turn."""
        validated_input = self._validate_input(input_data)
        payload = validated_input.payload
        if isinstance(payload, F1InboundQueryInput):
            return self._route_inbound_query(payload.query)
        if isinstance(payload, F1AggregationInput):
            return self._aggregate_responses(payload)
        raise InvalidAgentInput(f"unsupported F1 payload: {type(payload)!r}")

    def _route_inbound_query(self, query: Sec314bQuery) -> F1TurnResult:
        try:
            self._validate_inbound_a2_query(query)
        except ReplayDetected as exc:
            return self._query_refusal(query, "replay_detected", str(exc), sign_response=False)
        except SignatureInvalid as exc:
            return self._query_refusal(query, "signature_invalid", str(exc), sign_response=False)
        except PrincipalNotAllowed as exc:
            return self._query_refusal(
                query,
                "principal_not_allowed",
                str(exc),
                sign_response=False,
            )
        except SecurityEnvelopeError as exc:
            return self._query_refusal(query, "envelope_invalid", str(exc))
        except InvalidAgentInput as exc:
            return self._query_refusal(query, "route_violation", str(exc))

        purpose_refusal = self._purpose_refusal(query.purpose_declaration)
        if purpose_refusal is not None:
            return self._query_refusal(query, purpose_refusal, purpose_refusal)

        plan = self._build_route_plan(query)
        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="route",
            status="ok",
            detail=(
                f"F1 routed {len(plan.peer_requests)} peer request(s)"
                + (" plus local contribution" if plan.local_request else "")
            ),
            model_name="deterministic_route",
        )
        return F1TurnResult(action="route_plan", route_plan=plan)

    def _aggregate_responses(self, payload: F1AggregationInput) -> F1TurnResult:
        try:
            self._validate_aggregation_context(payload)
        except SignatureInvalid as exc:
            return self._query_refusal(
                payload.original_query,
                "signature_invalid",
                str(exc),
                sign_response=False,
            )
        except PrincipalNotAllowed as exc:
            return self._query_refusal(
                payload.original_query,
                "principal_not_allowed",
                str(exc),
                sign_response=False,
            )
        except SecurityEnvelopeError as exc:
            return self._query_refusal(
                payload.original_query,
                "envelope_invalid",
                str(exc),
            )
        except InvalidAgentInput as exc:
            return self._query_refusal(
                payload.original_query,
                "route_violation",
                str(exc),
            )

        routed_by_bank = _routed_requests_by_bank(payload.routed_requests)
        verified_responses: list[Sec314bResponse] = []
        notes: list[F1NegotiationNote] = []
        retry_requests: list[F1RoutedRequest] = []
        processed_banks: set[BankId] = set()

        for response in payload.responses:
            routed_request = routed_by_bank.get(response.responding_bank_id)
            try:
                self._validate_a3_response(
                    response,
                    original_query=payload.original_query,
                    routed_request=routed_request,
                )
            except ReplayDetected as exc:
                notes.append(
                    _terminal_note(response.responding_bank_id, "replay_detected", str(exc))
                )
                continue
            except SignatureInvalid as exc:
                notes.append(
                    _terminal_note(response.responding_bank_id, "signature_invalid", str(exc))
                )
                continue
            except PrincipalNotAllowed as exc:
                notes.append(
                    _terminal_note(
                        response.responding_bank_id,
                        "principal_not_allowed",
                        str(exc),
                    )
                )
                continue
            except SecurityEnvelopeError as exc:
                notes.append(
                    _terminal_note(response.responding_bank_id, "envelope_invalid", str(exc))
                )
                continue
            except InvalidAgentInput as exc:
                notes.append(
                    _terminal_note(response.responding_bank_id, "route_violation", str(exc))
                )
                continue

            if response.responding_bank_id in processed_banks:
                notes.append(
                    _terminal_note(
                        response.responding_bank_id,
                        "route_violation",
                        "duplicate response from one routed bank",
                    )
                )
                continue
            processed_banks.add(response.responding_bank_id)

            if response.refusal_reason is None:
                verified_responses.append(response)
                continue

            # `_validate_a3_response` already raises when routed_request is None,
            # so this branch is structurally unreachable with None. Re-check
            # explicitly rather than via `assert` so the guard survives
            # `python -O` (which strips assertions).
            if routed_request is None:
                raise InvalidAgentInput(
                    "internal invariant violated: refusal response reached "
                    "_handle_silo_refusal without a routed_request"
                )
            note, retry_request = self._handle_silo_refusal(
                response,
                routed_request=routed_request,
            )
            notes.append(note)
            if retry_request is not None:
                retry_requests.append(retry_request)

        if retry_requests:
            plan = _retry_route_plan(retry_requests, notes)
            return F1TurnResult(action="retry_plan", route_plan=plan)

        response = self._build_aggregate_response(
            payload.original_query,
            verified_responses,
            notes,
        )
        action = "aggregate" if response.refusal_reason is None else "refusal"
        return F1TurnResult(action=action, response=response)

    def _validate_aggregation_context(self, payload: F1AggregationInput) -> None:
        # Aggregation revalidates signatures and bindings on already-routed
        # artifacts. Freshness and replay are ingress checks; reapplying them
        # here would make slow but valid in-flight aggregations fail.
        self._validate_a2_query_identity(payload.original_query, use_replay_cache=False)
        routed_banks: set[BankId] = set()
        for request in payload.routed_requests:
            self._validate_routed_request_for_aggregation(
                request,
                original_query=payload.original_query,
            )
            routed_bank_id = _routed_bank_id(request)
            if routed_bank_id in routed_banks:
                raise InvalidAgentInput("aggregation input contains duplicate routed banks")
            routed_banks.add(routed_bank_id)

    def _validate_inbound_a2_query(self, query: Sec314bQuery) -> None:
        self._validate_a2_query_identity(query, use_replay_cache=True)

    def _validate_a2_query_identity(
        self,
        query: Sec314bQuery,
        *,
        use_replay_cache: bool,
    ) -> None:
        verified = self.principal_allowlist.verify_message(
            query,
            replay_cache=self.replay_cache if use_replay_cache else None,
            check_freshness=use_replay_cache,
        )
        if verified.principal.role != AgentRole.A2:
            raise InvalidAgentInput("F1 only accepts signed Sec314bQuery from A2")
        if verified.principal.bank_id != query.requesting_bank_id:
            raise InvalidAgentInput("A2 key bank must match requesting_bank_id")
        if query.sender_agent_id != verified.principal.agent_id:
            raise InvalidAgentInput("query sender_agent_id must match verified A2")
        if query.sender_bank_id != query.requesting_bank_id:
            raise InvalidAgentInput("query sender_bank_id must match requesting_bank_id")
        if query.recipient_agent_id != self.agent_id:
            raise InvalidAgentInput("query must be addressed to federation.F1")

    def _validate_routed_request_for_aggregation(
        self,
        request: F1RoutedRequest,
        *,
        original_query: Sec314bQuery,
    ) -> None:
        verified = self.principal_allowlist.verify_message(
            request,
            check_freshness=False,
        )
        if verified.principal.role != AgentRole.F1:
            raise InvalidAgentInput("routed request was not signed by F1")
        if verified.principal.bank_id != BankId.FEDERATION:
            raise InvalidAgentInput("routed request signer must be federation scoped")
        if verified.principal.agent_id != self.agent_id:
            raise InvalidAgentInput("routed request signer must be federation.F1")
        if request.route_approval is None:
            raise InvalidAgentInput("routed request is missing route approval")
        self.principal_allowlist.verify_route_approval(
            request.route_approval,
            check_expiry=False,
        )
        if request.route_approval.approved_query_body_hash != approved_body_hash(request):
            raise InvalidAgentInput("routed request body no longer matches approval")
        if _request_query_id(request) != original_query.query_id:
            raise InvalidAgentInput("routed request query_id does not match original query")
        if request.requesting_investigator_id != original_query.requesting_investigator_id:
            raise InvalidAgentInput(
                "routed request investigator does not match original query"
            )
        if request.requesting_bank_id != original_query.requesting_bank_id:
            raise InvalidAgentInput(
                "routed request requesting bank does not match original query"
            )
        if request.query_shape != original_query.query_shape:
            raise InvalidAgentInput("routed request query shape does not match original query")
        if request.query_payload.query_shape != original_query.query_payload.query_shape:
            raise InvalidAgentInput("routed request payload shape does not match original query")
        if request.recipient_agent_id != _a3_agent_id(request.route_approval.responding_bank_id):
            raise InvalidAgentInput("routed request recipient does not match route approval")
        if isinstance(request, Sec314bQuery):
            if request.route_approval.route_kind != RouteKind.PEER_314B:
                raise InvalidAgentInput("peer routed request must use peer_314b")
            if request.route_approval.responding_bank_id not in original_query.target_bank_ids:
                raise InvalidAgentInput("peer routed request targets an unapproved bank")
            return
        if request.route_approval.route_kind != RouteKind.LOCAL_CONTRIBUTION:
            raise InvalidAgentInput(
                "local routed request must use local_contribution route kind"
            )
        if request.responding_bank_id != original_query.requesting_bank_id:
            raise InvalidAgentInput(
                "local routed request must target the original requesting bank"
            )

    def _validate_a3_response(
        self,
        response: Sec314bResponse,
        *,
        original_query: Sec314bQuery,
        routed_request: F1RoutedRequest | None,
    ) -> None:
        if routed_request is None:
            raise InvalidAgentInput("response came from a bank F1 did not route to")
        verified = self.principal_allowlist.verify_message(
            response,
            replay_cache=self.replay_cache,
        )
        if verified.principal.role != AgentRole.A3:
            raise InvalidAgentInput("F1 only aggregates signed responses from A3")
        if verified.principal.bank_id != response.responding_bank_id:
            raise InvalidAgentInput("A3 key bank must match responding_bank_id")
        if response.sender_agent_id != _a3_agent_id(response.responding_bank_id):
            raise InvalidAgentInput("A3 sender_agent_id does not match responding bank")
        if response.recipient_agent_id != self.agent_id:
            raise InvalidAgentInput("A3 response must be addressed to federation.F1")
        if response.in_reply_to != original_query.query_id:
            raise InvalidAgentInput("A3 response does not match original query_id")
        expected_nonce = (
            f"{routed_request.nonce}{A3_RESPONSE_NONCE_SUFFIX}"
            if routed_request.nonce
            else None
        )
        if response.nonce != expected_nonce:
            raise InvalidAgentInput("A3 response nonce does not match routed request")
        route_approval = routed_request.route_approval
        if route_approval is None:
            raise InvalidAgentInput("routed request is missing route approval")
        if _as_utc(response.created_at) > _as_utc(route_approval.expires_at):
            raise InvalidAgentInput("A3 response was created after route approval expiry")

    def _build_route_plan(self, query: Sec314bQuery) -> F1RoutePlan:
        peer_requests = [
            self._build_peer_request(query, responding_bank_id=bank_id, retry_suffix=None)
            for bank_id in query.target_bank_ids
        ]
        local_request = (
            self._build_local_contribution_request(query, retry_suffix=None)
            if _needs_local_contribution(query)
            else None
        )
        sanctions_request = (
            self._build_sanctions_request(query)
            if _needs_sanctions_request(query)
            else None
        )
        return F1RoutePlan(
            peer_requests=peer_requests,
            local_request=local_request,
            sanctions_request=sanctions_request,
        )

    def _handle_silo_refusal(
        self,
        response: Sec314bResponse,
        *,
        routed_request: F1RoutedRequest,
    ) -> tuple[F1NegotiationNote, F1RoutedRequest | None]:
        # `routed_request` is guaranteed non-None by the caller: both
        # `_validate_a3_response` and the explicit if-raise at the call site
        # reject responses with no matching routed_request. Narrowing the
        # parameter type here satisfies static analysis on the
        # `_retry_attempts(routed_request)` call below without duplicating
        # the runtime guard.
        reason = response.refusal_reason or "unknown_refusal"
        if reason in TERMINAL_SECURITY_REFUSALS:
            return (
                F1NegotiationNote(
                    responding_bank_id=response.responding_bank_id,
                    refusal_reason=reason,
                    decision="terminal_refusal",
                    detail="security or route refusal is terminal",
                ),
                None,
            )
        if reason in TERMINAL_CAPABILITY_REFUSALS:
            return (
                F1NegotiationNote(
                    responding_bank_id=response.responding_bank_id,
                    refusal_reason=reason,
                    decision="partial_result",
                    detail="silo capability refusal is preserved as a partial result",
                ),
                None,
            )
        if reason in NEGOTIABLE_REFUSALS:
            attempt = _retry_attempts(routed_request)
            if attempt >= MAX_NEGOTIATION_RETRIES:
                return (
                    F1NegotiationNote(
                        responding_bank_id=response.responding_bank_id,
                        refusal_reason=reason,
                        decision="terminal_refusal",
                        detail=(
                            f"retry limit reached after {attempt} attempt(s); "
                            "returning silo refusal to A2"
                        ),
                    ),
                    None,
                )
            retry = self._retry_for_refusal(
                reason,
                routed_request,
                retry_count=attempt + 1,
            )
            if retry is not None:
                return (
                    F1NegotiationNote(
                        responding_bank_id=response.responding_bank_id,
                        refusal_reason=reason,
                        decision=_retry_decision(reason),
                        detail=_retry_detail(reason, routed_request, retry, attempt + 1),
                    ),
                    retry,
                )
        return (
            F1NegotiationNote(
                responding_bank_id=response.responding_bank_id,
                refusal_reason=reason,
                decision="terminal_refusal",
                detail="refusal is not safely negotiable by F1",
            ),
            None,
        )

    def _retry_for_refusal(
        self,
        reason: str,
        routed_request: F1RoutedRequest,
        *,
        retry_count: int,
    ) -> F1RoutedRequest | None:
        if not isinstance(routed_request.query_payload, AggregateActivityPayload):
            return None
        retry_query = _retry_query_for_refusal(reason, routed_request)
        if retry_query is None:
            return None

        suffix = f"retry-{reason}"
        if isinstance(routed_request, Sec314bQuery):
            return self._build_peer_request(
                retry_query,
                responding_bank_id=routed_request.route_approval.responding_bank_id,
                retry_suffix=suffix,
                retry_count=retry_count,
            )
        if routed_request.route_approval.route_kind == RouteKind.LOCAL_CONTRIBUTION:
            return self._build_local_contribution_request(
                retry_query,
                retry_suffix=suffix,
                retry_count=retry_count,
                override_payload=retry_query.query_payload,
            )
        return None

    def _build_peer_request(
        self,
        query: Sec314bQuery,
        *,
        responding_bank_id: BankId,
        retry_suffix: str | None,
        retry_count: int = 0,
        override_payload: AggregateActivityPayload | None = None,
    ) -> Sec314bQuery:
        created_at, expires_at = _message_times(query)
        unsigned = Sec314bQuery(
            sender_agent_id=self.agent_id,
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id=_a3_agent_id(responding_bank_id),
            created_at=created_at,
            expires_at=expires_at,
            nonce=_nonce(query, responding_bank_id, RouteKind.PEER_314B, retry_suffix),
            query_id=query.query_id,
            requesting_investigator_id=query.requesting_investigator_id,
            requesting_bank_id=query.requesting_bank_id,
            target_bank_ids=[responding_bank_id],
            query_shape=query.query_shape,
            query_payload=override_payload or query.query_payload,
            purpose_declaration=query.purpose_declaration,
            requested_rho_per_primitive=query.requested_rho_per_primitive,
        )
        return self._attach_route_and_sign(
            unsigned,
            route_kind=RouteKind.PEER_314B,
            responding_bank_id=responding_bank_id,
            retry_count=retry_count,
        )

    def _build_local_contribution_request(
        self,
        query: Sec314bQuery,
        *,
        retry_suffix: str | None,
        retry_count: int = 0,
        override_payload: AggregateActivityPayload | None = None,
    ) -> LocalSiloContributionRequest:
        responding_bank_id = query.requesting_bank_id
        created_at, expires_at = _message_times(query)
        placeholder_route = self._route_approval(
            query_id=query.query_id,
            route_kind=RouteKind.LOCAL_CONTRIBUTION,
            requesting_bank_id=query.requesting_bank_id,
            responding_bank_id=responding_bank_id,
            approved_query_body_hash="0" * 64,
            expires_at=expires_at,
            retry_count=retry_count,
        )
        unsigned = LocalSiloContributionRequest(
            sender_agent_id=self.agent_id,
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id=_a3_agent_id(responding_bank_id),
            created_at=created_at,
            expires_at=expires_at,
            nonce=_nonce(query, responding_bank_id, RouteKind.LOCAL_CONTRIBUTION, retry_suffix),
            source_query_id=query.query_id,
            requesting_investigator_id=query.requesting_investigator_id,
            requesting_bank_id=query.requesting_bank_id,
            responding_bank_id=responding_bank_id,
            query_shape=query.query_shape,
            query_payload=override_payload or query.query_payload,
            purpose_declaration=query.purpose_declaration,
            requested_rho_per_primitive=query.requested_rho_per_primitive,
            route_approval=placeholder_route,
        )
        return self._attach_route_and_sign(
            unsigned,
            route_kind=RouteKind.LOCAL_CONTRIBUTION,
            responding_bank_id=responding_bank_id,
            retry_count=retry_count,
        )

    def _attach_route_and_sign(
        self,
        request: Sec314bQuery | LocalSiloContributionRequest,
        *,
        route_kind: RouteKind,
        responding_bank_id: BankId,
        retry_count: int = 0,
    ) -> Sec314bQuery | LocalSiloContributionRequest:
        route = self._route_approval(
            query_id=_request_query_id(request),
            route_kind=route_kind,
            requesting_bank_id=request.requesting_bank_id,
            responding_bank_id=responding_bank_id,
            approved_query_body_hash=approved_body_hash(request),
            expires_at=request.expires_at or _safe_expires_at(request),
            retry_count=retry_count,
        )
        signed_route = sign_model_signature(
            route,
            private_key=self.private_key,
            signing_key_id=self.signing_key_id,
        )
        # sign_message validates internally via _validated_copy; we just need
        # the route_approval attached to the request before signing.
        routed = request.model_copy(update={"route_approval": signed_route})
        return sign_message(
            routed,
            private_key=self.private_key,
            signing_key_id=self.signing_key_id,
        )

    def _route_approval(
        self,
        *,
        query_id: UUID,
        route_kind: RouteKind,
        requesting_bank_id: BankId,
        responding_bank_id: BankId,
        approved_query_body_hash: str,
        expires_at: datetime,
        retry_count: int = 0,
    ) -> RouteApproval:
        return RouteApproval(
            query_id=query_id,
            route_kind=route_kind,
            approved_query_body_hash=approved_query_body_hash,
            requesting_bank_id=requesting_bank_id,
            responding_bank_id=responding_bank_id,
            approved_by_agent_id=self.agent_id,
            retry_count=retry_count,
            expires_at=expires_at,
        )

    def _build_sanctions_request(self, query: Sec314bQuery) -> SanctionsCheckRequest | None:
        entity_hashes = _query_entity_hashes(query)
        if not entity_hashes:
            return None
        created_at, expires_at = _message_times(query)
        request = SanctionsCheckRequest(
            sender_agent_id=self.agent_id,
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id=F3_AGENT_ID,
            created_at=created_at,
            expires_at=expires_at,
            nonce=f"{query.nonce}:f1:f3" if query.nonce else None,
            entity_hashes=entity_hashes,
            requesting_context=(
                "F1-B3 sanctions-related purpose; screen only supplied hash tokens."
            ),
        )
        return sign_message(
            request,
            private_key=self.private_key,
            signing_key_id=self.signing_key_id,
        )

    def _build_aggregate_response(
        self,
        query: Sec314bQuery,
        verified_responses: list[Sec314bResponse],
        notes: list[F1NegotiationNote],
    ) -> Sec314bResponse:
        fields: dict[str, ResponseValue] = {}
        provenance: list[PrimitiveCallRecord] = []
        for response in verified_responses:
            for field_name, value in response.fields.items():
                aggregate_name = f"{response.responding_bank_id.value}.{field_name}"
                fields[aggregate_name] = value
            for record in response.provenance:
                aggregate_name = f"{response.responding_bank_id.value}.{record.field_name}"
                provenance.append(record.model_copy(update={"field_name": aggregate_name}))

        refusal_reason = None
        if not fields and notes:
            refusal_reason = _aggregate_refusal_reason(notes)
        elif not fields:
            refusal_reason = "no_silo_responses"
        created_at, expires_at = _message_times(query)
        response = Sec314bResponse(
            sender_agent_id=self.agent_id,
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id=query.sender_agent_id,
            created_at=created_at,
            expires_at=expires_at,
            nonce=f"{query.nonce}:f1-response" if query.nonce else None,
            in_reply_to=query.query_id,
            responding_bank_id=BankId.FEDERATION,
            fields=fields,
            provenance=provenance,
            rho_debited_total=sum(record.rho_debited for record in provenance),
            refusal_reason=refusal_reason,
            partial_refusals=_response_refusal_notes(notes),
        )
        signed = sign_message(
            response,
            private_key=self.private_key,
            signing_key_id=self.signing_key_id,
        )
        self._emit(
            kind=AuditEventKind.MESSAGE_SENT,
            phase="aggregate",
            status="blocked" if refusal_reason else "ok",
            detail=f"F1 aggregated {len(verified_responses)} successful A3 response(s)",
            model_name="deterministic_aggregate",
        )
        return signed

    def _query_refusal(
        self,
        query: Sec314bQuery,
        reason: str,
        detail: str,
        *,
        sign_response: bool = True,
    ) -> F1TurnResult:
        self._emit(
            kind=AuditEventKind.CONSTRAINT_VIOLATION,
            phase="inbound",
            status="blocked",
            detail=detail,
            rule_name=reason,
        )
        response = Sec314bResponse(
            sender_agent_id=self.agent_id,
            sender_role=AgentRole.F1,
            sender_bank_id=BankId.FEDERATION,
            recipient_agent_id=query.sender_agent_id,
            created_at=utc_now(),
            expires_at=_safe_response_expiry(query),
            nonce=f"{query.nonce}:f1-refusal" if query.nonce else None,
            in_reply_to=query.query_id,
            responding_bank_id=BankId.FEDERATION,
            fields={},
            provenance=[],
            rho_debited_total=0.0,
            refusal_reason=reason,
        )
        if sign_response:
            response = sign_message(
                response,
                private_key=self.private_key,
                signing_key_id=self.signing_key_id,
            )
        return F1TurnResult(action="refusal", response=response)

    @staticmethod
    def _purpose_refusal(purpose: PurposeDeclaration) -> str | None:
        if not purpose.suspicion_rationale.strip():
            return "invalid_purpose"
        return None


def _needs_local_contribution(query: Sec314bQuery) -> bool:
    if query.query_shape != QueryShape.AGGREGATE_ACTIVITY:
        return False
    payload = query.query_payload
    return isinstance(payload, AggregateActivityPayload) and bool(
        {"pattern_aggregate", "pattern_aggregate_for_f2"} & set(payload.metrics)
    )


def _needs_sanctions_request(query: Sec314bQuery) -> bool:
    return query.purpose_declaration.typology_code == TypologyCode.SANCTIONS_EVASION


def _query_entity_hashes(query: Sec314bQuery) -> list[str]:
    # isinstance over the discriminated-union variants instead of hasattr
    # duck-typing: a future payload that happens to share a field name would
    # otherwise be silently caught here, and the field type is also checked
    # statically rather than via attribute lookup.
    payload = query.query_payload
    if isinstance(payload, (EntityPresencePayload, AggregateActivityPayload)):
        return list(payload.name_hashes)
    if isinstance(payload, CounterpartyLinkagePayload):
        return list(payload.counterparty_hashes)
    return []


def _message_times(
    message: Sec314bQuery | LocalSiloContributionRequest,
) -> tuple[datetime, datetime]:
    created_at = utc_now()
    return created_at, _safe_expires_at(message, now=created_at)


def _safe_expires_at(
    message: Sec314bQuery | LocalSiloContributionRequest,
    *,
    now: datetime | None = None,
) -> datetime:
    now = now or utc_now()
    if message.expires_at is not None and message.expires_at > now:
        return max(message.expires_at, now + timedelta(seconds=10))
    return now + timedelta(minutes=5)


def _safe_response_expiry(query: Sec314bQuery) -> datetime:
    now = utc_now()
    if query.expires_at is not None and query.expires_at > now:
        return max(query.expires_at, now + timedelta(seconds=10))
    return now + timedelta(minutes=5)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _nonce(
    query: Sec314bQuery,
    responding_bank_id: BankId,
    route_kind: RouteKind,
    retry_suffix: str | None,
) -> str | None:
    if query.nonce is None:
        return None
    suffix = f":{retry_suffix}" if retry_suffix else ""
    return f"{query.nonce}:f1:{route_kind.value}:{responding_bank_id.value}{suffix}"


def _a3_agent_id(bank_id: BankId) -> str:
    return f"{bank_id.value}.A3"


def _request_query_id(request: Sec314bQuery | LocalSiloContributionRequest) -> UUID:
    if isinstance(request, Sec314bQuery):
        return request.query_id
    return request.source_query_id


def _routed_requests_by_bank(
    requests: list[F1RoutedRequest],
) -> dict[BankId, F1RoutedRequest]:
    routed: dict[BankId, F1RoutedRequest] = {}
    for request in requests:
        routed[_routed_bank_id(request)] = request
    return routed


def _routed_bank_id(request: F1RoutedRequest) -> BankId:
    if isinstance(request, Sec314bQuery):
        return request.route_approval.responding_bank_id
    return request.responding_bank_id


def _retry_query_for_refusal(
    reason: str,
    routed_request: F1RoutedRequest,
) -> Sec314bQuery | None:
    if isinstance(routed_request, LocalSiloContributionRequest):
        query = _local_request_as_query(routed_request)
    else:
        query = routed_request
    payload = query.query_payload
    if not isinstance(payload, AggregateActivityPayload):
        return None
    if reason == "invalid_rho":
        if query.requested_rho_per_primitive >= DEFAULT_RETRY_RHO:
            return None
        return _validated_model_copy(
            query,
            update={"requested_rho_per_primitive": DEFAULT_RETRY_RHO},
        )
    if reason == "budget_exhausted" and query.requested_rho_per_primitive > MIN_RETRY_RHO:
        return _validated_model_copy(
            query,
            update={
                "requested_rho_per_primitive": max(
                    MIN_RETRY_RHO,
                    query.requested_rho_per_primitive / 2.0,
                )
            }
        )
    if reason == "unsupported_metric_combination":
        revised_payload = _supported_metric_payload(payload)
        if revised_payload is None:
            return None
        if list(revised_payload.metrics) == list(payload.metrics):
            return None
        return _validated_model_copy(query, update={"query_payload": revised_payload})
    return None


def _supported_metric_payload(
    payload: AggregateActivityPayload,
) -> AggregateActivityPayload | None:
    metrics = set(payload.metrics)
    if {"pattern_aggregate_for_f2", "pattern_aggregate"} & metrics:
        metric = (
            "pattern_aggregate_for_f2"
            if "pattern_aggregate_for_f2" in metrics
            else "pattern_aggregate"
        )
    elif "flow_histogram" in metrics:
        metric = "flow_histogram"
    elif "alert_count" in metrics and len(payload.name_hashes) > 1:
        metric = "flow_histogram"
    elif "alert_count" in metrics:
        metric = "alert_count"
    else:
        return None
    return _validated_model_copy(payload, update={"metrics": [metric]})


def _local_request_as_query(request: LocalSiloContributionRequest) -> Sec314bQuery:
    """Build a temporary query-shaped carrier for local-contribution retry logic.

    The result is never routed as a peer query. `_retry_query_for_refusal` uses
    the shared `Sec314bQuery` fields to adjust rho or payload shape, then
    `_build_local_contribution_request` wraps those adjusted fields back into a
    fresh `LocalSiloContributionRequest` for the requester's own A3.
    """
    return Sec314bQuery(
        sender_agent_id=request.sender_agent_id,
        sender_role=request.sender_role,
        sender_bank_id=request.sender_bank_id,
        recipient_agent_id=request.recipient_agent_id,
        created_at=request.created_at,
        expires_at=request.expires_at,
        nonce=request.nonce,
        query_id=request.source_query_id,
        requesting_investigator_id=request.requesting_investigator_id,
        requesting_bank_id=request.requesting_bank_id,
        # Iterate the BankId enum rather than a hardcoded peer list so a future
        # peer-bank addition is picked up automatically; FEDERATION is excluded
        # because it is the federation runtime, not a peer bank. Note: if a
        # future BankId variant ever represents a non-peer role (e.g. a
        # regulator or auditor), an explicit `is_peer_bank` predicate should
        # be added here. Today this carrier is only used by the
        # local-contribution retry path, which routes by
        # `responding_bank_id == requesting_bank_id`, so the synthesized
        # `target_bank_ids` is never actually dispatched to peers.
        target_bank_ids=[
            bank_id
            for bank_id in BankId
            if bank_id != BankId.FEDERATION and bank_id != request.requesting_bank_id
        ],
        query_shape=request.query_shape,
        query_payload=request.query_payload,
        purpose_declaration=request.purpose_declaration,
        requested_rho_per_primitive=request.requested_rho_per_primitive,
    )


def _validated_model_copy(model: ModelT, *, update: Mapping[str, Any]) -> ModelT:
    copied = model.model_copy(update=dict(update))
    return type(model).model_validate(copied.model_dump())


def _retry_attempts(request: F1RoutedRequest) -> int:
    return request.route_approval.retry_count


def _retry_detail(
    reason: str,
    original: F1RoutedRequest,
    retry: F1RoutedRequest,
    attempt: int,
) -> str:
    changes: list[str] = []
    if original.requested_rho_per_primitive != retry.requested_rho_per_primitive:
        changes.append(
            "rho "
            f"{original.requested_rho_per_primitive:g} -> "
            f"{retry.requested_rho_per_primitive:g}"
        )
    if isinstance(original.query_payload, AggregateActivityPayload) and isinstance(
        retry.query_payload,
        AggregateActivityPayload,
    ):
        old_metrics = ",".join(original.query_payload.metrics)
        new_metrics = ",".join(retry.query_payload.metrics)
        if old_metrics != new_metrics:
            changes.append(f"metrics {old_metrics} -> {new_metrics}")
    change_summary = "; ".join(changes) if changes else "no lossy field broadening"
    return (
        f"F1 created deterministic retry {attempt}/{MAX_NEGOTIATION_RETRIES} "
        f"after {reason}; {change_summary}"
    )


def _aggregate_refusal_reason(notes: list[F1NegotiationNote]) -> str:
    reasons = {note.refusal_reason for note in notes}
    if len(reasons) == 1:
        return next(iter(reasons))
    return "mixed_refusals"


def _response_refusal_notes(notes: list[F1NegotiationNote]) -> list[ResponseRefusalNote]:
    return [
        ResponseRefusalNote(
            responding_bank_id=note.responding_bank_id,
            refusal_reason=note.refusal_reason,
            decision=note.decision,
            detail=note.detail,
        )
        for note in notes
    ]


def _retry_decision(
    reason: str,
) -> str:
    # `invalid_rho` retries upgrade rho (e.g. 0.0 -> DEFAULT_RETRY_RHO) rather
    # than lowering it, so the audit label has to differ from `budget_exhausted`
    # which actually halves rho. Mislabeling muddies the audit trail for F5/UI.
    if reason == "budget_exhausted":
        return "retry_with_lower_rho"
    if reason == "invalid_rho":
        return "retry_with_valid_rho"
    if reason == "unsupported_metric_combination":
        return "retry_with_supported_metric"
    return "retry_with_lower_rho"


def _terminal_note(bank_id: BankId, reason: str, detail: str) -> F1NegotiationNote:
    return F1NegotiationNote(
        responding_bank_id=bank_id,
        refusal_reason=reason,
        decision="terminal_refusal",
        detail=detail,
    )


def _retry_route_plan(
    retry_requests: list[F1RoutedRequest],
    notes: list[F1NegotiationNote],
) -> F1RoutePlan:
    peer_requests = [request for request in retry_requests if isinstance(request, Sec314bQuery)]
    local_requests = [
        request for request in retry_requests if isinstance(request, LocalSiloContributionRequest)
    ]
    # F1RoutePlan.local_request is a single optional field because the demo's
    # architecture only routes one LocalSiloContributionRequest per query (the
    # requesting bank's own A3). Fail loud rather than silently drop additional
    # local requests if a future call ever violates that invariant.
    if len(local_requests) > 1:
        raise InvalidAgentInput(
            "internal invariant violated: retry plan contains "
            f"{len(local_requests)} LocalSiloContributionRequest entries; "
            "F1RoutePlan.local_request only carries one"
        )
    return F1RoutePlan(
        peer_requests=peer_requests,
        local_request=local_requests[0] if local_requests else None,
        negotiation_notes=notes,
    )
