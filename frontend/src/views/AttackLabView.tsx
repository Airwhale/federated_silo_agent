import { ProbeForm } from "@/components/attack/ProbeForm";
import { PROBES } from "@/components/attack/ProbeRegistry";

export function AttackLabView() {
  return (
    <div className="flex flex-col gap-3">
      <section className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Attack lab
          </h2>
          <span className="text-[11px] text-slate-500">
            {PROBES.length} probes &middot; each enters via the same control API as a normal request
          </span>
        </div>
      </section>
      <div className="grid gap-3 xl:grid-cols-2">
        {PROBES.map((probe) => (
          <ProbeForm key={probe.probeKind} config={probe} />
        ))}
      </div>
    </div>
  );
}
