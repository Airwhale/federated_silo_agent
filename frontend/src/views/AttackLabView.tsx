import { ProbeForm } from "@/components/attack/ProbeForm";
import { PROBES } from "@/components/attack/ProbeRegistry";

export function AttackLabView() {
  return (
    <div className="grid gap-4">
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-4">
        <h2 className="text-sm font-semibold text-white">Attack Lab</h2>
        <p className="mt-1 max-w-4xl text-sm text-slate-400">
          Every probe enters through the same P9a control API and records a
          typed timeline result. Built probes exercise real security paths;
          future probes return explicit not-built placeholders.
        </p>
        <p className="mt-1 max-w-4xl text-xs text-slate-500">
          Input: each card picks target, component, profile, and optional payload. Output: result shows blocked layer and evidence.
        </p>
      </section>
      <div className="grid gap-4 xl:grid-cols-2">
        {PROBES.map((probe) => (
          <ProbeForm key={probe.probeKind} config={probe} />
        ))}
      </div>
    </div>
  );
}
