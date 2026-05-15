import type { ComponentSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";

type Props = {
  snapshot: ComponentSnapshot;
};

export function DpLedgerPanel({ snapshot }: Props) {
  const ledger = snapshot.dp_ledger;
  if (!ledger) return null;
  const entries = ledger.entries ?? [];

  return (
    <InspectorSection title="DP ledger" status={ledger.status} hint={ledger.detail}>
      {entries.length === 0 ? (
        <p className="text-slate-500">No privacy budget rows recorded.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {entries.map((entry) => {
            // Guard against ``rho_max=0``: would otherwise produce
            // ``Infinity`` (when ``rho_spent > 0``) or ``NaN`` (when
            // ``rho_spent = 0``), and ``style.width: NaN%`` is invalid
            // CSS that breaks the bar render entirely. Both probes and
            // future P15 ledger writes can in principle emit a
            // zero-cap row (e.g. a requester with no allocated
            // budget); the bar reads as "0% filled" in that case,
            // which is the truthful interpretation.
            const rawPct = entry.rho_max > 0 ? (entry.rho_spent / entry.rho_max) * 100 : 0;
            // ``Number.isFinite`` guard catches the edge cases the
            // division check above doesn't: an upstream snapshot that
            // somehow carried ``Infinity`` or ``NaN`` in ``rho_spent``
            // (Pydantic's ``NonNegativeFloat`` rejects those server-
            // side, but defending in the renderer keeps an invalid
            // ``style.width: NaN%`` from silently breaking the bar
            // if the contract is ever loosened).
            const pct = Math.min(100, Math.max(0, Number.isFinite(rawPct) ? rawPct : 0));
            return (
              <li
                key={`${entry.requester_key}-${entry.responding_bank_id}`}
                className="rounded border border-slate-800/70 bg-slate-900/40 px-2.5 py-1.5"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-slate-100">{entry.responding_bank_id}</span>
                  <span className="font-mono text-[10px] text-slate-500">
                    {entry.requester_key}
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-violet-400/80"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="mt-0.5 flex items-baseline justify-between gap-2 text-[11px] text-slate-400">
                  <span>
                    rho spent <span className="font-mono text-slate-300">{entry.rho_spent.toFixed(4)}</span>
                    {" / max "}
                    <span className="font-mono text-slate-300">{entry.rho_max.toFixed(4)}</span>
                  </span>
                  <span className="font-mono text-slate-500">
                    remaining {entry.rho_remaining.toFixed(4)}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-[11px] text-slate-500">
        Histogram views separate total release rho from per-bucket rho and sigma when provenance is available.
      </p>
    </InspectorSection>
  );
}
