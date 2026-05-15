import { describeError } from "@/api/errors";
import { useHealth, useSystem } from "@/api/hooks";
import type { ComponentReadinessSnapshot } from "@/api/types";
import { ModelRoutePanel } from "@/components/inspector/ModelRoutePanel";
import { StatusPill } from "@/components/StatusPill";
import { componentLabel } from "@/domain/instances";

export function SystemView() {
  const health = useHealth();
  const system = useSystem();

  return (
    <div className="grid gap-3 xl:grid-cols-[360px_minmax(0,1fr)]">
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-white">Backend</h2>
          <StatusPill status={health.data?.status === "ok" ? "live" : "pending"} />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {health.data?.status === "ok" ? "Control API is reachable." : "Checking API health."}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Output: backend reachability and provider route configuration.
        </p>
        {system.error ? (
          <p className="mt-3 text-xs text-rose-300">{describeError(system.error)}</p>
        ) : null}
        {system.data?.provider_health ? (
          <div className="mt-4">
            <ModelRoutePanel providerHealth={system.data.provider_health} />
          </div>
        ) : null}
      </section>

      <section className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-white">System Readiness</h2>
            <p className="mt-1 text-xs text-slate-500">
              {system.data?.detail ?? "Loading system snapshot."}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Output: every component, status, milestone, and readiness detail.
            </p>
          </div>
          {system.data ? <StatusPill status={system.data.status} /> : null}
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-xs">
            <thead className="border-b border-slate-800 text-[10px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-2 pr-3 text-left font-medium">Component</th>
                <th className="py-2 pr-3 text-left font-medium">ID</th>
                <th className="py-2 pr-3 text-left font-medium">Status</th>
                <th className="py-2 pr-3 text-left font-medium">Available after</th>
                <th className="py-2 text-left font-medium">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {(system.data?.components ?? []).map((component) => (
                <ReadinessRow key={component.component_id} component={component} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function ReadinessRow({ component }: { component: ComponentReadinessSnapshot }) {
  return (
    <tr className="align-top">
      <td className="py-2 pr-3 font-medium text-slate-100">
        {componentLabel(component.component_id)}
      </td>
      <td className="py-2 pr-3 font-mono text-[11px] text-slate-500">
        {component.component_id}
      </td>
      <td className="py-2 pr-3">
        <StatusPill status={component.status} />
      </td>
      <td className="py-2 pr-3 text-slate-400">
        {component.available_after ?? "none"}
      </td>
      <td className="py-2 text-slate-400">{component.detail}</td>
    </tr>
  );
}
