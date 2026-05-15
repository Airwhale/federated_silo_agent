import { useSystem } from "@/api/hooks";
import { describeError } from "@/api/errors";
import type { ProviderHealthSnapshot } from "@/api/types";
import { useSessionContext } from "@/components/SessionContext";
import { INSTANCES, type TrustDomain } from "@/domain/instances";
import { TRUST_DOMAIN_LABELS } from "@/lib/trustDomainLabels";

/**
 * LLM route topology — hub-and-spoke view of the five trust-domain
 * model routes. Per-domain provider/key data lands with P14; today
 * every node mirrors the global `provider_health` snapshot, with each
 * status pip showing one redacted-presence check.
 *
 * Visual:
 *   investigator ---- federation ---- bank_alpha
 *                          |    \---- bank_beta
 *                          |    \---- bank_gamma
 *
 * Each node is a small circle with the trust-domain abbreviation +
 * four status pips (route / Gemini / OpenRouter / secrets-redacted).
 * The legend on the right explains what the pips mean. Clicking a
 * node opens the inspector drawer on that trust domain's `litellm`
 * component.
 */

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
  bank_alpha: "α",
  bank_beta: "β",
  bank_gamma: "γ",
};

const EDGES: { from: TrustDomain; to: TrustDomain }[] = [
  { from: "investigator", to: "federation" },
  { from: "federation", to: "bank_alpha" },
  { from: "federation", to: "bank_beta" },
  { from: "federation", to: "bank_gamma" },
];

interface PipSpec {
  key: keyof ProviderHealthSnapshot;
  label: string;
  short: string;
}

const PIPS: PipSpec[] = [
  { key: "litellm_configured", label: "Route configured", short: "R" },
  { key: "gemini_api_key_present", label: "Gemini key present", short: "G" },
  { key: "openrouter_api_key_present", label: "OpenRouter key present", short: "O" },
  { key: "lobster_trap_configured", label: "Lobster Trap configured", short: "L" },
];

const NODE_RADIUS = 34;
const PIP_RADIUS = 5;

export function LlmRouteView() {
  const query = useSystem();
  const { setSelection } = useSessionContext();

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="border-b border-slate-800 px-4 py-3">
        <h2 className="text-base font-semibold text-slate-100">LLM routes</h2>
        <p className="mt-0.5 text-xs text-slate-400">
          One model route per trust domain (today: shared snapshot via
          P9a; P14 supplies per-domain provider / model / structured-output
          schema). Click a node to inspect.
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {query.isLoading ? (
          <p className="text-xs text-slate-500">Loading system snapshot…</p>
        ) : query.error ? (
          <p className="text-xs text-rose-300">
            Could not load — {describeError(query.error)}
          </p>
        ) : query.data ? (
          <div className="flex flex-col gap-4 lg:flex-row">
            <RouteGraph
              provider={query.data.provider_health}
              onSelect={(domain) =>
                setSelection({ domain, componentId: "litellm" })
              }
            />
            <Legend provider={query.data.provider_health} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

interface RouteGraphProps {
  provider: ProviderHealthSnapshot;
  onSelect: (domain: TrustDomain) => void;
}

function RouteGraph({ provider, onSelect }: RouteGraphProps) {
  return (
    <div className="flex-1 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40">
      <svg
        viewBox="0 40 800 320"
        role="img"
        aria-label="LLM route topology: investigator and three bank silos around the federation hub"
        className="h-auto w-full"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Edges first so the nodes paint on top */}
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
              strokeDasharray="2 3"
            />
          );
        })}

        {INSTANCES.map((spec) => (
          <RouteNode
            key={spec.id}
            domain={spec.id}
            provider={provider}
            onSelect={() => onSelect(spec.id)}
          />
        ))}
      </svg>
    </div>
  );
}

interface RouteNodeProps {
  domain: TrustDomain;
  provider: ProviderHealthSnapshot;
  onSelect: () => void;
}

function RouteNode({ domain, provider, onSelect }: RouteNodeProps) {
  const { x, y } = NODE_POSITIONS[domain];
  const abbrev = NODE_ABBREV[domain];
  const label = TRUST_DOMAIN_LABELS[domain];

  return (
    <g
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className="cursor-pointer outline-none focus-visible:[&_circle]:stroke-emerald-400"
      aria-label={`Inspect ${label} LLM route`}
    >
      {/* Node circle */}
      <circle
        cx={x}
        cy={y}
        r={NODE_RADIUS}
        fill="rgb(15 23 42)"
        stroke="rgb(71 85 105)"
        strokeWidth={1.5}
        className="hover:stroke-emerald-400/70"
      />
      {/* Abbreviation in the center */}
      <text
        x={x}
        y={y + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill="rgb(226 232 240)"
        fontSize={abbrev.length === 1 ? 22 : 14}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
      >
        {abbrev}
      </text>
      {/* Small domain label under the node */}
      <text
        x={x}
        y={y + NODE_RADIUS + 14}
        textAnchor="middle"
        fill="rgb(148 163 184)"
        fontSize={10}
      >
        {label}
      </text>
      {/* Four status pips around the top arc, evenly spaced */}
      {PIPS.map((pip, idx) => {
        const angle = -Math.PI / 2 + (idx - 1.5) * 0.5;
        const px = x + Math.cos(angle) * (NODE_RADIUS + 4);
        const py = y + Math.sin(angle) * (NODE_RADIUS + 4);
        const on = Boolean(provider[pip.key]);
        return (
          <circle
            key={pip.short}
            cx={px}
            cy={py}
            r={PIP_RADIUS}
            fill={on ? "rgb(52 211 153)" : "rgb(51 65 85)"}
            stroke="rgb(15 23 42)"
            strokeWidth={1.5}
          >
            <title>
              {pip.label}: {on ? "yes" : "no"}
            </title>
          </circle>
        );
      })}
    </g>
  );
}

interface LegendProps {
  provider: ProviderHealthSnapshot;
}

function Legend({ provider }: LegendProps) {
  return (
    <aside className="w-full shrink-0 rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs lg:w-64">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Pip key
      </h3>
      <ul className="flex flex-col gap-1.5">
        {PIPS.map((pip) => {
          const on = Boolean(provider[pip.key]);
          return (
            <li key={pip.short} className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full ring-2 ring-slate-950"
                style={{ background: on ? "rgb(52 211 153)" : "rgb(51 65 85)" }}
                aria-hidden
              />
              <span className="font-mono text-[10px] text-slate-500">{pip.short}</span>
              <span className="text-slate-200">{pip.label}</span>
            </li>
          );
        })}
      </ul>

      <h3 className="mb-1 mt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Nodes
      </h3>
      <ul className="flex flex-col gap-1 text-[11px]">
        {INSTANCES.map((spec) => (
          <li key={spec.id} className="flex items-center gap-2 text-slate-300">
            <span className="inline-flex h-5 w-7 items-center justify-center rounded border border-slate-700 bg-slate-900 font-mono text-[11px] text-slate-200">
              {NODE_ABBREV[spec.id]}
            </span>
            {TRUST_DOMAIN_LABELS[spec.id]}
          </li>
        ))}
      </ul>

      <p className="mt-4 text-[10px] leading-relaxed text-slate-500">
        Pips are global today (one snapshot via P9a). P14 supplies
        per-domain route metadata so each node shows its own provider /
        model / last-request status.
      </p>
    </aside>
  );
}
