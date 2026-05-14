import { useState } from "react";

interface Props {
  data: unknown;
  defaultOpen?: boolean;
}

export function RawJsonPanel({ data, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className="rounded border border-slate-800 bg-slate-950/60"
    >
      <summary className="cursor-pointer px-2 py-1 text-[11px] uppercase tracking-wide text-slate-500">
        Raw JSON
      </summary>
      <pre className="overflow-x-auto px-3 py-2 font-mono text-[11px] text-slate-300">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}
