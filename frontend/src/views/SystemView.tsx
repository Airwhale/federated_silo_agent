import { useHealth, useSystem } from "@/api/hooks";
import { ProviderHealthPanel } from "@/components/inspector/ProviderHealthPanel";
import { StatusPill } from "@/components/StatusPill";

export function SystemView() {
  const health = useHealth();
  const system = useSystem();

  return (
    <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-4">
        <h2 className="text-sm font-semibold text-white">Backend</h2>
        <div className="mt-3 flex items-center gap-2">
          <StatusPill status={health.data?.status === "ok" ? "live" : "pending"} />
          <span className="text-sm text-slate-400">{health.data?.status ?? "checking"}</span>
        </div>
        {system.data?.provider_health ? (
          <div className="mt-4">
            <ProviderHealthPanel providerHealth={system.data.provider_health} />
          </div>
        ) : null}
      </section>
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-4">
        <h2 className="text-sm font-semibold text-white">Readiness</h2>
        <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {(system.data?.components ?? []).map((component) => (
            <div key={component.component_id} className="rounded-md border border-slate-800 bg-slate-900 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-white">{component.label}</span>
                <StatusPill status={component.status} />
              </div>
              <p className="mt-2 text-xs text-slate-400">{component.detail}</p>
              {component.available_after ? (
                <p className="mt-2 text-xs text-slate-500">Available after {component.available_after}</p>
              ) : null}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
