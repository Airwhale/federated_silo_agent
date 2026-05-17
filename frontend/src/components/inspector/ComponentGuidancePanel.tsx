import type { ComponentSnapshot } from "@/api/types";
import { COMPONENT_GUIDANCE } from "@/domain/componentGuidance";
import { InspectorSection } from "./InspectorSection";
import { KeyValueGrid } from "./KeyValueGrid";

type Props = {
  snapshot: ComponentSnapshot;
};

export function ComponentGuidancePanel({ snapshot }: Props) {
  const guidance = COMPONENT_GUIDANCE[snapshot.component_id];
  return (
    <InspectorSection title="Component guide">
      <KeyValueGrid
        rows={[
          { label: "Current status", value: snapshot.status },
          { label: "Purpose", value: guidance.description },
          { label: "Expected behavior", value: guidance.expectedBehavior, tone: "good" },
          { label: "Attack succeeds if", value: guidance.attackSucceedsIf, tone: "danger" },
        ]}
      />
    </InspectorSection>
  );
}
