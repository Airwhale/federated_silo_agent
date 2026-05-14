import type { EnvelopeVerificationSnapshot } from "@/api/types";
import { layerToneClass } from "@/lib/statusColor";

import { KeyValueGrid } from "./KeyValueGrid";

interface Props {
  data: EnvelopeVerificationSnapshot;
}

export function EnvelopePanel({ data }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">{data.detail}</p>
      <KeyValueGrid
        rows={[
          { label: "Message type", value: data.message_type ?? "—" },
          { label: "Sender", value: data.sender_agent_id ?? "—" },
          { label: "Recipient", value: data.recipient_agent_id ?? "—" },
          { label: "Body hash", value: data.body_hash ?? "—" },
          {
            label: "Signature",
            value: data.signature_status,
            tone:
              data.signature_status === "valid"
                ? "good"
                : data.signature_status === "invalid" ||
                  data.signature_status === "missing"
                ? "danger"
                : "muted",
          },
          {
            label: "Freshness",
            value: data.freshness_status,
            tone:
              data.freshness_status === "fresh"
                ? "good"
                : data.freshness_status === "expired"
                ? "danger"
                : "muted",
          },
          {
            label: "Blocked by",
            value: data.blocked_by ? (
              <span className={layerToneClass(data.blocked_by)}>{data.blocked_by}</span>
            ) : (
              "—"
            ),
          },
        ]}
      />
    </div>
  );
}
