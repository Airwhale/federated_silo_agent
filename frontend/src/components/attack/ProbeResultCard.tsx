import type { ProbeResult } from "../../api/types";
import { StatusPill } from "../StatusPill";
import { DpLedgerPanel } from "../inspector/DpLedgerPanel";
import { EnvelopePanel } from "../inspector/EnvelopePanel";
import { ReplayPanel } from "../inspector/ReplayPanel";
import { RouteApprovalPanel } from "../inspector/RouteApprovalPanel";

type Props = {
  result: ProbeResult | null;
};

/**
 * Renders the typed result of one Attack-Lab probe launch: status,
 * blocked layer, reason text, and any envelope / replay / route /
 * DP-ledger snapshots the backend attached. Reuses the inspector
 * panels so probe outputs render with the same vocabulary as
 * direct component inspection.
 */
export function ProbeResultCard({ result }: Props) {
  if (!result) {
    return (
      <p className="text-[11px] text-slate-500">
        Probe result lands here: status, blocked layer, evidence snapshots.
      </p>
    );
  }

  const snapshot = {
    component_id: result.target_component,
    status: result.timeline_event.status,
    title: result.probe_kind,
    fields: [],
    envelope: result.envelope,
    replay: result.replay,
    route_approval: result.route_approval,
    dp_ledger: result.dp_ledger,
  };

  return (
    <div className="flex flex-col gap-2">
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-200">
            Result
          </span>
          <code className="truncate font-mono text-[11px] text-slate-500">
            {result.target_component}
          </code>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <StatusPill status={result.timeline_event.status} />
          <StatusPill layer={result.blocked_by} />
        </div>
      </header>
      <p className="text-xs text-slate-300">{result.reason}</p>
      <EnvelopePanel snapshot={snapshot} />
      <ReplayPanel snapshot={snapshot} />
      <RouteApprovalPanel snapshot={snapshot} />
      <DpLedgerPanel snapshot={snapshot} />
    </div>
  );
}
