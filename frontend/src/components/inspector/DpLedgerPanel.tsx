import type { ComponentSnapshot } from "../../api/types";
import { StatusPill } from "../StatusPill";

type Props = {
  snapshot: ComponentSnapshot;
};

export function DpLedgerPanel({ snapshot }: Props) {
  const ledger = snapshot.dp_ledger;
  if (!ledger) return null;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">DP Ledger</h3>
        <StatusPill status={ledger.status} />
      </div>
      <p className="mt-2 text-sm text-slate-400">{ledger.detail}</p>
      <div className="mt-3 grid gap-2">
        {(ledger.entries ?? []).map((entry) => (
          <div key={`${entry.requester_key}-${entry.responding_bank_id}`} className="rounded-md bg-slate-900 p-2">
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="font-medium text-slate-200">{entry.responding_bank_id}</span>
              <span className="text-slate-400">{entry.requester_key}</span>
            </div>
            <div className="mt-2 h-2 rounded-full bg-slate-800">
              <div
                className="h-2 rounded-full bg-violet-400"
                style={{ width: `${Math.min(100, (entry.rho_spent / entry.rho_max) * 100)}%` }}
              />
            </div>
            <div className="mt-1 text-xs text-slate-400">
              rho spent {entry.rho_spent.toFixed(4)} / remaining {entry.rho_remaining.toFixed(4)}
            </div>
          </div>
        ))}
        {(ledger.entries ?? []).length === 0 ? (
          <div className="rounded-md bg-slate-900 p-2 text-sm text-slate-500">
            No privacy budget rows recorded.
          </div>
        ) : null}
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Histogram views separate total release rho from per-bucket rho and sigma when provenance is available.
      </p>
    </section>
  );
}
