import type { ReactNode } from "react";
import type { SnapshotStatus } from "../../api/types";
import { StatusPill } from "../StatusPill";

type Props = {
  title: string;
  status?: SnapshotStatus;
  /** Optional brief subtitle rendered to the right of the title, before the pill. */
  hint?: ReactNode;
  children: ReactNode;
};

/**
 * Shared section wrapper for all inspector-drawer panels (Signing,
 * Envelope, Replay, Route approval, DP ledger, Audit chain, etc.).
 * Encapsulates the consistent header treatment so each panel can focus
 * on its content rather than reinventing the title + status-pill bar.
 * Border + padding match the topology header style for visual cohesion
 * across the console: anything that's a "scoped inspectable thing"
 * reads as the same shape.
 */
export function InspectorSection({ title, status, hint, children }: Props) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-slate-800/70 px-3 py-1.5">
        <div className="flex min-w-0 items-baseline gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            {title}
          </h3>
          {hint ? <span className="truncate text-[11px] text-slate-500">{hint}</span> : null}
        </div>
        {status ? <StatusPill status={status} /> : null}
      </header>
      <div className="space-y-2 p-2.5 text-xs">{children}</div>
    </section>
  );
}
