import type { ComponentSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";
import { KeyValueGrid, type KeyValueRow } from "./KeyValueGrid";

type Props = {
  snapshot: ComponentSnapshot;
};

export function EnvelopePanel({ snapshot }: Props) {
  const envelope = snapshot.envelope;
  if (!envelope) return null;

  const rows: KeyValueRow[] = [
    { label: "Message", value: envelope.message_type ?? "not checked", tone: envelope.message_type ? "default" : "muted" },
    { label: "Sender", value: envelope.sender_agent_id ?? "not checked", tone: envelope.sender_agent_id ? "default" : "muted" },
    { label: "Recipient", value: envelope.recipient_agent_id ?? "not checked", tone: envelope.recipient_agent_id ? "default" : "muted" },
    { label: "Body hash", value: envelope.body_hash ?? "not checked", tone: envelope.body_hash ? "default" : "muted" },
    { label: "Signature", value: envelope.signature_status, tone: signatureTone(envelope.signature_status) },
    { label: "Freshness", value: envelope.freshness_status, tone: freshnessTone(envelope.freshness_status) },
  ];

  return (
    <InspectorSection title="Envelope" status={envelope.status} hint={envelope.detail}>
      <KeyValueGrid rows={rows} />
    </InspectorSection>
  );
}

function signatureTone(value: string): KeyValueRow["tone"] {
  if (value === "valid") return "good";
  if (value === "invalid" || value === "missing") return "danger";
  return "muted";
}

function freshnessTone(value: string): KeyValueRow["tone"] {
  if (value === "fresh") return "good";
  if (value === "stale" || value === "replay") return "danger";
  return "muted";
}
