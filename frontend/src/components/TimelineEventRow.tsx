import type { TimelineEventSnapshot } from "@/api/types";
import { labelFor } from "@/lib/componentLabels";
import { layerToneClass, statusPillClass } from "@/lib/statusColor";
import { formatHhMmSs } from "@/lib/time";

interface Props {
  event: TimelineEventSnapshot;
}

export function TimelineEventRow({ event }: Props) {
  return (
    <li className="flex flex-col gap-1 px-3 py-2 hover:bg-slate-900/40">
      <div className="flex items-baseline gap-2">
        <code className="font-mono text-[11px] text-slate-500">
          {formatHhMmSs(event.timestamp)}
        </code>
        <span className="truncate text-sm text-slate-100">{event.title}</span>
        <span className={`${statusPillClass(event.status)} ml-auto shrink-0`}>
          {event.status}
        </span>
      </div>
      <p className="line-clamp-2 text-xs text-slate-400">{event.detail}</p>
      <div className="flex items-center gap-2 text-[11px] text-slate-500">
        <span>{labelFor(event.component_id)}</span>
        <span className="text-slate-700">·</span>
        <span className="font-mono">{event.component_id}</span>
        {event.blocked_by ? (
          <>
            <span className="text-slate-700">·</span>
            <span className={layerToneClass(event.blocked_by)}>
              blocked by {event.blocked_by}
            </span>
          </>
        ) : null}
      </div>
    </li>
  );
}
