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
      <p className="mb-2 rounded border border-slate-800/70 bg-slate-900/50 px-2.5 py-2 text-xs leading-relaxed text-slate-300">
        {guidance.description}
      </p>
      <KeyValueGrid
        rows={[
          { label: "Expected behavior", value: guidance.expectedBehavior, tone: "good" },
          { label: "Attack succeeds if", value: guidance.attackSucceedsIf, tone: "danger" },
        ]}
      />
    </InspectorSection>
  );
}
