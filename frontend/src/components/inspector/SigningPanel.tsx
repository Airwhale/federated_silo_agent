import type { SigningStateSnapshot } from "@/api/types";

import { KeyValueGrid } from "./KeyValueGrid";

interface Props {
  data: SigningStateSnapshot;
}

export function SigningPanel({ data }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">{data.detail}</p>
      <KeyValueGrid
        rows={[
          {
            label: "Private key exposed",
            value: "false",
            tone: "good",
          },
          {
            label: "Last verified key id",
            value: data.last_verified_key_id ?? "—",
            tone: data.last_verified_key_id ? "default" : "muted",
          },
        ]}
      />
      <div>
        <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
          Known signing key ids ({data.known_signing_key_ids.length})
        </p>
        <ul className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs">
          {data.known_signing_key_ids.length === 0 ? (
            <li className="text-slate-500">none</li>
          ) : (
            data.known_signing_key_ids.map((id) => (
              <li key={id} className="font-mono text-slate-200">
                {id}
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
