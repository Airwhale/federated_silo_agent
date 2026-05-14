/**
 * Shared key/value grid for inspector panels. Keeps row spacing + monospace
 * value styling consistent so P18 polish only touches one place.
 */
interface Row {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "muted" | "danger" | "good";
}

interface Props {
  rows: Row[];
}

const TONE: Record<NonNullable<Row["tone"]>, string> = {
  default: "text-slate-100",
  muted: "text-slate-400",
  danger: "text-rose-300",
  good: "text-emerald-300",
};

export function KeyValueGrid({ rows }: Props) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="text-slate-500">{row.label}</dt>
          <dd className={`font-mono ${TONE[row.tone ?? "default"]} break-all`}>
            {row.value ?? <span className="text-slate-600">—</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}
