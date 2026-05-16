import type { ComponentId } from "../../api/types";
import type { TrustDomain, TrustInstance, TrustTier } from "../../domain/instances";
import { InstanceTile } from "./InstanceTile";

type Props = {
  sessionId: string | null;
  instance: TrustInstance;
  onSelect: (componentId: ComponentId, instanceId: TrustDomain) => void;
};

/**
 * Tier-driven accent palette. Restrained intentionally -- the federation
 * column gets the strongest emerald accent because the demo's whole
 * story is "federation enables cross-bank inference"; investigator is
 * neutral slate (it's outside the TEE perimeter); bank silos share a
 * sky-tinted accent that groups them visually as "the three silos the
 * federation talks to."
 */
const TIER_CLASSES: Record<TrustTier, {
  border: string;
  accentBar: string;
  label: string;
  tierLabel: string;
}> = {
  investigator: {
    border: "border-slate-800",
    accentBar: "bg-slate-500/60",
    label: "text-slate-100",
    tierLabel: "text-slate-400",
  },
  federation: {
    border: "border-emerald-500/30",
    accentBar: "bg-emerald-400/80",
    label: "text-emerald-100",
    tierLabel: "text-emerald-300",
  },
  silo: {
    border: "border-sky-500/20",
    accentBar: "bg-sky-400/80",
    label: "text-sky-100",
    tierLabel: "text-sky-300",
  },
};

export function TrustDomainColumn({ sessionId, instance, onSelect }: Props) {
  const agents = instance.mechanisms.filter((mechanism) => mechanism.kind === "agent");
  const mechanisms = instance.mechanisms.filter((mechanism) => mechanism.kind !== "agent");
  const tone = TIER_CLASSES[instance.tier];

  return (
    <section
      className={`flex min-w-[245px] flex-1 flex-col rounded-md border ${tone.border} bg-slate-900/40`}
    >
      {/*
        Top accent bar reads as a colored ribbon -- subtle but enough to
        let a viewer's eye group columns by tier without reading any
        labels. ~2px tall, no rounded corners on the bottom edge so it
        sits flush against the column body.
      */}
      <div aria-hidden className={`h-0.5 w-full rounded-t-md ${tone.accentBar}`} />
      <header className="flex items-baseline justify-between gap-2 px-2.5 py-2">
        <div className="flex min-w-0 items-baseline gap-1.5">
          <h2 className={`truncate text-xs font-semibold ${tone.label}`}>
            {instance.label}
          </h2>
          <span className={`text-[10px] uppercase tracking-wide ${tone.tierLabel}`}>
            {instance.subtitle}
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-wide text-slate-500">
          {instance.id}
        </span>
      </header>

      <div className="flex flex-col gap-0.5 px-2 pb-1">
        <SectionLabel>Agents</SectionLabel>
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

      <div className="flex flex-col gap-0.5 border-t border-slate-800/70 px-2 pb-2 pt-1">
        <SectionLabel>Mechanisms</SectionLabel>
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

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-1 pt-0.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
      {children}
    </p>
  );
}
