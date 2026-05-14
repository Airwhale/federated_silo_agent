import type { SnapshotField } from "@/api/types";

interface Props {
  fields: SnapshotField[];
}

export function GenericFieldsPanel({ fields }: Props) {
  if (fields.length === 0) {
    return <p className="text-xs text-slate-500">No fields reported for this component.</p>;
  }
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
      {fields.map((field) => (
        <div key={field.name} className="contents">
          <dt className="text-slate-500">{field.name}</dt>
          <dd
            className={`break-all ${field.redacted ? "italic text-slate-500" : "font-mono text-slate-200"}`}
          >
            {field.redacted ? "[redacted]" : field.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
