import { useSystem } from "@/api/hooks";
import { describeError } from "@/api/errors";
import type { ComponentReadinessSnapshot } from "@/api/types";
import { StatusPill } from "@/components/StatusPill";
import { labelFor } from "@/lib/componentLabels";

/**
 * Global readiness grid — a quick "is everything wired up?" view that
 * doesn't depend on an active session. Lists every component from
 * `GET /system` with its status pill + available_after milestone.
 */
export function SystemView() {
  const query = useSystem();

  return (
    <div className="flex h-full flex-col overflow-hidden p-4">
      <header className="mb-3 flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-slate-100">System readiness</h2>
        {query.data ? <StatusPill status={query.data.status} /> : null}
      </header>

      {query.isLoading ? (
        <p className="text-xs text-slate-500">Loading…</p>
      ) : query.error ? (
        <p className="text-xs text-rose-300">{describeError(query.error)}</p>
      ) : query.data ? (
        <>
          <p className="mb-3 text-xs text-slate-400">{query.data.detail}</p>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase tracking-wide text-slate-500">
                <tr className="border-b border-slate-800">
                  <th className="py-1 text-left font-medium">Component</th>
                  <th className="py-1 text-left font-medium">ID</th>
                  <th className="py-1 text-left font-medium">Status</th>
                  <th className="py-1 text-left font-medium">Available after</th>
                  <th className="py-1 text-left font-medium">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {query.data.components.map((row: ComponentReadinessSnapshot) => (
                  <tr key={row.component_id}>
                    <td className="py-1.5 text-slate-100">{labelFor(row.component_id)}</td>
                    <td className="py-1.5 font-mono text-[11px] text-slate-500">
                      {row.component_id}
                    </td>
                    <td className="py-1.5">
                      <StatusPill status={row.status} />
                    </td>
                    <td className="py-1.5 text-slate-400">{row.available_after ?? "—"}</td>
                    <td className="py-1.5 text-slate-400">{row.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
