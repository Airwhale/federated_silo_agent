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
import { KeyValueGrid, type KeyValueRow } from "@/components/inspector/KeyValueGrid";
import { ModelRoutePanel } from "@/components/inspector/ModelRoutePanel";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";
import { TRUST_INSTANCES, trustDomainLabel, type TrustDomain } from "@/domain/instances";

type RouteDestination = Extract<ComponentId, "litellm" | "lobster_trap">;

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

// Compact hub-and-spoke layout: investigator -- federation -- 3 banks.
// Viewbox is small so the graph fits without forcing a horizontal
// scrollbar on narrow viewports, and the page can scroll the rest of
// the content vertically.
const NODE_POSITIONS: Record<TrustDomain, { x: number; y: number }> = {
  investigator: { x: 120, y: 200 },
  federation: { x: 400, y: 200 },
  bank_alpha: { x: 660, y: 90 },
  bank_beta: { x: 680, y: 200 },
  bank_gamma: { x: 660, y: 310 },
};

const NODE_ABBREV: Record<TrustDomain, string> = {
  investigator: "INV",
  federation: "FED",
  bank_alpha: "ALP",
  bank_beta: "BET",
  bank_gamma: "GAM",
};

const EDGES: { from: TrustDomain; to: TrustDomain }[] = [
  { from: "investigator", to: "federation" },
  { from: "federation", to: "bank_alpha" },
  { from: "federation", to: "bank_beta" },
  { from: "federation", to: "bank_gamma" },
];

// Pip semantics. Each pip is a small circle arched over a node; the
// legend on the side spells out what each one represents so we never
// repeat the names per-node.
type PipKey = "LT" | "Proxy" | "Key" | "IO";

interface PipSpec {
  key: PipKey;
  label: string;
  describe: (provider: ProviderHealthSnapshot | null, node: RouteNodeState) => boolean;
}

const PIPS: PipSpec[] = [
  {
    key: "LT",
    label: "Lobster Trap configured",
    describe: (p) => Boolean(p?.lobster_trap_configured),
  },
  {
    key: "Proxy",
    label: "LiteLLM proxy configured",
    describe: (p) => Boolean(p?.litellm_configured),
  },
  {
    key: "Key",
    label: "Provider key present (Gemini or OpenRouter)",
    describe: (p) =>
      Boolean(p?.gemini_api_key_present) || Boolean(p?.openrouter_api_key_present),
  },
  {
    key: "IO",
    label: "Last route I/O recorded for this instance",
    describe: (_p, node) => Boolean(node.lastResult),
  },
];

const NODE_RADIUS = 34;
const PIP_RADIUS = 5;

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
  const nodeStates = useMemo<RouteNodeState[]>(
    () =>
      TRUST_INSTANCES.map((instance) => ({
        domain: instance.id,
        status: readinessByComponent.get(destination)?.status ?? readinessFallback,
        lastResult: lastResults[resultKey(instance.id, destination)],
      })),
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
              Hub-and-spoke &middot; click a node to focus the input form
            </span>
          </div>
          <StatusPill status={providerHealth?.status ?? "pending"} />
        </header>

        <RouteGraph
          nodes={nodeStates}
          providerHealth={providerHealth}
          selectedDomain={selectedDomain}
          onSelect={(domain) => {
            setSelectedDomain(domain);
            setSelection({ componentId: destination, instanceId: domain });
          }}
        />

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
  nodes: RouteNodeState[];
  providerHealth: ProviderHealthSnapshot | null;
  selectedDomain: TrustDomain;
  onSelect: (domain: TrustDomain) => void;
}

function RouteGraph({ nodes, providerHealth, selectedDomain, onSelect }: RouteGraphProps) {
  return (
    <div className="overflow-x-auto px-3 py-2">
      <svg
        viewBox="40 40 740 320"
        role="img"
        aria-label="LLM route topology: investigator and three bank silos around the federation hub"
        className="h-auto w-full max-w-[820px]"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Edges first so the nodes paint on top. Dashed lines, label-less:
            the labels are documented in the legend, not repeated per edge. */}
        {EDGES.map((edge) => {
          const from = NODE_POSITIONS[edge.from];
          const to = NODE_POSITIONS[edge.to];
          return (
            <line
              key={`${edge.from}-${edge.to}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="rgb(51 65 85)"
              strokeWidth={1.5}
              strokeDasharray="3 4"
            />
          );
        })}

        {nodes.map((node) => (
          <RouteNode
            key={node.domain}
            node={node}
            providerHealth={providerHealth}
            selected={node.domain === selectedDomain}
            onSelect={() => onSelect(node.domain)}
          />
        ))}
      </svg>
    </div>
  );
}

interface RouteNodeProps {
  node: RouteNodeState;
  providerHealth: ProviderHealthSnapshot | null;
  selected: boolean;
  onSelect: () => void;
}

function RouteNode({ node, providerHealth, selected, onSelect }: RouteNodeProps) {
  const { x, y } = NODE_POSITIONS[node.domain];
  const abbrev = NODE_ABBREV[node.domain];
  const label = trustDomainLabel(node.domain);
  const lastStatus = node.lastResult?.status ?? node.status;

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
      aria-label={`Focus ${label} route input`}
    >
      <circle
        cx={x}
        cy={y}
        r={NODE_RADIUS}
        fill="rgb(15 23 42)"
        stroke={selected ? "rgb(56 189 248)" : "rgb(71 85 105)"}
        strokeWidth={selected ? 2.5 : 1.5}
        className="hover:stroke-emerald-400/70"
      />
      <text
        x={x}
        y={y + 2}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="rgb(226 232 240)"
        fontSize={abbrev.length === 1 ? 22 : 14}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
      >
        {abbrev}
      </text>
      <text
        x={x}
        y={y + NODE_RADIUS + 14}
        textAnchor="middle"
        fill="rgb(148 163 184)"
        fontSize={10}
      >
        {label}
      </text>
      <text
        x={x}
        y={y + NODE_RADIUS + 26}
        textAnchor="middle"
        fill="rgb(100 116 139)"
        fontSize={9}
      >
        {lastStatus}
      </text>
      {/* Four pips arched over the top of the circle, evenly spaced. */}
      {PIPS.map((pip, idx) => {
        const angle = -Math.PI / 2 + (idx - 1.5) * 0.5;
        const px = x + Math.cos(angle) * (NODE_RADIUS + 4);
        const py = y + Math.sin(angle) * (NODE_RADIUS + 4);
        const on = pip.describe(providerHealth, node);
        return (
          <circle
            key={pip.key}
            cx={px}
            cy={py}
            r={PIP_RADIUS}
            fill={on ? "rgb(52 211 153)" : "rgb(51 65 85)"}
            stroke="rgb(15 23 42)"
            strokeWidth={1.5}
          >
            <title>{`${pip.label}: ${on ? "yes" : "no"}`}</title>
          </circle>
        );
      })}
    </g>
  );
}

interface LegendProps {
  providerHealth: ProviderHealthSnapshot | null;
}

function Legend({ providerHealth }: LegendProps) {
  return (
    <div className="border-t border-slate-800/70 px-3 py-2 text-xs">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Pip key
          </h3>
          <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
            {PIPS.map((pip) => {
              // For LT / Proxy / Key, the legend shows current state at a
              // glance; for IO, the legend's pip is grey because IO is
              // per-instance, not global.
              const isGlobal = pip.key !== "IO";
              const on = isGlobal
                ? pip.describe(providerHealth, { domain: "federation", status: "live" })
                : false;
              return (
                <li key={pip.key} className="flex items-center gap-2">
                  <span
                    className="inline-block h-2 w-2 shrink-0 rounded-full"
                    style={{ background: on ? "rgb(52 211 153)" : "rgb(51 65 85)" }}
                    aria-hidden
                  />
                  <span className="font-mono text-[10px] text-slate-500">{pip.key}</span>
                  <span className="text-slate-300">{pip.label}</span>
                </li>
              );
            })}
          </ul>
        </div>
        <div>
          <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Nodes
          </h3>
          <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2 text-[11px]">
            {TRUST_INSTANCES.map((instance) => (
              <li key={instance.id} className="flex items-center gap-2 text-slate-300">
                <span className="inline-flex h-4 w-7 shrink-0 items-center justify-center rounded border border-slate-700 bg-slate-900 font-mono text-[10px] text-slate-200">
                  {NODE_ABBREV[instance.id]}
                </span>
                {instance.label}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="mt-2 text-[10px] text-slate-500">
        Pips reflect global provider configuration today; per-domain route
        metadata lands with P14.
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

function FieldLabel({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
      {children}
    </label>
  );
}
