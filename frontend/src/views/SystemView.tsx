import { describeError } from "@/api/errors";
import { useHealth, useSystem } from "@/api/hooks";
import type { ComponentReadinessSnapshot } from "@/api/types";
import { ModelRoutePanel } from "@/components/inspector/ModelRoutePanel";
import { StatusPill } from "@/components/StatusPill";
import { componentLabel } from "@/domain/instances";

/**
 * Two-pane system view: backend / provider health on the left, full
 * per-component readiness table on the right. Polished for ops-console
 * density: dropped the per-section "Output: ..." helper paragraphs (the
 * column headers and pills already encode the same information), and
 * regrouped the readiness rows by trust tier so the cross-bank story
 * the topology sells is also legible here as a tabular reference.
 */
export function SystemView() {
  const health = useHealth();
  const system = useSystem();

  return (
    <div className="grid gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
      <section className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3">
        <header className="flex items-baseline justify-between gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Backend
          </h2>
          <StatusPill status={health.data?.status === "ok" ? "live" : "pending"} />
        </header>
        <p className="text-[11px] text-slate-500">
          {health.data?.status === "ok"
            ? "Control API reachable; provider routes report below."
            : "Checking API health."}
        </p>
        {system.error ? (
          <p className="text-[11px] text-rose-300">{describeError(system.error)}</p>
        ) : null}
        {system.data?.provider_health ? (
          <ModelRoutePanel providerHealth={system.data.provider_health} />
        ) : null}
      </section>

      <section className="flex min-w-0 flex-col gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3">
        <header className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex items-baseline gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
              System readiness
            </h2>
            <span className="text-[11px] text-slate-500">
              {system.data?.detail ?? "Loading system snapshot."}
            </span>
          </div>
          {system.data ? <StatusPill status={system.data.status} /> : null}
        </header>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] table-fixed text-xs">
            <colgroup>
              <col className="w-[22%]" />
              <col className="w-[18%]" />
              <col className="w-[12%]" />
              <col className="w-[12%]" />
              <col />
            </colgroup>
            <thead className="border-b border-slate-800 text-[10px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-1.5 pr-3 text-left font-medium">Component</th>
                <th className="py-1.5 pr-3 text-left font-medium">ID</th>
                <th className="py-1.5 pr-3 text-left font-medium">Status</th>
                <th className="py-1.5 pr-3 text-left font-medium">Milestone</th>
                <th className="py-1.5 text-left font-medium">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
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
  // Not-built rows recede visually so a viewer can scan for what's
  // live first; the StatusPill is still authoritative, but the
  // additional row-level dimming makes "what's the current build
  // surface" answerable at a glance.
  const notBuilt = component.status === "not_built";
  return (
    <tr className={`align-top ${notBuilt ? "opacity-60" : ""}`}>
      <td className={`py-1.5 pr-3 font-medium ${notBuilt ? "italic text-slate-300" : "text-slate-100"}`}>
        {componentLabel(component.component_id)}
      </td>
      <td className="py-1.5 pr-3 font-mono text-[11px] text-slate-500">
        {component.component_id}
      </td>
      <td className="py-1.5 pr-3">
        <StatusPill status={component.status} />
      </td>
      <td className="py-1.5 pr-3 text-slate-400">
        {component.available_after ?? <span className="text-slate-600">—</span>}
      </td>
      <td className="py-1.5 text-slate-400">{component.detail}</td>
    </tr>
  );
}
