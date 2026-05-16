import type { ComponentSnapshot } from "../../api/types";
import { fieldGuidance } from "../../domain/fieldGuidance";
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
        guidanceComponentId={snapshot.component_id}
        rows={fields.map((field) => {
          const value = field.redacted ? "redacted" : field.value;
          const guidance = fieldGuidance(snapshot.component_id, field.name, value);
          return {
            label: field.name,
            value,
            helpValue: value,
            tone: guidance.dangerous ? "danger" : field.redacted ? "muted" : "default",
            help: guidance.help,
          };
        })}
      />
    </InspectorSection>
  );
}
