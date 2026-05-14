import type { ReplayCacheSnapshot } from "@/api/types";
import { formatAbsolute, formatRelative } from "@/lib/time";

interface Props {
  data: ReplayCacheSnapshot;
}

export function ReplayPanel({ data }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">
        Nonces are stored hashed (16-char SHA-256 prefix); the raw nonce never
        crosses the API boundary.
      </p>
      {data.entries.length === 0 ? (
        <p className="text-xs text-slate-500">No replay-cache entries in this session yet.</p>
      ) : (
        <ul className="divide-y divide-slate-800 rounded border border-slate-800 bg-slate-950/40 text-xs">
          {data.entries.map((entry) => (
            <li key={`${entry.principal_id}:${entry.nonce_hash}`} className="px-3 py-2">
              <div className="flex items-baseline justify-between gap-2">
                <code className="font-mono text-slate-200">{entry.nonce_hash}</code>
                <span className="text-[11px] text-slate-500">{entry.principal_id}</span>
              </div>
              <div className="mt-1 grid grid-cols-2 gap-x-3 text-[11px] text-slate-500">
                <span title={formatAbsolute(entry.first_seen_at)}>
                  seen {formatRelative(entry.first_seen_at)}
                </span>
                <span title={formatAbsolute(entry.expires_at)}>
                  expires {formatRelative(entry.expires_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
