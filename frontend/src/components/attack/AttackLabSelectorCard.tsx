import { useMemo, useState } from "react";
import type { ProbeKind } from "@/api/types";
import { FieldLabel } from "@/components/forms/FieldLabel";
import { StatusPill } from "@/components/StatusPill";
import { ProbeForm } from "./ProbeForm";
import { PROBES } from "./ProbeRegistry";

type Props = {
  description?: string;
  probeKinds?: ProbeKind[];
  title?: string;
};

export function AttackLabSelectorCard({
  description = "Pick one attack category, then run the matching probe through the same backend controls used by the demo.",
  probeKinds,
  title = "Security probes",
}: Props) {
  const visibleProbes = useMemo(
    () => (probeKinds ? PROBES.filter((probe) => probeKinds.includes(probe.probeKind)) : PROBES),
    [probeKinds],
  );
  const [selectedProbeKind, setSelectedProbeKind] = useState(visibleProbes[0]?.probeKind);
  const selectedProbe = useMemo(
    () => visibleProbes.find((probe) => probe.probeKind === selectedProbeKind) ?? visibleProbes[0],
    [selectedProbeKind, visibleProbes],
  );

  if (!selectedProbe) {
    return null;
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800/70 px-3 py-2">
        <div className="min-w-0">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            {title}
          </h2>
          <p className="mt-1 max-w-4xl text-[11px] leading-5 text-slate-400">
            {description}
          </p>
        </div>
        <div className="w-full min-w-[14rem] sm:w-72">
          <FieldLabel label="Attack category">
            <select
              value={selectedProbe.probeKind}
              onChange={(event) => setSelectedProbeKind(event.target.value as typeof selectedProbe.probeKind)}
              className="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
            >
              {visibleProbes.map((probe) => (
                <option key={probe.probeKind} value={probe.probeKind}>
                  {probe.label}
                </option>
              ))}
            </select>
          </FieldLabel>
        </div>
      </header>

      <div className="grid gap-3 p-3 xl:grid-cols-[18rem_minmax(0,1fr)]">
        <aside className="rounded border border-slate-800 bg-slate-900/40 p-3 text-[11px] leading-5 text-slate-400">
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <StatusPill label={selectedProbe.expectedLayer} />
            {selectedProbe.availableAfter ? (
              <StatusPill status="not_built" label={selectedProbe.availableAfter} />
            ) : null}
          </div>
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            What this tests
          </div>
          <p className="mt-1 text-slate-300">{selectedProbe.summary}</p>
          <div className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Expected block layer
          </div>
          <p className="mt-1 text-slate-300">
            {selectedProbe.stageLabel}: {selectedProbe.stageDescription}
          </p>
        </aside>
        <ProbeForm key={selectedProbe.probeKind} config={selectedProbe} />
      </div>
    </section>
  );
}
