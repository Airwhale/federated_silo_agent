import { useMemo, useState } from "react";

type Props = {
  value: unknown;
};

function safeStringify(value: unknown): string {
  // `JSON.stringify` throws TypeError on circular references and on values
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

export function RawJsonPanel({ value }: Props) {
  const [open, setOpen] = useState(false);
  const rendered = useMemo(() => (open ? safeStringify(value) : null), [open, value]);
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <button
        type="button"
        onClick={() => setOpen((next) => !next)}
        className="text-sm font-semibold text-sky-200 hover:text-sky-100"
      >
        Raw JSON
      </button>
      {open && rendered !== null ? (
        <pre className="mt-3 max-h-72 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-300 scrollbar-thin">
          {rendered}
        </pre>
      ) : null}
    </section>
  );
}
