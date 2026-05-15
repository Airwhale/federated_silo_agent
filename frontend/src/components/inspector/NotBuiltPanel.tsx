import type { ComponentSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";

type Props = {
  snapshot: ComponentSnapshot;
};

export function NotBuiltPanel({ snapshot }: Props) {
  if (snapshot.status !== "not_built") return null;
  const available =
    snapshot.fields?.find((field) => field.name === "available_after")?.value ?? "later";
  const detail = snapshot.fields?.find((field) => field.name === "detail")?.value;
  return (
    <InspectorSection
      title="Not built"
      status={snapshot.status}
      hint={`Available after ${available}`}
    >
      {detail ? (
        <p className="text-slate-400">{detail}</p>
      ) : (
        <p className="text-slate-500">
          Live inspector data lands when the milestone above completes.
        </p>
      )}
    </InspectorSection>
  );
}
