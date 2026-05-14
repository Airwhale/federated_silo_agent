import { PROBE_REGISTRY } from "@/components/attack/ProbeRegistry";
import { ProbeForm } from "@/components/attack/ProbeForm";
import { RunControls } from "@/components/RunControls";

export function AttackLabView() {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <RunControls />
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <header className="mb-3 flex flex-col gap-1">
          <h2 className="text-base font-semibold text-slate-100">Attack lab</h2>
          <p className="text-xs text-slate-400">
            Each probe enters through the same signed-envelope / allowlist /
            replay / route-approval / P7-budget gates a real attacker would
            face. Probes target a specific trust-domain instance; results
            attach to that instance on the timeline.
          </p>
        </header>
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {PROBE_REGISTRY.map((config) => (
            <ProbeForm key={config.kind} config={config} />
          ))}
        </div>
      </div>
    </div>
  );
}
