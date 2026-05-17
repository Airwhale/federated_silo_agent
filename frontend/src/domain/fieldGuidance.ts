import type { ComponentId } from "@/api/types";

type FieldGuidance = {
  help: string;
  dangerousWhen?: (value: unknown) => boolean;
};

const GENERIC_FIELD_GUIDANCE: Record<string, FieldGuidance> = {
  available_after: {
    help: "Possible values: now, a milestone like P12, or a later phase. Correct when it matches the component status. Dangerous if an unbuilt component claims it is available now.",
  },
  availability: {
    help: "Possible values: live now, pending, or simulated. Correct for F5 is live now, meaning the component exists and can be inspected. Dangerous if this says live while the behavior is still only a placeholder.",
  },
  detail: {
    help: "Human-readable state detail. Correct when it explains the current status. Dangerous if it claims a live protection exists when the status is pending or not_built.",
  },
  component: {
    help: "Component identifier returned by the backend snapshot. Correct when it matches the drawer target.",
  },
  "private key exposed": {
    help: "Possible values: yes or no. Correct is no. Dangerous is yes, because private signing material would be visible.",
    dangerousWhen: (value) => String(value).toLowerCase() === "yes",
  },
  "last verified key": {
    help: "Signing key id most recently verified. Correct when present after signed traffic. Muted/not recorded is acceptable before any signed message.",
  },
  "known keys": {
    help: "Registered public signing keys. Correct when expected principals are listed. Dangerous if unknown keys appear or the list is empty in a live signed path.",
  },
  message: {
    help: "Envelope message type. Correct values are the typed protocol messages expected on this route. Dangerous if a sender uses a message type it is not allowed to send.",
  },
  sender: {
    help: "Declared sender agent. Correct when it matches the signing key and allowlist. Dangerous if the role or bank is spoofed.",
  },
  recipient: {
    help: "Declared recipient agent. Correct when it matches the route. Dangerous if a message is addressed to the wrong component.",
  },
  "body hash": {
    help: "Canonical hash of the signed body. Correct when it matches the signed payload. Dangerous if it changes after signing.",
  },
  signature: {
    help: "Possible values: valid, invalid, missing, not_checked. Correct is valid for signed traffic. Dangerous is invalid or missing.",
    dangerousWhen: (value) => ["invalid", "missing"].includes(String(value)),
  },
  freshness: {
    help: "Possible values: fresh, expired, not_checked. Correct is fresh for live inbound traffic. Dangerous is expired.",
    dangerousWhen: (value) => String(value) === "expired",
  },
  binding: {
    help: "Possible values: matched, mismatched, not_checked. Correct is matched. Dangerous is mismatched because the approved route no longer matches the body.",
    dangerousWhen: (value) => String(value) === "mismatched",
  },
  "route kind": {
    help: "Route class such as peer_314b or local_contribution. Correct when it matches the request shape and banks involved.",
  },
  requester: {
    help: "Bank or investigator requesting the operation. Correct when it matches the approved route.",
  },
  responder: {
    help: "Bank expected to answer. Correct when it matches the silo receiving the request.",
  },
  "approved hash": {
    help: "Body hash that F1 approved. Correct when it equals computed hash. Dangerous when a different body is sent under the same approval.",
  },
  "computed hash": {
    help: "Body hash calculated from the message being checked now. Correct when it matches approved hash.",
  },
  events: {
    help: "Number of durable audit-chain events. Correct is 0 while audit persistence is not built. Dangerous if UI timeline events are misrepresented as a durable chain.",
  },
  "latest hash": {
    help: "Latest hash-chain event digest. Correct when populated after audit-chain persistence lands. Not built is acceptable before P13/P15.",
  },
  destination: {
    help: "Selected model-route endpoint. Correct when it matches the active path.",
  },
  origin: {
    help: "Model-using component that owns the prompt. Correct when judges selected the intended A1/A2/F2/F4 origin.",
  },
  "route path": {
    help: "Possible values include Origin -> Lobster Trap -> LiteLLM -> provider, or direct Origin -> LiteLLM -> provider for a bypass test. Correct default includes Lobster Trap.",
    dangerousWhen: (value) => !String(value).includes("Lobster Trap"),
  },
  "active endpoint": {
    help: "Backend model-route endpoint receiving the interaction. Correct is the model route; Lobster Trap is a gate in the route path, not the destination.",
  },
  readiness: {
    help: "Backend readiness detail. Correct when it states live, pending, or not_built honestly.",
  },
  "last result": {
    help: "Most recent interaction outcome for this selected route. Correct when it states which stage accepted or blocked the request.",
  },
  "trust domain": {
    help: "Trust domain whose local model route is being observed. Correct when it matches the selected graph origin.",
  },
  "route state": {
    help: "Model-route configuration state. Correct when LT and LiteLLM are both configured. Incomplete means later stages are not ready.",
  },
  "lobster trap": {
    help: "Possible values: configured or missing. Correct is configured for model-bound paths. Missing means prompt policy scanning is unavailable.",
    dangerousWhen: (value) => String(value).toLowerCase() === "missing",
  },
  "litellm proxy": {
    help: "Possible values: configured or missing. Correct is configured when model routing is expected. Missing means no local model proxy is ready.",
    dangerousWhen: (value) => String(value).toLowerCase() === "missing",
  },
  "model credentials": {
    help: "Shows whether provider credentials are present without revealing them. Correct is provider present for live model calls; none reported is acceptable for offline demo mode.",
  },
  "secret values": {
    help: "Correct value is redacted. Dangerous if API keys or private material appear.",
    dangerousWhen: (value) => String(value).toLowerCase() !== "redacted",
  },
  "live adapter": {
    help: "Indicates whether this panel is still a presence snapshot or live telemetry. Pending adapter means model calls are not executing yet.",
  },
};

const COMPONENT_FIELD_GUIDANCE: Partial<Record<ComponentId, Record<string, FieldGuidance>>> = {
  F2: {
    analysis_mode: {
      help: "Possible values: deterministic, hybrid, or model_only. Correct is hybrid: deterministic rules first, LLM fallback only for ambiguous cases. Dangerous is model_only.",
      dangerousWhen: (value) => String(value) === "model_only",
    },
    clear_positive_rules: {
      help: "Expected F2 deterministic rules, such as F2-B1 and F2-B2. Correct when both structuring-ring and layering-chain rules are present.",
    },
    input_boundary: {
      help: "Expected value: dp_noised_aggregates. Correct means F2 sees hash-only DP aggregate summaries. Dangerous values would imply raw transactions or customer names.",
      dangerousWhen: (value) => String(value) !== "dp_noised_aggregates",
    },
  },
  F3: {
    watchlist_entries: {
      help: "Number of sanctions watchlist entries loaded. Correct when nonzero for a live sanctions screen. Dangerous if zero while claiming live screening.",
      dangerousWhen: (value) => Number(value) === 0,
    },
  },
  F4: {},
  F5: {
    availability: {
      help: "Correct value is live now. F5 is built as a deterministic, read-only auditor; dangerous would be pending or not_built after P13 is merged.",
      dangerousWhen: (value) => String(value).toLowerCase() !== "live now",
    },
  },
  lobster_trap: {
    detail: {
      help: "Correct when it says the local policy proxy is reachable. Dangerous if prompt attacks are shown as pending or only configured after the proxy is running.",
    },
  },
  litellm: {
    detail: {
      help: "Correct when it says the local model proxy is reachable. Dangerous if direct model-route tests are shown as pending after LiteLLM is running.",
    },
  },
};

export function fieldGuidance(
  componentId: ComponentId | undefined,
  label: string,
  value?: unknown,
): { help?: string; dangerous?: boolean } {
  const key = label.toLowerCase();
  const componentGuidance = componentId
    ? COMPONENT_FIELD_GUIDANCE[componentId]?.[label]
      ?? COMPONENT_FIELD_GUIDANCE[componentId]?.[key]
    : undefined;
  const genericGuidance = GENERIC_FIELD_GUIDANCE[label] ?? GENERIC_FIELD_GUIDANCE[key];
  const guidance = componentGuidance ?? genericGuidance;
  if (!guidance) {
    return {
      help: `Possible values depend on ${componentId ?? "this component"} runtime state. Healthy values match the component guide and backend contract; dangerous values imply raw-data exposure, missing controls, or misleading readiness.`,
      dangerous: false,
    };
  }
  return {
    help: guidance.help,
    dangerous: guidance.dangerousWhen?.(value) ?? false,
  };
}
