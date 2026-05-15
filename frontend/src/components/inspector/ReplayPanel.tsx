import type { ComponentSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";

type Props = {
  snapshot: ComponentSnapshot;
};

export function ReplayPanel({ snapshot }: Props) {
  const replay = snapshot.replay;
  if (!replay) return null;
  const entries = replay.entries ?? [];

  return (
    <InspectorSection
      title="Replay cache"
      status={snapshot.status}
      hint={`${entries.length} ${entries.length === 1 ? "entry" : "entries"}`}
    >
      {entries.length === 0 ? (
        <p className="text-slate-500">No replay entries recorded.</p>
      ) : (
        <ul className="divide-y divide-slate-800/70 rounded border border-slate-800/70 bg-slate-900/40">
          {entries.map((entry) => (
            <li
              key={`${entry.principal_id}-${entry.nonce_hash}`}
              className="px-2.5 py-1.5"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                <span className="font-medium text-slate-100">{entry.principal_id}</span>
                <span className="font-mono text-[10px] text-slate-500">
                  nonce {entry.nonce_hash}
                </span>
              </div>
              <div className="mt-0.5 text-[11px] text-slate-400">
                first seen {entry.first_seen_at} &middot; expires {entry.expires_at}
              </div>
            </li>
          ))}
        </ul>
      )}
    </InspectorSection>
  );
}
