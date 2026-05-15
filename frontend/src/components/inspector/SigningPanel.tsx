import type { ComponentSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";
import { KeyValueGrid, type KeyValueRow } from "./KeyValueGrid";

type Props = {
  snapshot: ComponentSnapshot;
};

export function SigningPanel({ snapshot }: Props) {
  const signing = snapshot.signing;
  if (!signing) return null;

  const rows: KeyValueRow[] = [
    {
      label: "Private key exposed",
      value: signing.private_key_material_exposed ? "yes" : "no",
      tone: signing.private_key_material_exposed ? "danger" : "good",
    },
    {
      label: "Last verified key",
      value: signing.last_verified_key_id ?? "not recorded",
      tone: signing.last_verified_key_id ? "default" : "muted",
    },
    {
      label: "Known keys",
      value: signing.known_signing_key_ids.length
        ? signing.known_signing_key_ids.join(", ")
        : "none",
      tone: signing.known_signing_key_ids.length ? "default" : "muted",
    },
  ];

  return (
    <InspectorSection title="Signing" status={signing.status} hint={signing.detail}>
      <KeyValueGrid rows={rows} />
    </InspectorSection>
  );
}
