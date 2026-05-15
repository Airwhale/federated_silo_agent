import type { ComponentSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";
import { KeyValueGrid, type KeyValueRow } from "./KeyValueGrid";

type Props = {
  snapshot: ComponentSnapshot;
};

export function RouteApprovalPanel({ snapshot }: Props) {
  const route = snapshot.route_approval;
  if (!route) return null;

  const rows: KeyValueRow[] = [
    {
      label: "Binding",
      value: route.binding_status,
      tone:
        route.binding_status === "matched"
          ? "good"
          : route.binding_status === "mismatched"
            ? "danger"
            : "muted",
    },
    { label: "Route kind", value: route.route_kind ?? "not checked", tone: route.route_kind ? "default" : "muted" },
    { label: "Requester", value: route.requester_bank_id ?? "not checked", tone: route.requester_bank_id ? "default" : "muted" },
    { label: "Responder", value: route.responder_bank_id ?? "not checked", tone: route.responder_bank_id ? "default" : "muted" },
    { label: "Approved hash", value: route.approved_query_body_hash ?? "not checked", tone: route.approved_query_body_hash ? "default" : "muted" },
    { label: "Computed hash", value: route.computed_query_body_hash ?? "not checked", tone: route.computed_query_body_hash ? "default" : "muted" },
  ];

  return (
    <InspectorSection title="Route approval" status={route.status} hint={route.detail}>
      <KeyValueGrid rows={rows} />
    </InspectorSection>
  );
}
