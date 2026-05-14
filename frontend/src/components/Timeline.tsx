import { useMemo, useState } from "react";

import { useTimeline } from "@/api/hooks";
import { describeError } from "@/api/errors";
import type {
  ComponentId,
  SecurityLayer,
  SnapshotStatus,
  TimelineEventSnapshot,
} from "@/api/types";
import { INSTANCES, type TrustDomain } from "@/domain/instances";

import { TimelineEventRow } from "./TimelineEventRow";
import { useSessionContext } from "./SessionContext";

interface Filters {
  domain: TrustDomain | "all";
  status: SnapshotStatus | "all";
  layer: SecurityLayer | "all";
}

function domainOf(componentId: ComponentId): TrustDomain {
  for (const spec of INSTANCES) {
    if (
      spec.agents.includes(componentId) ||
      spec.mechanisms.includes(componentId)
    ) {
      return spec.id;
    }
  }
  // Mechanism singletons land in federation today (a reasonable default for
  // global "envelope"/"signing"/"replay" until P15 splits per-instance).
  return "federation";
}

function applyFilters(
  events: TimelineEventSnapshot[],
  filters: Filters,
): TimelineEventSnapshot[] {
  return events.filter((e) => {
    if (filters.status !== "all" && e.status !== filters.status) return false;
    if (filters.layer !== "all" && e.blocked_by !== filters.layer) return false;
    if (filters.domain !== "all" && domainOf(e.component_id) !== filters.domain) {
      return false;
    }
    return true;
  });
}

export function Timeline() {
  const { sessionId } = useSessionContext();
  const query = useTimeline(sessionId);
  const [filters, setFilters] = useState<Filters>({
    domain: "all",
    status: "all",
    layer: "all",
  });

  const filtered = useMemo(
    () => (query.data ? applyFilters(query.data, filters) : []),
    [query.data, filters],
  );

  return (
    <section className="flex h-full flex-col border-l border-slate-800 bg-slate-950/40">
      <header className="flex flex-col gap-2 border-b border-slate-800 px-3 py-2">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-slate-100">Timeline</h2>
          <span className="text-[11px] text-slate-500">
            {query.data?.length ?? 0} events · {filtered.length} shown
          </span>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <FilterSelect
            label="Domain"
            value={filters.domain}
            onChange={(v) => setFilters((f) => ({ ...f, domain: v as Filters["domain"] }))}
            options={[
              { value: "all", label: "all" },
              ...INSTANCES.map((s) => ({ value: s.id, label: s.shortLabel })),
            ]}
          />
          <FilterSelect
            label="Status"
            value={filters.status}
            onChange={(v) => setFilters((f) => ({ ...f, status: v as Filters["status"] }))}
            options={[
              { value: "all", label: "all" },
              { value: "live", label: "live" },
              { value: "blocked", label: "blocked" },
              { value: "pending", label: "pending" },
              { value: "not_built", label: "not_built" },
              { value: "simulated", label: "simulated" },
              { value: "error", label: "error" },
            ]}
          />
          <FilterSelect
            label="Layer"
            value={filters.layer}
            onChange={(v) => setFilters((f) => ({ ...f, layer: v as Filters["layer"] }))}
            options={[
              { value: "all", label: "all" },
              { value: "signature", label: "signature" },
              { value: "allowlist", label: "allowlist" },
              { value: "replay", label: "replay" },
              { value: "route_approval", label: "route_approval" },
              { value: "lobster_trap", label: "lobster_trap" },
              { value: "a3_policy", label: "a3_policy" },
              { value: "p7_budget", label: "p7_budget" },
              { value: "not_built", label: "not_built" },
              { value: "accepted", label: "accepted" },
              { value: "internal_error", label: "internal_error" },
            ]}
          />
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!sessionId ? (
          <EmptyState>
            No session yet. Use <strong>Create session</strong> to start one.
          </EmptyState>
        ) : query.isLoading ? (
          <EmptyState>Loading timeline…</EmptyState>
        ) : query.error ? (
          <EmptyState tone="error">
            Could not load timeline — {describeError(query.error)}
          </EmptyState>
        ) : filtered.length === 0 ? (
          <EmptyState>No matching events.</EmptyState>
        ) : (
          <ol className="divide-y divide-slate-800">
            {filtered
              .slice()
              .reverse()
              .map((event) => (
                <TimelineEventRow key={event.event_id} event={event} />
              ))}
          </ol>
        )}
      </div>
    </section>
  );
}

interface FilterSelectProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}

function FilterSelect({ label, value, onChange, options }: FilterSelectProps) {
  return (
    <label className="flex items-center gap-1 text-slate-300">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-100"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function EmptyState({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone?: "error";
}) {
  return (
    <p
      className={
        "px-3 py-6 text-center text-xs " +
        (tone === "error" ? "text-rose-300" : "text-slate-500")
      }
    >
      {children}
    </p>
  );
}
