import { Network, Send } from "lucide-react";
import { useMemo, useState } from "react";
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
import { ModelRoutePanel } from "@/components/inspector/ModelRoutePanel";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";
import { TRUST_INSTANCES, trustDomainLabel, type TrustDomain } from "@/domain/instances";

type RouteDestination = Extract<ComponentId, "litellm" | "lobster_trap">;

type NodePosition = {
  x: number;
  y: number;
};

type RouteNodeState = {
  domain: TrustDomain;
  status: SnapshotStatus;
  lastResult?: ComponentInteractionResult;
};

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

const NODE_POSITIONS: Record<TrustDomain, NodePosition> = {
  investigator: { x: 120, y: 250 },
  federation: { x: 410, y: 250 },
  bank_alpha: { x: 720, y: 105 },
  bank_beta: { x: 750, y: 250 },
  bank_gamma: { x: 720, y: 395 },
};

const EDGES: { from: TrustDomain; to: TrustDomain; label: string }[] = [
  { from: "investigator", to: "federation", label: "A2 to F1" },
  { from: "federation", to: "bank_alpha", label: "F1 to A3" },
  { from: "federation", to: "bank_beta", label: "F1 to A3" },
  { from: "federation", to: "bank_gamma", label: "F1 to A3" },
];

const NODE_SIZE = {
  width: 184,
  height: 132,
};

export function LlmRouteView() {
  const { sessionId, setSelection } = useSessionContext();
  const system = useSystem();
  const [selectedDomain, setSelectedDomain] = useState<TrustDomain>("federation");
  const [destination, setDestination] = useState<RouteDestination>("litellm");
  const [interactionKind, setInteractionKind] = useState<ComponentInteractionKind>("prompt");
  const [attackerProfile, setAttackerProfile] =
    useState<AttackerProfile>("valid_but_malicious");
  const [payloadText, setPayloadText] = useState("");
  const [lastResults, setLastResults] = useState<Partial<Record<TrustDomain, ComponentInteractionResult>>>({});
  const interaction = useInteraction(sessionId, destination);

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
  // genuinely pending" — fall back to ``pending`` only while we have no
  // data, and use ``error`` when the system snapshot failed outright.
  // ``simulated`` is reserved for a future P14 per-instance status.
  const readinessFallback: SnapshotStatus = system.isLoading
    ? "pending"
    : system.error
    ? "error"
    : "pending";
  const nodeStates = useMemo<RouteNodeState[]>(
    () =>
      TRUST_INSTANCES.map((instance) => ({
        domain: instance.id,
        status: readinessByComponent.get(destination)?.status ?? readinessFallback,
        lastResult: lastResults[instance.id],
      })),
    [destination, lastResults, readinessByComponent, readinessFallback],
  );

  const selectedDestination = ROUTE_DESTINATIONS.find((item) => item.id === destination)
    ?? ROUTE_DESTINATIONS[0];
  const selectedReadiness = readinessByComponent.get(destination);
  const selectedResult = lastResults[selectedDomain];

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
            [selectedDomain]: result,
          }));
        },
      },
    );
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
      <section className="min-w-0 rounded-lg border border-slate-800 bg-slate-950">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
              <Network size={16} aria-hidden />
              LLM Route Graph
            </h2>
            <p className="mt-1 max-w-3xl text-xs text-slate-500">
              One route surface per trust domain. P9b shows shared provider
              configuration plus per-instance interaction state so P14/P15 can
              replace placeholders without changing this graph.
            </p>
          </div>
          {providerHealth ? <StatusPill status={providerHealth.status} /> : <StatusPill status="pending" />}
        </div>

        <div className="overflow-x-auto p-4">
          <div className="relative h-[520px] min-w-[940px]">
            <RouteEdges />
            {nodeStates.map((node) => (
              <RouteNode
                key={node.domain}
                node={node}
                providerHealth={providerHealth}
                selected={node.domain === selectedDomain}
                onSelect={() => {
                  setSelectedDomain(node.domain);
                  setSelection({ componentId: destination, instanceId: node.domain });
                }}
              />
            ))}
          </div>
        </div>
      </section>

      <aside className="flex min-w-0 flex-col gap-4">
        <section className="rounded-lg border border-slate-800 bg-slate-950 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-white">Unified Route Input</h2>
              <p className="mt-1 text-xs text-slate-500">
                Select where the input goes, then send one bounded interaction.
              </p>
            </div>
            {interaction.data ? <StatusPill status={interaction.data.status} /> : null}
          </div>

          <div className="mt-4 grid gap-2">
            <label className="grid gap-1 text-xs text-slate-400">
              Trust domain
              <select
                value={selectedDomain}
                onChange={(event) => setSelectedDomain(event.target.value as TrustDomain)}
                className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
              >
                {TRUST_INSTANCES.map((instance) => (
                  <option key={instance.id} value={instance.id}>
                    {instance.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="grid gap-1 text-xs text-slate-400">
              Destination
              <select
                value={destination}
                onChange={(event) => setDestination(event.target.value as RouteDestination)}
                className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
              >
                {ROUTE_DESTINATIONS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid gap-2 sm:grid-cols-2">
              <label className="grid gap-1 text-xs text-slate-400">
                Interaction
                <select
                  value={interactionKind}
                  onChange={(event) =>
                    setInteractionKind(event.target.value as ComponentInteractionKind)
                  }
                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
                >
                  {INTERACTION_KINDS.map((kind) => (
                    <option key={kind} value={kind}>
                      {kind.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>

              <label className="grid gap-1 text-xs text-slate-400">
                Sender profile
                <select
                  value={attackerProfile}
                  onChange={(event) =>
                    setAttackerProfile(event.target.value as AttackerProfile)
                  }
                  className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
                >
                  {ATTACKER_PROFILES.map((profile) => (
                    <option key={profile} value={profile}>
                      {profile.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <textarea
              value={payloadText}
              onChange={(event) => setPayloadText(event.target.value)}
              maxLength={4096}
              className="min-h-32 resize-y rounded-md border border-slate-700 bg-slate-900 p-3 text-sm text-slate-100"
              placeholder="Demo-safe route input"
            />

            <button
              type="button"
              disabled={!sessionId || interaction.isPending}
              onClick={submit}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-sky-500 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send size={16} aria-hidden />
              Send To Route
            </button>
          </div>

          {interaction.error instanceof Error ? (
            <div className="mt-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-100">
              {describeError(interaction.error)}
            </div>
          ) : null}
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

function RouteEdges() {
  return (
    <svg
      viewBox="0 0 940 520"
      className="pointer-events-none absolute inset-0 h-full w-full"
      aria-hidden
    >
      {EDGES.map((edge) => {
        const from = NODE_POSITIONS[edge.from];
        const to = NODE_POSITIONS[edge.to];
        const labelX = (from.x + to.x) / 2;
        const labelY = (from.y + to.y) / 2;
        return (
          <g key={`${edge.from}-${edge.to}`}>
            <line
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="rgb(51 65 85)"
              strokeWidth={2}
              strokeDasharray="6 8"
            />
            <rect
              x={labelX - 34}
              y={labelY - 10}
              width={68}
              height={20}
              rx={6}
              fill="rgb(2 6 23)"
              stroke="rgb(30 41 59)"
            />
            <text
              x={labelX}
              y={labelY + 4}
              textAnchor="middle"
              fill="rgb(148 163 184)"
              fontSize={10}
            >
              {edge.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function RouteNode({
  node,
  providerHealth,
  selected,
  onSelect,
}: {
  node: RouteNodeState;
  providerHealth: ProviderHealthSnapshot | null;
  selected: boolean;
  onSelect: () => void;
}) {
  const position = NODE_POSITIONS[node.domain];
  const credentialState = providerHealth?.gemini_api_key_present || providerHealth?.openrouter_api_key_present;
  const lastStatus = node.lastResult?.status ?? node.status;
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{
        left: position.x - NODE_SIZE.width / 2,
        top: position.y - NODE_SIZE.height / 2,
        width: NODE_SIZE.width,
        height: NODE_SIZE.height,
      }}
      className={`absolute flex flex-col rounded-lg border bg-slate-950 p-3 text-left shadow-xl transition hover:border-sky-400/70 ${
        selected ? "border-sky-400 ring-2 ring-sky-400/30" : "border-slate-800"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-white">{trustDomainLabel(node.domain)}</div>
          <div className="mt-0.5 text-[11px] text-slate-500">local route instance</div>
        </div>
        <StatusPill status={lastStatus} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-1.5 text-[11px]">
        <RouteStateDot label="LT" active={Boolean(providerHealth?.lobster_trap_configured)} />
        <RouteStateDot label="Proxy" active={Boolean(providerHealth?.litellm_configured)} />
        <RouteStateDot label="Key" active={Boolean(credentialState)} />
        <RouteStateDot label="IO" active={Boolean(node.lastResult)} />
      </div>
      <div className="mt-auto truncate rounded-md bg-slate-900 px-2 py-1 text-[11px] text-slate-400">
        {node.lastResult?.reason ?? "No route input yet"}
      </div>
    </button>
  );
}

function RouteStateDot({ label, active }: { label: string; active: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-1.5 py-1 text-slate-300">
      <span
        className={`h-2 w-2 rounded-full ${active ? "bg-emerald-400" : "bg-slate-600"}`}
        aria-hidden
      />
      {label}
    </span>
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
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Selected Route State</h2>
          <p className="mt-1 text-xs text-slate-500">
            {trustDomainLabel(domain)} to {destination.label}
          </p>
        </div>
        <StatusPill status={lastResult?.status ?? readinessStatus} />
      </div>

      <dl className="mt-4 grid gap-2 text-sm">
        <StateRow name="Destination" value={destination.detail} />
        <StateRow name="Readiness" value={readinessDetail} status={readinessStatus} />
        <StateRow
          name="Last result"
          value={lastResult?.reason ?? "No interaction recorded for this instance"}
          status={lastResult?.status}
          blockedBy={lastResult?.blocked_by ?? undefined}
        />
      </dl>
      {providerHealth ? (
        <div className="mt-4">
          <ModelRoutePanel
            providerHealth={providerHealth}
            trustDomainLabel={trustDomainLabel(domain)}
            lastResult={lastResult?.reason}
          />
        </div>
      ) : null}
    </section>
  );
}

function StateRow({
  name,
  value,
  status,
  blockedBy,
}: {
  name: string;
  value: string;
  status?: SnapshotStatus;
  blockedBy?: ComponentInteractionResult["blocked_by"];
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900 p-2">
      <dt className="text-[11px] uppercase text-slate-500">{name}</dt>
      <dd className="mt-1 flex flex-wrap items-center gap-2 text-slate-200">
        <span>{value}</span>
        {status ? <StatusPill status={status} /> : null}
        {blockedBy ? <StatusPill layer={blockedBy} /> : null}
      </dd>
    </div>
  );
}
