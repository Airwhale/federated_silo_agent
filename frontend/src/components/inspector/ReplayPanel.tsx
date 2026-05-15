import type { ComponentSnapshot } from "../../api/types";

type Props = {
  snapshot: ComponentSnapshot;
};

export function ReplayPanel({ snapshot }: Props) {
  const replay = snapshot.replay;
  if (!replay) return null;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <h3 className="text-sm font-semibold text-white">Replay Cache</h3>
      <div className="mt-3 grid gap-2">
        {(replay.entries ?? []).map((entry) => (
          <div key={`${entry.principal_id}-${entry.nonce_hash}`} className="rounded-md bg-slate-900 p-2 text-sm">
            <div className="font-medium text-slate-200">{entry.principal_id}</div>
            <div className="text-xs text-slate-500">nonce {entry.nonce_hash}</div>
            <div className="mt-1 text-xs text-slate-400">
              first seen {entry.first_seen_at} / expires {entry.expires_at}
            </div>
          </div>
        ))}
        {(replay.entries ?? []).length === 0 ? (
          <div className="rounded-md bg-slate-900 p-2 text-sm text-slate-500">
            No replay entries recorded.
          </div>
        ) : null}
      </div>
    </section>
  );
}
