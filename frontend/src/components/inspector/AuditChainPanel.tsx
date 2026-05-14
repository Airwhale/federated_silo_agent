import type { AuditChainSnapshot } from "@/api/types";

import { KeyValueGrid } from "./KeyValueGrid";

interface Props {
  data: AuditChainSnapshot;
}

export function AuditChainPanel({ data }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">{data.detail}</p>
      <KeyValueGrid
        rows={[
          { label: "Event count", value: String(data.event_count) },
          {
            label: "Latest event hash",
            value: data.latest_event_hash ?? "—",
            tone: data.latest_event_hash ? "default" : "muted",
          },
        ]}
      />
    </div>
  );
}
