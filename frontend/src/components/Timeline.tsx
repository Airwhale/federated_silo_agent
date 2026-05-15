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

// Pre-computed component -> set-of-trust-domains index. Built once at
// module load so the per-event filter in the timeline (which fires on
// every re-render and every 2-second poll refresh) does an O(1) Map
// lookup instead of O(instances * mechanisms) of nested ``find``/``some``.
//
// Several mechanisms (``signing``, ``envelope``, ``replay``,
// ``lobster_trap``, ``litellm``, ``route_approval``) are shared across
// multiple trust domains in ``TRUST_INSTANCES``, so the index has to be
// a Set rather than a single TrustDomain. Using a plain ``Map<C, TD>``
// last-write-wins would silently mis-attribute every shared component
// to whichever domain appears last (today: ``bank_gamma``), breaking
// both filter and navigation for those rows. Backend will start
// emitting an instance-specific ``target_instance_id`` on each timeline
// event in P15; until then the UI treats shared components as belonging
// to all of their domains for filter purposes and picks an arbitrary
// representative for navigation (first match, matching the previous
// ``find``-based behavior).
const componentToInstances: ReadonlyMap<ComponentId, ReadonlySet<TrustDomain>> = (() => {
  const map = new Map<ComponentId, Set<TrustDomain>>();
  for (const instance of TRUST_INSTANCES) {
    for (const mechanism of instance.mechanisms) {
      const existing = map.get(mechanism.componentId);
      if (existing) {
        existing.add(instance.id);
      } else {
        map.set(mechanism.componentId, new Set([instance.id]));
      }
    }
  }
  return map;
})();

function eventMatchesInstanceFilter(
  componentId: ComponentId,
  filterDomain: TrustDomain | "all",
): boolean {
  if (filterDomain === "all") return true;
  return componentToInstances.get(componentId)?.has(filterDomain) ?? false;
}

function representativeInstance(componentId: ComponentId): TrustDomain | undefined {
  // Returns the first domain that owns the component (insertion order),
  // matching the previous ``TRUST_INSTANCES.find(...)`` semantics for
  // event-row click navigation. The drawer renders the same singleton
  // data for any of the domains a shared component belongs to, so the
  // "first" choice is a UX rather than correctness concern.
  const set = componentToInstances.get(componentId);
  if (!set) return undefined;
  return set.values().next().value;
}

export function Timeline({ sessionId, onSelect }: Props) {
  const timeline = useTimeline(sessionId);
  const [filters, setFilters] = useState(initialFilters);

  const events = useMemo(() => {
    const text = filters.text.trim().toLowerCase();
    return (timeline.data ?? []).filter((event) => {
      return (
        eventMatchesInstanceFilter(event.component_id, filters.instanceId) &&
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
            onSelect={() => onSelect(event.component_id, representativeInstance(event.component_id))}
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
