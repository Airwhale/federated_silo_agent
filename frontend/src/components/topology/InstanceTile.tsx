import { AlertTriangle, Loader2, ShieldCheck } from "lucide-react";
import { useComponent } from "../../api/hooks";
import type { ComponentId, SnapshotStatus } from "../../api/types";
import type { TrustDomain } from "../../domain/instances";
import { useSessionContext } from "../SessionContext";
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
  const { selection } = useSessionContext();
  const component = useComponent(sessionId, componentId, instanceId);
  const isAgent = kind === "agent";
  const selected = selection?.componentId === componentId && selection.instanceId === instanceId;

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
      className={`flex w-full items-center justify-between gap-2 rounded-md border px-2.5 py-1.5 text-left text-sm transition-colors ${
        isAgent
          ? "border-slate-700 bg-slate-800/70 hover:border-emerald-500/40"
          : "border-slate-800 bg-slate-900/60 hover:border-slate-700"
      } ${selected ? "ring-1 ring-emerald-400/70" : ""}`}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span
          className={`grid h-6 w-6 shrink-0 place-items-center rounded border ${
            isAgent
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-slate-700 bg-slate-900 text-slate-400"
          }`}
        >
          <ShieldCheck size={13} aria-hidden />
        </span>
        <span className="min-w-0 flex-1 leading-tight">
          <span className={isAgent ? "block truncate font-medium text-slate-100" : "block truncate text-slate-400"}>
            {label}
          </span>
          <span className="block truncate font-mono text-[10px] text-slate-500">{componentId}</span>
        </span>
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
