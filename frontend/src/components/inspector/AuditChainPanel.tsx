import type { ComponentSnapshot } from "../../api/types";
import { StatusPill } from "../StatusPill";

type Props = {
  snapshot: ComponentSnapshot;
};

export function AuditChainPanel({ snapshot }: Props) {
  const audit = snapshot.audit_chain;
  if (!audit) return null;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">Audit Chain</h3>
        <StatusPill status={audit.status} />
      </div>
      <dl className="mt-3 grid gap-2 text-sm">
        <div className="rounded-md bg-slate-900 p-2">
          <dt className="text-[11px] uppercase text-slate-500">Events</dt>
          <dd className="mt-1 text-slate-200">{audit.event_count}</dd>
        </div>
        <div className="rounded-md bg-slate-900 p-2">
          <dt className="text-[11px] uppercase text-slate-500">Latest hash</dt>
          <dd className="mt-1 break-words text-slate-200">{audit.latest_event_hash ?? "not built"}</dd>
        </div>
      </dl>
      <p className="mt-3 text-sm text-slate-400">{audit.detail}</p>
    </section>
  );
}
