import type { ComponentSnapshot } from "../../api/types";
import { KeyValueGrid } from "./KeyValueGrid";

type Props = {
  snapshot: ComponentSnapshot;
};

export function GenericFieldsPanel({ snapshot }: Props) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <h3 className="text-sm font-semibold text-white">Fields</h3>
      <div className="mt-3">
        <KeyValueGrid
          rows={snapshot.fields?.map((field) => ({
            label: field.name,
            value: field.redacted ? "redacted" : field.value,
            tone: field.redacted ? "muted" : "default",
          })) ?? []}
        />
      </div>
    </section>
  );
}
