import type { RouteApprovalSnapshot } from "@/api/types";

import { KeyValueGrid } from "./KeyValueGrid";

interface Props {
  data: RouteApprovalSnapshot;
}

export function RouteApprovalPanel({ data }: Props) {
  const matched = data.binding_status === "matched";
  const mismatched = data.binding_status === "mismatched";

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">{data.detail}</p>
      <KeyValueGrid
        rows={[
          { label: "Query id", value: data.query_id ?? "—" },
          { label: "Route kind", value: data.route_kind ?? "—" },
          { label: "Requester", value: data.requester_bank_id ?? "—" },
          { label: "Responder", value: data.responder_bank_id ?? "—" },
          {
            label: "Approved body hash",
            value: data.approved_query_body_hash ?? "—",
          },
          {
            label: "Computed body hash",
            value: data.computed_query_body_hash ?? "—",
            tone: mismatched ? "danger" : matched ? "good" : "default",
          },
          {
            label: "Binding",
            value: data.binding_status,
            tone: matched ? "good" : mismatched ? "danger" : "muted",
          },
        ]}
      />
    </div>
  );
}
