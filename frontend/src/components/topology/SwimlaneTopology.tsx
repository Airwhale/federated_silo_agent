import type { ComponentId } from "../../api/types";
import { TRUST_INSTANCES, type TrustDomain } from "../../domain/instances";
import { TrustDomainColumn } from "./TrustDomainColumn";

type Props = {
  sessionId: string | null;
  onSelect: (componentId: ComponentId, instanceId: TrustDomain) => void;
};

export function SwimlaneTopology({ sessionId, onSelect }: Props) {
  return (
    <section className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/70 p-3 scrollbar-thin">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-white">Topology</h2>
        <p className="mt-1 text-xs text-slate-500">
          Input: click any tile to inspect it. Output: drawer shows that component's state.
        </p>
      </div>
      <div className="grid min-w-[1320px] grid-cols-5 gap-3">
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
