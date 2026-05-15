import { useMemo, useState } from "react";
import { useTimeline } from "../api/hooks";
import type { ComponentId } from "../api/types";
import { TRUST_INSTANCES, type TrustDomain } from "../domain/instances";
import { FilterBar, type TimelineFilters } from "./FilterBar";
import { TimelineEventRow } from "./TimelineEventRow";

type Props = {
  sessionId: string | null;
  onSelect: (componentId: ComponentId, instanceId?: TrustDomain) => void;
};

const initialFilters: TimelineFilters = {
  instanceId: "all",
  componentId: "all",
  status: "all",
  layer: "all",
  text: "",
};

function instanceForComponent(componentId: ComponentId): TrustDomain | undefined {
  return TRUST_INSTANCES.find((instance) =>
    instance.mechanisms.some((mechanism) => mechanism.componentId === componentId),
  )?.id;
}

export function Timeline({ sessionId, onSelect }: Props) {
  const timeline = useTimeline(sessionId);
  const [filters, setFilters] = useState(initialFilters);

  const events = useMemo(() => {
    const text = filters.text.trim().toLowerCase();
    return (timeline.data ?? []).filter((event) => {
      const instanceId = instanceForComponent(event.component_id);
      return (
        (filters.instanceId === "all" || filters.instanceId === instanceId) &&
        (filters.componentId === "all" || filters.componentId === event.component_id) &&
        (filters.status === "all" || filters.status === event.status) &&
        (filters.layer === "all" || filters.layer === event.blocked_by) &&
        (!text ||
          event.title.toLowerCase().includes(text) ||
          event.detail.toLowerCase().includes(text))
      );
    });
  }, [filters, timeline.data]);

  return (
    <section className="flex min-h-[520px] flex-col gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div>
        <h2 className="text-sm font-semibold text-white">Timeline</h2>
        <p className="mt-1 text-xs text-slate-500">
          Input: filters narrow events. Output: rows show state changes and blocks.
        </p>
        <p className="mt-1 text-xs text-slate-500">{events.length} visible events</p>
      </div>
      <FilterBar filters={filters} onChange={setFilters} />
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto pr-1 scrollbar-thin">
        {events.map((event) => (
          <TimelineEventRow
            key={event.event_id}
            event={event}
            onSelect={() => onSelect(event.component_id, instanceForComponent(event.component_id))}
          />
        ))}
        {events.length === 0 ? (
          <div className="rounded-md border border-slate-800 p-4 text-sm text-slate-500">
            No timeline events match the current filters.
          </div>
        ) : null}
      </div>
    </section>
  );
}
