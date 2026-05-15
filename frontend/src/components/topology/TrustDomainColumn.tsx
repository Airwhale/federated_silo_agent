import type { ComponentId } from "../../api/types";
import type { TrustDomain, TrustInstance } from "../../domain/instances";
import { InstanceTile } from "./InstanceTile";

type Props = {
  sessionId: string | null;
  instance: TrustInstance;
  onSelect: (componentId: ComponentId, instanceId: TrustDomain) => void;
};

export function TrustDomainColumn({ sessionId, instance, onSelect }: Props) {
  return (
    <section className="min-w-[245px] rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-white">{instance.label}</h2>
        <p className="mt-1 text-xs text-slate-500">{instance.subtitle}</p>
      </div>
      <div className="flex flex-col gap-2">
        {instance.mechanisms.map((mechanism) => (
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
