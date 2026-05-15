import { useState } from "react";

type Props = {
  value: unknown;
};

export function RawJsonPanel({ value }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <button
        type="button"
        onClick={() => setOpen((next) => !next)}
        className="text-sm font-semibold text-sky-200 hover:text-sky-100"
      >
        Raw JSON
      </button>
      {open ? (
        <pre className="mt-3 max-h-72 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-300 scrollbar-thin">
          {JSON.stringify(value, null, 2)}
        </pre>
      ) : null}
    </section>
  );
}
