import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

type Props = {
  value: unknown;
};

function safeStringify(value: unknown): string {
  // ``JSON.stringify`` throws TypeError on circular references and on values
  // containing BigInt. API snapshots never produce either today, but a
  // dev mistake (passing a React element or a Map) would otherwise crash
  // the entire inspector. Catch and degrade gracefully.
  try {
    return JSON.stringify(value, null, 2);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return `// Could not serialise value: ${message}\n${String(value)}`;
  }
}

/**
 * Always-collapsed-by-default raw-JSON dump for the inspector drawer.
 * Sits below every other panel as the "developer escape hatch" view --
 * a judge inspecting a component typically wants the formatted panels
 * above, not the raw schema, so this stays out of the way until clicked.
 */
export function RawJsonPanel({ value }: Props) {
  const [open, setOpen] = useState(false);
  const rendered = useMemo(() => (open ? safeStringify(value) : null), [open, value]);
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <button
        type="button"
        onClick={() => setOpen((next) => !next)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-300 hover:bg-slate-900/60 hover:text-slate-100"
        aria-expanded={open}
      >
        {open ? <ChevronDown size={12} aria-hidden /> : <ChevronRight size={12} aria-hidden />}
        Raw JSON
        <span className="ml-auto text-[10px] font-medium text-slate-500">
          developer view
        </span>
      </button>
      {open && rendered !== null ? (
        <pre className="max-h-72 overflow-auto rounded-b-lg bg-slate-900 p-3 font-mono text-[11px] leading-snug text-slate-300 scrollbar-thin">
          {rendered}
        </pre>
      ) : null}
    </section>
  );
}
