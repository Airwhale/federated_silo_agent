import type { ComponentSnapshot } from "../../api/types";
import { StatusPill } from "../StatusPill";

type Props = {
  snapshot: ComponentSnapshot;
};

export function SigningPanel({ snapshot }: Props) {
  const signing = snapshot.signing;
  if (!signing) return null;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">Signing</h3>
        <StatusPill status={signing.status} />
      </div>
      <p className="mt-2 text-sm text-slate-400">{signing.detail}</p>
      <div className="mt-3 rounded-md bg-slate-900 p-2 text-xs text-slate-300">
        <div>Private key exposed: {String(signing.private_key_material_exposed)}</div>
        <div>Last verified key: {signing.last_verified_key_id ?? "not recorded"}</div>
        <div className="mt-2 break-words">
          Known keys: {signing.known_signing_key_ids.join(", ")}
        </div>
      </div>
    </section>
  );
}
