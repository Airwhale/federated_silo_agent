import type { ReactNode } from "react";

export type KeyValueRow = {
  label: string;
  value: ReactNode;
  tone?: "default" | "muted" | "danger" | "good";
};

type Props = {
  rows: KeyValueRow[];
};

const TONE_CLASS: Record<NonNullable<KeyValueRow["tone"]>, string> = {
  default: "text-slate-100",
  muted: "text-slate-400",
  danger: "text-rose-300",
  good: "text-emerald-300",
};

export function KeyValueGrid({ rows }: Props) {
  return (
    <dl className="grid gap-2 text-sm">
      {rows.map((row) => (
        <div key={row.label} className="rounded-md bg-slate-900 p-2">
          <dt className="text-[11px] uppercase text-slate-500">{row.label}</dt>
          <dd className={`mt-1 break-words ${TONE_CLASS[row.tone ?? "default"]}`}>
            {row.value ?? <span className="text-slate-600">not reported</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}
