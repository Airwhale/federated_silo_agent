import type { ComponentId } from "../../api/types";
import { TRUST_INSTANCES, type TrustDomain } from "../../domain/instances";
import { TrustDomainColumn } from "./TrustDomainColumn";

type Props = {
  sessionId: string | null;
  onSelect: (componentId: ComponentId, instanceId: TrustDomain) => void;
};

/**
 * Five-column swimlane that is the demo's primary "what is happening"
 * surface. Columns are tier-styled so a judge can read the story
 * left-to-right without explanation: a single investigator runs outside
 * the TEE perimeter, the federation coordinator sits inside the TEE
 * (emerald-accented to signal trust boundary), and three bank silos
 * carry the local transaction data the federation never sees in raw
 * form. The "ring crosses banks" narrative is visible as the
 * left-to-right grouping of the silo columns.
 */
export function SwimlaneTopology({ sessionId, onSelect }: Props) {
  return (
    <section className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/70 scrollbar-thin">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-slate-800 px-3 py-2">
        <div className="flex items-baseline gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Topology
          </h2>
          <span className="text-[11px] text-slate-500">
            5 trust domains &middot; click a tile to inspect
          </span>
        </div>
        <TierLegend />
      </header>
      <div className="grid min-w-[1320px] grid-cols-5 gap-2 p-2">
        {TRUST_INSTANCES.map((instance) => (
          <TrustDomainColumn
            key={instance.id}
            sessionId={sessionId}
            instance={instance}
            onSelect={onSelect}
          />
        ))}
      </div>
    </section>
  );
}

/**
 * Inline legend explaining the column-accent vocabulary. Tiny, restrained,
 * but enough to anchor a first-time viewer's read of the topology.
 * Lives next to the section header so it's adjacent to the thing it
 * explains.
 */
function TierLegend() {
  return (
    <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] uppercase tracking-wide text-slate-500">
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="h-2 w-2 rounded-sm bg-slate-500/60" />
        Outside TEE
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="h-2 w-2 rounded-sm bg-emerald-400/80" />
        Federation (TEE)
      </li>
      <li className="flex items-center gap-1.5">
        <span aria-hidden className="h-2 w-2 rounded-sm bg-sky-400/80" />
        Bank silo
      </li>
    </ul>
  );
}
