import type { ComponentSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";
import { KeyValueGrid } from "./KeyValueGrid";

type Props = {
  snapshot: ComponentSnapshot;
};

export function GenericFieldsPanel({ snapshot }: Props) {
  const fields = snapshot.fields ?? [];
  if (fields.length === 0) return null;
  return (
    <InspectorSection title="Fields">
      <KeyValueGrid
        rows={fields.map((field) => ({
          label: field.name,
          value: field.redacted ? "redacted" : field.value,
          tone: field.redacted ? "muted" : "default",
        }))}
      />
    </InspectorSection>
  );
}
