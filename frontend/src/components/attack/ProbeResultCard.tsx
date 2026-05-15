import type { ProbeResult } from "../../api/types";
import { StatusPill } from "../StatusPill";
import { DpLedgerPanel } from "../inspector/DpLedgerPanel";
import { EnvelopePanel } from "../inspector/EnvelopePanel";
import { ReplayPanel } from "../inspector/ReplayPanel";
import { RouteApprovalPanel } from "../inspector/RouteApprovalPanel";

type Props = {
  result: ProbeResult | null;
};

export function ProbeResultCard({ result }: Props) {
  if (!result) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm text-slate-500">
        Output appears here: status, blocked layer, and any evidence snapshots.
      </div>
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
    <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-white">{result.probe_kind}</h3>
          <p className="mt-1 text-xs text-slate-500">{result.target_component}</p>
        </div>
        <div className="flex flex-wrap gap-1">
          <StatusPill status={result.timeline_event.status} />
          <StatusPill layer={result.blocked_by} />
        </div>
      </div>
      <p className="text-sm text-slate-300">{result.reason}</p>
      <EnvelopePanel snapshot={snapshot} />
      <ReplayPanel snapshot={snapshot} />
      <RouteApprovalPanel snapshot={snapshot} />
      <DpLedgerPanel snapshot={snapshot} />
    </div>
  );
}
