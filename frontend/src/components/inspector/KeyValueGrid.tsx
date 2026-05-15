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

/**
 * Two-column label/value rows separated by thin dividers. Replaces the
 * previous one-card-per-row stack which was visually noisy and ate
 * vertical space disproportionately to the information density of each
 * row. Used by the System view's Backend panel and by every inspector
 * GenericFieldsPanel, so the density change cascades.
 *
 * Label column is fixed-width (10rem) on >= sm so the values align
 * vertically and a viewer's eye can scan down the value column to
 * find what they need. On mobile the labels stack above the values
 * (single column) to avoid horizontal squeeze.
 */
export function KeyValueGrid({ rows }: Props) {
  return (
    <dl className="divide-y divide-slate-800/70 rounded border border-slate-800/70 bg-slate-900/40 text-xs">
      {rows.map((row) => (
        <div
          key={row.label}
          className="grid gap-x-3 gap-y-0.5 px-2.5 py-1.5 sm:grid-cols-[10rem_minmax(0,1fr)]"
        >
          <dt className="text-[11px] uppercase tracking-wide text-slate-500">
            {row.label}
          </dt>
          <dd className={`break-words ${TONE_CLASS[row.tone ?? "default"]}`}>
            {row.value ?? <span className="text-slate-600">not reported</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}
