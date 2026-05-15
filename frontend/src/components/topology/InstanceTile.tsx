import { AlertTriangle, Loader2, ShieldCheck } from "lucide-react";
import { useComponent } from "../../api/hooks";
import type { ComponentId, SnapshotStatus } from "../../api/types";
import type { TrustDomain } from "../../domain/instances";
import { StatusPill } from "../StatusPill";

type Props = {
  sessionId: string | null;
  instanceId: TrustDomain;
  componentId: ComponentId;
  label: string;
  kind: string;
  onSelect: (componentId: ComponentId, instanceId: TrustDomain) => void;
};

type StatusKind =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; status: SnapshotStatus };

export function InstanceTile({
  sessionId,
  instanceId,
  componentId,
  label,
  kind,
  onSelect,
}: Props) {
  const component = useComponent(sessionId, componentId, instanceId);

  // Three distinct visual states; never silently fall back to "pending"
  // which would be visually identical to a real pending component and
  // hide both transport errors and API contract breaches.
  const state: StatusKind = !sessionId || component.isLoading
    ? { kind: "loading" }
    : component.error
    ? {
        kind: "error",
        message: component.error instanceof Error ? component.error.message : "unknown error",
      }
    : { kind: "ready", status: component.data?.status ?? "error" };

  return (
    <button
      type="button"
      onClick={() => onSelect(componentId, instanceId)}
      className="flex w-full items-center gap-2 rounded-md border border-slate-800 bg-slate-900/80 p-2 text-left hover:border-sky-400/70 hover:bg-slate-800"
    >
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-slate-800 text-sky-200">
        <ShieldCheck size={15} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-slate-100">{label}</span>
        <span className="block truncate text-[11px] text-slate-500">{kind}</span>
      </span>
      {state.kind === "loading" ? (
        <Loader2 size={14} className="shrink-0 animate-spin text-slate-500" aria-label="loading" />
      ) : state.kind === "error" ? (
        <span
          className="inline-flex items-center gap-1 rounded-md border border-rose-400/40 bg-rose-500/10 px-1.5 py-0.5 text-[11px] text-rose-200"
          title={state.message}
        >
          <AlertTriangle size={12} aria-hidden /> err
        </span>
      ) : (
        <StatusPill status={state.status} />
      )}
    </button>
  );
}
