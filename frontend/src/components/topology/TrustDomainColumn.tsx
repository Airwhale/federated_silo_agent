import type { InstanceSpec } from "@/domain/instances";

import { InstanceTile } from "./InstanceTile";

interface Props {
  spec: InstanceSpec;
}

export function TrustDomainColumn({ spec }: Props) {
  return (
    <section className="flex min-w-[12rem] flex-1 flex-col gap-2 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <header className="mb-1 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-slate-100">{spec.label}</h2>
        <span className="font-mono text-[10px] uppercase tracking-wide text-slate-500">
          {spec.id}
        </span>
      </header>

      <div className="flex flex-col gap-1">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">Agents</p>
        {spec.agents.map((id) => (
          <InstanceTile key={`${spec.id}:agent:${id}`} componentId={id} domain={spec.id} />
        ))}
      </div>

      <div className="mt-2 flex flex-col gap-1">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">Mechanisms</p>
        {spec.mechanisms.map((id) => (
          <InstanceTile
            key={`${spec.id}:mech:${id}`}
            componentId={id}
            domain={spec.id}
          />
        ))}
      </div>
    </section>
  );
}
