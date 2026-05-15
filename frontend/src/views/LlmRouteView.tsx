import { Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { describeError } from "@/api/errors";
import { useInteraction, useSystem } from "@/api/hooks";
import type {
  AttackerProfile,
  ComponentId,
  ComponentInteractionKind,
  ComponentInteractionResult,
  ProviderHealthSnapshot,
  SnapshotStatus,
} from "@/api/types";
import { FieldLabel } from "@/components/forms/FieldLabel";
import { KeyValueGrid, type KeyValueRow } from "@/components/inspector/KeyValueGrid";
import { ModelRoutePanel } from "@/components/inspector/ModelRoutePanel";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";
import {
  TRUST_INSTANCES,
  trustDomainLabel,
  type TrustDomain,
  type TrustTier,
} from "@/domain/instances";

type RouteDestination = Extract<ComponentId, "litellm" | "lobster_trap">;

// Route graph models the actual LLM call chain:
//
//   LLM-driven agent ──→ Lobster Trap ──→ LiteLLM ──→ provider
//
// Five trust-domain nodes is a topology that fits on a slide but lies
// about the LLM graph: F3 sanctions and F5 auditor are deterministic
// (no LLM call), F2 graph analysis is aggregate-only (no LLM), and the
// LT + LiteLLM proxies are single global hops shared by every LLM-
// driven agent. The layered DAG below reflects that.

type LlmAgentNode = {
  id: string;
  label: string;
  componentId: ComponentId;
  trustDomain: TrustDomain;
  tier: TrustTier;
};

type LlmAgentNodeState = {
  agent: LlmAgentNode;
  status: SnapshotStatus;
  lastResult?: ComponentInteractionResult;
};

const LLM_AGENTS: LlmAgentNode[] = [
  { id: "A1", label: "A1 monitor", componentId: "A1", trustDomain: "investigator", tier: "investigator" },
  { id: "A2", label: "A2 investigator", componentId: "A2", trustDomain: "investigator", tier: "investigator" },
  { id: "F1", label: "F1 coordinator", componentId: "F1", trustDomain: "federation", tier: "federation" },
  { id: "F4", label: "F4 SAR drafter", componentId: "F4", trustDomain: "federation", tier: "federation" },
  { id: "A3a", label: "A3 alpha", componentId: "bank_alpha.A3", trustDomain: "bank_alpha", tier: "silo" },
  { id: "A3b", label: "A3 beta", componentId: "bank_beta.A3", trustDomain: "bank_beta", tier: "silo" },
  { id: "A3g", label: "A3 gamma", componentId: "bank_gamma.A3", trustDomain: "bank_gamma", tier: "silo" },
];

const TIER_LABEL: Record<TrustTier, string> = {
  investigator: "Investigator",
  federation: "Federation",
  silo: "Silos",
};

// Deterministic agents -- listed off-graph so a judge can see at a
// glance what's deliberately not on the LLM path (and why those
// branches don't need policy/proxy oversight today).
const DETERMINISTIC_AGENTS: { id: string; label: string; componentId: ComponentId; rationale: string }[] = [
  { id: "F2", label: "F2 graph", componentId: "F2", rationale: "Aggregate-only graph analytics over DP-noised signals." },
  { id: "F3", label: "F3 sanctions", componentId: "F3", rationale: "Exact-hash watchlist screening; LLM would risk list leakage." },
  { id: "F5", label: "F5 auditor", componentId: "F5", rationale: "Schema-based audit-chain checks; deterministic by design." },
];

const ROUTE_DESTINATIONS: { id: RouteDestination; label: string; detail: string }[] = [
  {
    id: "litellm",
    label: "Model route",
    detail: "Local route to the configured model provider",
  },
  {
    id: "lobster_trap",
    label: "Lobster Trap",
    detail: "Prompt and policy gate before model execution",
  },
];

const INTERACTION_KINDS: ComponentInteractionKind[] = [
  "prompt",
  "safe_input",
  "inspect",
  "explain_state",
];

const ATTACKER_PROFILES: AttackerProfile[] = [
  "valid_but_malicious",
  "unknown",
  "wrong_role",
];

// Layout: 7 agent origins on the left, then LT, LiteLLM, provider in a
// horizontal chain. Y positions stack the agents from top to bottom in
// tier order (investigator > federation > silos) so the visual grouping
// matches the rest of the console.
const AGENT_X = 170;
const LT_X = 400;
const LITELLM_X = 560;
const PROVIDER_X = 720;
const CHAIN_Y = 230;
const AGENT_Y_TOP = 70;
const AGENT_Y_STEP = 50;
const NODE_RADIUS = 22;
const NODE_RADIUS_CHAIN = 30;

export function LlmRouteView() {
  const { sessionId, setSelection } = useSessionContext();
  const system = useSystem();
  const [selectedDomain, setSelectedDomain] = useState<TrustDomain>("federation");
  const [destination, setDestination] = useState<RouteDestination>("litellm");
  const [interactionKind, setInteractionKind] = useState<ComponentInteractionKind>("prompt");
  const [attackerProfile, setAttackerProfile] =
    useState<AttackerProfile>("valid_but_malicious");
  const [payloadText, setPayloadText] = useState("");
  // Key results by ``${domain}:${destination}`` so switching the
  // destination dropdown (litellm <-> lobster_trap) doesn't show
  // stale results from the other destination's last interaction.
  const [lastResults, setLastResults] = useState<Record<string, ComponentInteractionResult>>({});
  const interaction = useInteraction(sessionId, destination);

  // Clear the mutation's data/error badges when the destination
  // changes. Without this the "Executed" / "Placeholder" / "API said"
  // chip from the previous destination would persist until a new
  // interaction fires.
  useEffect(() => {
    interaction.reset();
    // ``interaction`` is a useMutation result; its ``reset`` is stable
    // per hook instance. Re-running on every ``interaction`` identity
    // change would loop, so we only depend on ``destination``.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destination]);

  const resultKey = (domain: TrustDomain, dest: RouteDestination) => `${domain}:${dest}`;

  const providerHealth = system.data?.provider_health ?? null;
  const readinessByComponent = useMemo(
    () =>
      new Map(
        (system.data?.components ?? []).map((component) => [
          component.component_id,
          component,
        ]),
      ),
    [system.data?.components],
  );

  // System-readiness loading state is distinct from "the component is
  // genuinely pending": fall back to ``pending`` only while we have no
  // data, and use ``error`` when the system snapshot failed outright.
  const readinessFallback: SnapshotStatus = system.isLoading
    ? "pending"
    : system.error
    ? "error"
    : "pending";

  const statusOf = (componentId: ComponentId): SnapshotStatus =>
    readinessByComponent.get(componentId)?.status ?? readinessFallback;

  const agentStates = useMemo<LlmAgentNodeState[]>(
    () =>
      LLM_AGENTS.map((agent) => ({
        agent,
        status: statusOf(agent.componentId),
        lastResult: lastResults[resultKey(agent.trustDomain, destination)],
      })),
    // statusOf depends on readinessByComponent + readinessFallback; the
    // function reference itself rotates each render but its inputs are
    // captured by the dependencies list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [destination, lastResults, readinessByComponent, readinessFallback],
  );

  const selectedDestination = ROUTE_DESTINATIONS.find((item) => item.id === destination)
    ?? ROUTE_DESTINATIONS[0];
  const selectedReadiness = readinessByComponent.get(destination);
  const selectedResult = lastResults[resultKey(selectedDomain, destination)];

  const submit = () => {
    interaction.mutate(
      {
        interaction_kind: interactionKind,
        payload_text: payloadText.trim() || undefined,
        target_instance_id: selectedDomain,
        attacker_profile: attackerProfile,
      },
      {
        onSuccess: (result) => {
          setLastResults((current) => ({
            ...current,
            [resultKey(selectedDomain, destination)]: result,
          }));
        },
      },
    );
  };

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section className="min-w-0 rounded-lg border border-slate-800 bg-slate-950">
        <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-slate-800/70 px-3 py-2">
          <div className="flex items-baseline gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
              LLM route graph
            </h2>
            <span className="text-[11px] text-slate-500">
              Agent &rarr; Lobster Trap &rarr; LiteLLM &rarr; provider &middot; click an agent to focus the input form
            </span>
          </div>
          <StatusPill status={providerHealth?.status ?? "pending"} />
        </header>

        <RouteGraph
          agents={agentStates}
          providerHealth={providerHealth}
          ltStatus={statusOf("lobster_trap")}
          litellmStatus={statusOf("litellm")}
          selectedDomain={selectedDomain}
          onSelectAgent={(agent) => {
            setSelectedDomain(agent.trustDomain);
            setSelection({ componentId: agent.componentId, instanceId: agent.trustDomain });
          }}
        />

        <OffGraphRow />
        <Legend providerHealth={providerHealth} />
      </section>

      <aside className="flex min-w-0 flex-col gap-3">
        <section className="flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-950">
          <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-slate-800/70 px-3 py-2">
            <div className="flex items-baseline gap-2">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
                Unified route input
              </h2>
              <span className="text-[11px] text-slate-500">
                One bounded interaction per send
              </span>
            </div>
            {interaction.data ? <StatusPill status={interaction.data.status} /> : null}
          </header>

          <div className="flex flex-col gap-2 px-3 pb-3">
            <FieldLabel label="Trust domain">
              <select
                value={selectedDomain}
                onChange={(event) => setSelectedDomain(event.target.value as TrustDomain)}
                className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100"
              >
                {TRUST_INSTANCES.map((instance) => (
                  <option key={instance.id} value={instance.id}>
                    {instance.label}
                  </option>
                ))}
              </select>
            </FieldLabel>

            <FieldLabel label="Destination">
              <select
                value={destination}
                onChange={(event) => setDestination(event.target.value as RouteDestination)}
                className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100"
              >
                {ROUTE_DESTINATIONS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </FieldLabel>

            <div className="grid gap-2 sm:grid-cols-2">
              <FieldLabel label="Interaction">
                <select
                  value={interactionKind}
                  onChange={(event) =>
                    setInteractionKind(event.target.value as ComponentInteractionKind)
                  }
                  className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100"
                >
                  {INTERACTION_KINDS.map((kind) => (
                    <option key={kind} value={kind}>
                      {kind.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </FieldLabel>

              <FieldLabel label="Sender profile">
                <select
                  value={attackerProfile}
                  onChange={(event) =>
                    setAttackerProfile(event.target.value as AttackerProfile)
                  }
                  className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100"
                >
                  {ATTACKER_PROFILES.map((profile) => (
                    <option key={profile} value={profile}>
                      {profile.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </FieldLabel>
            </div>

            <textarea
              value={payloadText}
              onChange={(event) => setPayloadText(event.target.value)}
              maxLength={4096}
              rows={3}
              className="resize-y rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-[11px] text-slate-100"
              placeholder="Demo-safe route input"
            />

            <button
              type="button"
              disabled={!sessionId || interaction.isPending}
              onClick={submit}
              className="inline-flex items-center justify-center gap-1.5 self-start rounded border border-sky-400/60 bg-sky-500/15 px-3 py-1 text-xs font-medium text-sky-100 hover:bg-sky-500/25 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send size={12} aria-hidden />
              {interaction.isPending ? "Sending" : "Send to route"}
            </button>

            {interaction.error instanceof Error ? (
              <div className="rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-100">
                {describeError(interaction.error)}
              </div>
            ) : null}
          </div>
        </section>

        <RouteStatePanel
          domain={selectedDomain}
          destination={selectedDestination}
          readinessStatus={selectedReadiness?.status ?? "pending"}
          readinessDetail={selectedReadiness?.detail ?? "System snapshot is loading."}
          providerHealth={providerHealth}
          lastResult={selectedResult}
        />
      </aside>
    </div>
  );
}

interface RouteGraphProps {
  agents: LlmAgentNodeState[];
  providerHealth: ProviderHealthSnapshot | null;
  ltStatus: SnapshotStatus;
  litellmStatus: SnapshotStatus;
  selectedDomain: TrustDomain;
  onSelectAgent: (agent: LlmAgentNode) => void;
}

function statusStroke(status: SnapshotStatus, selected = false): string {
  if (selected) return "rgb(56 189 248)"; // sky-400
  switch (status) {
    case "live":
      return "rgb(52 211 153)"; // emerald-400
    case "simulated":
      return "rgb(125 211 252)"; // sky-300
    case "blocked":
    case "error":
      return "rgb(248 113 113)"; // red-400
    case "pending":
      return "rgb(234 179 8)"; // amber-500
    case "not_built":
    default:
      return "rgb(71 85 105)"; // slate-600
  }
}

function tierMidY(tier: TrustTier, agents: LlmAgentNode[]): number {
  const indices = agents
    .map((agent, idx) => ({ agent, idx }))
    .filter((entry) => entry.agent.tier === tier);
  if (indices.length === 0) return CHAIN_Y;
  const sum = indices.reduce(
    (acc, entry) => acc + AGENT_Y_TOP + entry.idx * AGENT_Y_STEP,
    0,
  );
  return sum / indices.length;
}

function RouteGraph({
  agents,
  providerHealth,
  ltStatus,
  litellmStatus,
  selectedDomain,
  onSelectAgent,
}: RouteGraphProps) {
  const providerStatus = providerHealth?.status ?? "pending";
  const tiers: TrustTier[] = ["investigator", "federation", "silo"];

  return (
    <div className="overflow-x-auto px-3 py-2">
      <svg
        viewBox="0 30 800 410"
        role="img"
        aria-label="LLM route graph: LLM-driven agents flow through Lobster Trap and LiteLLM to the model provider"
        className="h-auto w-full max-w-[860px]"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Tier band labels on the far left so the visual grouping is
            labelled once instead of decorating each agent node. */}
        {tiers.map((tier) => {
          const y = tierMidY(tier, LLM_AGENTS);
          return (
            <text
              key={tier}
              x={40}
              y={y}
              dominantBaseline="middle"
              fill="rgb(148 163 184)"
              fontSize={10}
              fontFamily="ui-sans-serif, system-ui, -apple-system"
              fontWeight={600}
              style={{ letterSpacing: "0.08em" }}
            >
              {TIER_LABEL[tier].toUpperCase()}
            </text>
          );
        })}

        {/* Edges -- agents to LT, then LT -> LiteLLM -> Provider.
            Dashed lines so the nodes stay visually dominant. */}
        {agents.map((state, idx) => {
          const y = AGENT_Y_TOP + idx * AGENT_Y_STEP;
          return (
            <line
              key={`edge-${state.agent.id}-lt`}
              x1={AGENT_X + NODE_RADIUS}
              y1={y}
              x2={LT_X - NODE_RADIUS_CHAIN}
              y2={CHAIN_Y}
              stroke="rgb(51 65 85)"
              strokeWidth={1.25}
              strokeDasharray="3 4"
            />
          );
        })}
        <line
          x1={LT_X + NODE_RADIUS_CHAIN}
          y1={CHAIN_Y}
          x2={LITELLM_X - NODE_RADIUS_CHAIN}
          y2={CHAIN_Y}
          stroke="rgb(71 85 105)"
          strokeWidth={1.75}
        />
        <line
          x1={LITELLM_X + NODE_RADIUS_CHAIN}
          y1={CHAIN_Y}
          x2={PROVIDER_X - NODE_RADIUS_CHAIN}
          y2={CHAIN_Y}
          stroke="rgb(71 85 105)"
          strokeWidth={1.75}
        />

        {/* Column captions above each chain node. */}
        <text x={LT_X} y={50} textAnchor="middle" fill="rgb(148 163 184)" fontSize={10} fontWeight={600} style={{ letterSpacing: "0.08em" }}>
          POLICY GATE
        </text>
        <text x={LITELLM_X} y={50} textAnchor="middle" fill="rgb(148 163 184)" fontSize={10} fontWeight={600} style={{ letterSpacing: "0.08em" }}>
          MODEL PROXY
        </text>
        <text x={PROVIDER_X} y={50} textAnchor="middle" fill="rgb(148 163 184)" fontSize={10} fontWeight={600} style={{ letterSpacing: "0.08em" }}>
          PROVIDER
        </text>

        {/* Agent nodes. */}
        {agents.map((state, idx) => (
          <AgentNode
            key={state.agent.id}
            state={state}
            y={AGENT_Y_TOP + idx * AGENT_Y_STEP}
            selected={state.agent.trustDomain === selectedDomain}
            onSelect={() => onSelectAgent(state.agent)}
          />
        ))}

        <ChainNode
          x={LT_X}
          label="Lobster Trap"
          subtitle="Policy gate"
          status={ltStatus}
        />
        <ChainNode
          x={LITELLM_X}
          label="LiteLLM"
          subtitle="Single global proxy"
          status={litellmStatus}
        />
        <ChainNode
          x={PROVIDER_X}
          label="Provider"
          subtitle={providerLabel(providerHealth)}
          status={providerStatus}
        />
      </svg>
    </div>
  );
}

function providerLabel(providerHealth: ProviderHealthSnapshot | null): string {
  if (!providerHealth) return "Gemini / OpenRouter";
  if (providerHealth.gemini_api_key_present && providerHealth.openrouter_api_key_present) {
    return "Gemini + OpenRouter";
  }
  if (providerHealth.gemini_api_key_present) return "Gemini";
  if (providerHealth.openrouter_api_key_present) return "OpenRouter";
  return "Gemini / OpenRouter";
}

interface AgentNodeProps {
  state: LlmAgentNodeState;
  y: number;
  selected: boolean;
  onSelect: () => void;
}

function AgentNode({ state, y, selected, onSelect }: AgentNodeProps) {
  const { agent } = state;
  const x = AGENT_X;
  const effectiveStatus = state.lastResult?.status ?? state.status;

  return (
    <g
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      className="cursor-pointer outline-none"
      aria-label={`Focus ${agent.label} route input`}
    >
      <circle
        cx={x}
        cy={y}
        r={NODE_RADIUS}
        fill="rgb(15 23 42)"
        stroke={statusStroke(effectiveStatus, selected)}
        strokeWidth={selected ? 2.5 : 1.5}
        className="hover:stroke-emerald-400/70"
      />
      <text
        x={x}
        y={y + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="rgb(226 232 240)"
        fontSize={11}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
      >
        {agent.id}
      </text>
      <text
        x={x + NODE_RADIUS + 6}
        y={y + 2}
        textAnchor="start"
        dominantBaseline="middle"
        fill="rgb(203 213 225)"
        fontSize={10}
      >
        {agent.label}
      </text>
      <text
        x={x + NODE_RADIUS + 6}
        y={y + 14}
        textAnchor="start"
        dominantBaseline="middle"
        fill="rgb(100 116 139)"
        fontSize={9}
      >
        {trustDomainLabel(agent.trustDomain)}
      </text>
      <title>{`${agent.label} (${agent.componentId}) -- status: ${effectiveStatus}`}</title>
    </g>
  );
}

function ChainNode({
  x,
  label,
  subtitle,
  status,
}: {
  x: number;
  label: string;
  subtitle: string;
  status: SnapshotStatus;
}) {
  return (
    <g>
      <circle
        cx={x}
        cy={CHAIN_Y}
        r={NODE_RADIUS_CHAIN}
        fill="rgb(15 23 42)"
        stroke={statusStroke(status)}
        strokeWidth={2}
      />
      <text
        x={x}
        y={CHAIN_Y + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="rgb(226 232 240)"
        fontSize={10}
        fontWeight={600}
      >
        {label}
      </text>
      <text
        x={x}
        y={CHAIN_Y + NODE_RADIUS_CHAIN + 14}
        textAnchor="middle"
        fill="rgb(148 163 184)"
        fontSize={9}
      >
        {subtitle}
      </text>
      <text
        x={x}
        y={CHAIN_Y + NODE_RADIUS_CHAIN + 26}
        textAnchor="middle"
        fill="rgb(100 116 139)"
        fontSize={9}
      >
        {status}
      </text>
    </g>
  );
}

function OffGraphRow() {
  return (
    <div className="border-t border-slate-800/70 px-3 py-2 text-xs">
      <div className="mb-1.5 flex items-baseline gap-2">
        <h3 className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
          Off-graph &middot; no LLM call
        </h3>
        <span className="text-[10px] text-slate-600">
          Deterministic agents are deliberately off the policy / proxy chain.
        </span>
      </div>
      <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
        {DETERMINISTIC_AGENTS.map((agent) => (
          <li
            key={agent.id}
            className="flex flex-col gap-0.5 rounded border border-slate-800/70 bg-slate-900/40 px-2 py-1.5 opacity-70"
          >
            <span className="flex items-baseline gap-2">
              <span className="font-mono text-[10px] text-slate-300">{agent.id}</span>
              <span className="text-[11px] text-slate-200">{agent.label}</span>
            </span>
            <span className="text-[10px] text-slate-500">{agent.rationale}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface LegendProps {
  providerHealth: ProviderHealthSnapshot | null;
}

function Legend({ providerHealth }: LegendProps) {
  const items: { label: string; on: boolean }[] = [
    { label: "Lobster Trap configured", on: Boolean(providerHealth?.lobster_trap_configured) },
    { label: "LiteLLM proxy configured", on: Boolean(providerHealth?.litellm_configured) },
    {
      label: "Provider key present (Gemini or OpenRouter)",
      on: Boolean(providerHealth?.gemini_api_key_present)
        || Boolean(providerHealth?.openrouter_api_key_present),
    },
  ];

  return (
    <div className="border-t border-slate-800/70 px-3 py-2 text-xs">
      <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        Provider config
      </h3>
      <ul className="grid grid-cols-1 gap-1 sm:grid-cols-3">
        {items.map((item) => (
          <li key={item.label} className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ background: item.on ? "rgb(52 211 153)" : "rgb(51 65 85)" }}
              aria-hidden
            />
            <span className="text-slate-300">{item.label}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[10px] text-slate-500">
        LT and LiteLLM are single global hops shared by every LLM-driven
        agent today; per-agent route metadata lands with P14.
      </p>
    </div>
  );
}

function RouteStatePanel({
  domain,
  destination,
  readinessStatus,
  readinessDetail,
  providerHealth,
  lastResult,
}: {
  domain: TrustDomain;
  destination: { id: RouteDestination; label: string; detail: string };
  readinessStatus: SnapshotStatus;
  readinessDetail: string;
  providerHealth: ProviderHealthSnapshot | null;
  lastResult?: ComponentInteractionResult;
}) {
  const rows: KeyValueRow[] = [
    { label: "Destination", value: destination.detail },
    { label: "Readiness", value: readinessDetail, tone: readinessStatus === "live" ? "good" : "muted" },
    {
      label: "Last result",
      value: lastResult ? (
        <span className="flex flex-wrap items-center gap-1.5">
          <span>{lastResult.reason}</span>
          <StatusPill status={lastResult.status} />
          {lastResult.blocked_by ? <StatusPill layer={lastResult.blocked_by} /> : null}
        </span>
      ) : (
        "No interaction recorded for this instance"
      ),
      tone: lastResult ? "default" : "muted",
    },
  ];

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-slate-800/70 px-3 py-2">
        <div className="flex items-baseline gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Selected route
          </h2>
          <span className="text-[11px] text-slate-500">
            {trustDomainLabel(domain)} &rarr; {destination.label}
          </span>
        </div>
        <StatusPill status={lastResult?.status ?? readinessStatus} />
      </header>
      <div className="flex flex-col gap-2 p-3 text-xs">
        <KeyValueGrid rows={rows} />
        {providerHealth ? (
          <ModelRoutePanel
            providerHealth={providerHealth}
            trustDomainLabel={trustDomainLabel(domain)}
            lastResult={lastResult?.reason}
          />
        ) : null}
      </div>
    </section>
  );
}

