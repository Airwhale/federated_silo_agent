import type { ComponentSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";
import { KeyValueGrid, type KeyValueRow } from "./KeyValueGrid";

type Props = {
  snapshot: ComponentSnapshot;
};

export function AuditChainPanel({ snapshot }: Props) {
  const audit = snapshot.audit_chain;
  if (!audit) return null;

  const rows: KeyValueRow[] = [
    { label: "Events", value: String(audit.event_count) },
    {
      label: "Latest hash",
      value: audit.latest_event_hash ?? "not built",
      tone: audit.latest_event_hash ? "default" : "muted",
    },
  ];

  return (
    <InspectorSection title="Audit chain" status={audit.status} hint={audit.detail}>
      <KeyValueGrid rows={rows} />
    </InspectorSection>
  );
}
