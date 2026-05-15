import type { ComponentSnapshot } from "../../api/types";
import { StatusPill } from "../StatusPill";

type Props = {
  snapshot: ComponentSnapshot;
};

export function RouteApprovalPanel({ snapshot }: Props) {
  const route = snapshot.route_approval;
  if (!route) return null;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">Route Approval</h3>
        <StatusPill status={route.status} />
      </div>
      <dl className="mt-3 grid gap-2 text-sm">
        <Row name="Binding" value={route.binding_status} />
        <Row name="Route kind" value={route.route_kind ?? "not checked"} />
        <Row name="Requester" value={route.requester_bank_id ?? "not checked"} />
        <Row name="Responder" value={route.responder_bank_id ?? "not checked"} />
        <Row name="Approved hash" value={route.approved_query_body_hash ?? "not checked"} />
        <Row name="Computed hash" value={route.computed_query_body_hash ?? "not checked"} />
      </dl>
      <p className="mt-3 text-sm text-slate-400">{route.detail}</p>
    </section>
  );
}

function Row({ name, value }: { name: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-900 p-2">
      <dt className="text-[11px] uppercase text-slate-500">{name}</dt>
      <dd className="mt-1 break-words text-slate-200">{value}</dd>
    </div>
  );
}
