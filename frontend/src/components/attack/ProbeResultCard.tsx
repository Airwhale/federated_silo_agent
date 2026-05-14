import type { ProbeResult } from "@/api/types";
import type { TrustDomain } from "@/domain/instances";
import { layerToneClass, statusPillClass } from "@/lib/statusColor";
import { TRUST_DOMAIN_LABELS } from "@/lib/trustDomainLabels";

import { DpLedgerPanel } from "../inspector/DpLedgerPanel";
import { EnvelopePanel } from "../inspector/EnvelopePanel";
import { RawJsonPanel } from "../inspector/RawJsonPanel";
import { ReplayPanel } from "../inspector/ReplayPanel";
import { RouteApprovalPanel } from "../inspector/RouteApprovalPanel";

interface Props {
  result: ProbeResult;
  domain: TrustDomain;
}

export function ProbeResultCard({ result, domain }: Props) {
  const status = result.timeline_event.status;
  return (
    <section className="flex flex-col gap-3 rounded border border-slate-800 bg-slate-950/40 p-3">
      <header className="flex flex-wrap items-baseline gap-2">
        <span className={statusPillClass(status)}>{status}</span>
        <span
          className={
            result.accepted
              ? "rounded bg-rose-500/15 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-rose-300 ring-1 ring-inset ring-rose-500/40"
              : "rounded bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-emerald-300 ring-1 ring-inset ring-emerald-500/30"
          }
        >
          {result.accepted ? "ATTACK ACCEPTED" : "blocked"}
        </span>
        <span className={`text-xs ${layerToneClass(result.blocked_by)}`}>
          {result.blocked_by}
        </span>
        <span className="ml-auto text-[11px] text-slate-500">
          target: {TRUST_DOMAIN_LABELS[domain]} · {result.target_component}
        </span>
      </header>
      <p className="text-xs text-slate-300">{result.reason}</p>

      {result.envelope ? (
        <PanelBlock title="Envelope verification">
          <EnvelopePanel data={result.envelope} />
        </PanelBlock>
      ) : null}
      {result.replay ? (
        <PanelBlock title="Replay cache">
          <ReplayPanel data={result.replay} />
        </PanelBlock>
      ) : null}
      {result.route_approval ? (
        <PanelBlock title="Route approval">
          <RouteApprovalPanel data={result.route_approval} />
        </PanelBlock>
      ) : null}
      {result.dp_ledger ? (
        <PanelBlock title="DP ledger">
          <DpLedgerPanel data={result.dp_ledger} />
        </PanelBlock>
      ) : null}

      <RawJsonPanel data={result} />
    </section>
  );
}

function PanelBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">{title}</p>
      {children}
    </div>
  );
}
