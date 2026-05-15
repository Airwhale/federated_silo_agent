import type { TimelineEventSnapshot } from "../api/types";
import { formatTime } from "../lib/time";
import { StatusPill } from "./StatusPill";

type Props = {
  event: TimelineEventSnapshot;
  onSelect: () => void;
};

export function TimelineEventRow({ event, onSelect }: Props) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full rounded-md border border-slate-800 bg-slate-900/80 p-3 text-left hover:border-sky-500/70"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-slate-500">{formatTime(event.timestamp)}</span>
        <div className="flex flex-wrap justify-end gap-1">
          <StatusPill status={event.status} />
          {event.blocked_by ? <StatusPill layer={event.blocked_by} /> : null}
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
          {event.component_id}
        </span>
        <span className="truncate text-sm font-medium text-white">{event.title}</span>
      </div>
      <p className="mt-1 line-clamp-2 text-xs text-slate-400">{event.detail}</p>
    </button>
  );
}
