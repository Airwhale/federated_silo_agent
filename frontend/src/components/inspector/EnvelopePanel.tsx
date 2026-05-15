import type { ComponentSnapshot } from "../../api/types";
import { StatusPill } from "../StatusPill";

type Props = {
  snapshot: ComponentSnapshot;
};

export function EnvelopePanel({ snapshot }: Props) {
  const envelope = snapshot.envelope;
  if (!envelope) return null;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">Envelope</h3>
        <StatusPill status={envelope.status} />
      </div>
      <dl className="mt-3 grid gap-2 text-sm">
        <Row name="Message" value={envelope.message_type ?? "not checked"} />
        <Row name="Sender" value={envelope.sender_agent_id ?? "not checked"} />
        <Row name="Recipient" value={envelope.recipient_agent_id ?? "not checked"} />
        <Row name="Body hash" value={envelope.body_hash ?? "not checked"} />
        <Row name="Signature" value={envelope.signature_status} />
        <Row name="Freshness" value={envelope.freshness_status} />
      </dl>
      <p className="mt-3 text-sm text-slate-400">{envelope.detail}</p>
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
