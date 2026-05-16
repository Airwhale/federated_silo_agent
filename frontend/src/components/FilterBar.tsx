import { Shuffle } from "lucide-react";
import type { ComponentId, SecurityLayer, SnapshotStatus } from "../api/types";
import { TRUST_INSTANCES, type TrustDomain } from "../domain/instances";
import { nextSample } from "../domain/sampleInputs";

export type TimelineFilters = {
  instanceId: TrustDomain | "all";
  componentId: ComponentId | "all";
  status: SnapshotStatus | "all";
  layer: SecurityLayer | "all";
  text: string;
};

type Props = {
  filters: TimelineFilters;
  onChange: (filters: TimelineFilters) => void;
};

const statuses: Array<SnapshotStatus | "all"> = [
  "all",
  "live",
  "blocked",
  "not_built",
  "pending",
  "simulated",
  "error",
];

const layers: Array<SecurityLayer | "all"> = [
  "all",
  "signature",
  "allowlist",
  "replay",
  "route_approval",
  "lobster_trap",
  "p7_budget",
  "not_built",
  "internal_error",
];

const components = Array.from(
  new Set(TRUST_INSTANCES.flatMap((item) => item.mechanisms.map((m) => m.componentId))),
);

const filterSamples = ["F2", "route", "blocked", "budget"];

export function FilterBar({ filters, onChange }: Props) {
  return (
    <div className="grid gap-2 md:grid-cols-5">
      <select
        value={filters.instanceId}
        onChange={(event) =>
          onChange({ ...filters, instanceId: event.target.value as TimelineFilters["instanceId"] })
        }
        className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
      >
        <option value="all">All domains</option>
        {TRUST_INSTANCES.map((instance) => (
          <option key={instance.id} value={instance.id}>
            {instance.label}
          </option>
        ))}
      </select>
      <select
        value={filters.componentId}
        onChange={(event) =>
          onChange({ ...filters, componentId: event.target.value as TimelineFilters["componentId"] })
        }
        className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
      >
        <option value="all">All components</option>
        {components.map((component) => (
          <option key={component} value={component}>
            {component}
          </option>
        ))}
      </select>
      <select
        value={filters.status}
        onChange={(event) =>
          onChange({ ...filters, status: event.target.value as TimelineFilters["status"] })
        }
        className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
      >
        {statuses.map((status) => (
          <option key={status} value={status}>
            {status.replaceAll("_", " ")}
          </option>
        ))}
      </select>
      <select
        value={filters.layer}
        onChange={(event) =>
          onChange({ ...filters, layer: event.target.value as TimelineFilters["layer"] })
        }
        className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
      >
        {layers.map((layer) => (
          <option key={layer} value={layer}>
            {layer.replaceAll("_", " ")}
          </option>
        ))}
      </select>
      <div className="flex gap-1">
        <input
          value={filters.text}
          onChange={(event) => onChange({ ...filters, text: event.target.value })}
          placeholder="Try: F2, route, blocked"
          className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
        />
        <button
          type="button"
          onClick={() => onChange({ ...filters, text: nextSample(filters.text, filterSamples) })}
          className="inline-flex items-center rounded-md border border-slate-700 bg-slate-900 px-2 text-slate-300 hover:bg-slate-800 hover:text-slate-100"
          title="Cycle sample filter text"
          aria-label="Cycle sample filter text"
        >
          <Shuffle size={13} aria-hidden />
        </button>
      </div>
    </div>
  );
}
