import type { ComponentId } from "../../api/types";
import type { TrustDomain, TrustInstance } from "../../domain/instances";
import { InstanceTile } from "./InstanceTile";

type Props = {
  sessionId: string | null;
  instance: TrustInstance;
  onSelect: (componentId: ComponentId, instanceId: TrustDomain) => void;
};

export function TrustDomainColumn({ sessionId, instance, onSelect }: Props) {
  const agents = instance.mechanisms.filter((mechanism) => mechanism.kind === "agent");
  const mechanisms = instance.mechanisms.filter((mechanism) => mechanism.kind !== "agent");

  return (
    <section className="flex min-w-[245px] flex-1 flex-col gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-white">{instance.label}</h2>
          <span className="font-mono text-[10px] uppercase tracking-wide text-slate-500">
            {instance.id}
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500">{instance.subtitle}</p>
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">Agents</p>
        {agents.map((mechanism) => (
          <InstanceTile
            key={`${instance.id}-${mechanism.id}`}
            sessionId={sessionId}
            instanceId={instance.id}
            componentId={mechanism.componentId}
            label={mechanism.label}
            kind={mechanism.kind}
            onSelect={onSelect}
          />
        ))}
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-[10px] uppercase tracking-wide text-slate-500">Mechanisms</p>
        {mechanisms.map((mechanism) => (
          <InstanceTile
            key={`${instance.id}-${mechanism.id}`}
            sessionId={sessionId}
            instanceId={instance.id}
            componentId={mechanism.componentId}
            label={mechanism.label}
            kind={mechanism.kind}
            onSelect={onSelect}
          />
        ))}
      </div>
    </section>
  );
}
