import type { ComponentReadinessSnapshot } from "@/api/types";

interface Props {
  readiness?: ComponentReadinessSnapshot | null;
  detail?: string;
}

export function NotBuiltPanel({ readiness, detail }: Props) {
  const availableAfter = readiness?.available_after ?? "a future milestone";
  const summary = readiness?.detail ?? detail ?? "Not built yet.";
  return (
    <div className="flex flex-col gap-3 rounded border border-slate-800 bg-slate-950/40 p-3">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-500/15 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-400 ring-1 ring-inset ring-slate-500/30">
          not built
        </span>
        <span className="text-xs text-slate-500">Available after: {availableAfter}</span>
      </div>
      <p className="text-xs text-slate-400">{summary}</p>
      <p className="text-[10px] text-slate-500">
        The panel keeps its final shape so the next milestone fills in real data
        without UI changes.
      </p>
    </div>
  );
}
