import { AlertTriangle, Loader2 } from "lucide-react";
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

/**
 * One topology tile -- a clickable row inside a trust-domain column.
 * Polished for ops-console density: tighter padding, smaller font, no
 * generic shield icon (the previous "ShieldCheck on every tile" carried
 * no kind-specific signal). Kind is now communicated by a 2px colored
 * accent strip on the left edge -- agents emerald, security slate,
 * policy/model/data/audit each a distinct restrained tone -- so the
 * agent-vs-mechanism distinction is legible without taking horizontal
 * space.
 *
 * Built vs not-built: the StatusPill at right already encodes status,
 * but tiles for not-built components additionally get reduced opacity
 * and a dotted left-edge accent so the "this row is a placeholder"
 * signal reads at a glance, not just on the right-edge pill.
 */
const KIND_ACCENT: Record<string, string> = {
  agent: "bg-emerald-400/70",
  security: "bg-slate-500/60",
  policy: "bg-amber-400/70",
  model: "bg-sky-400/70",
  data: "bg-violet-400/70",
  audit: "bg-rose-400/70",
};

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

  const notBuilt = state.kind === "ready" && state.status === "not_built";
  const accent = KIND_ACCENT[kind] ?? KIND_ACCENT.security;

  return (
    <button
      type="button"
      onClick={() => onSelect(componentId, instanceId)}
      title={`${label} (${componentId})`}
      className={`group relative flex w-full items-center gap-2 overflow-hidden rounded border px-2 py-1 text-left text-xs transition-colors ${
        isAgent
          ? "border-slate-700/80 bg-slate-800/60 hover:border-emerald-400/40 hover:bg-slate-800"
          : "border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-900"
      } ${selected ? "ring-1 ring-emerald-300/70" : ""} ${notBuilt ? "opacity-60" : ""}`}
    >
      {/*
        Left-edge accent strip carries the kind signal so the row can
        drop the previous generic 24x24 ShieldCheck icon box. 2px wide,
        full tile height; dashed for not-built tiles so the
        placeholder state is visible even when the row is far from the
        right-edge StatusPill.
      */}
      <span
        aria-hidden
        className={`absolute left-0 top-0 h-full w-[2px] ${notBuilt ? "border-l border-dashed border-slate-500/60 bg-transparent" : accent}`}
      />
      <span className="ml-1 min-w-0 flex-1 leading-tight">
        <span
          className={`block truncate font-medium ${
            isAgent ? "text-slate-100" : "text-slate-300"
          } ${notBuilt ? "italic" : ""}`}
        >
          {label}
        </span>
        <span className="block truncate font-mono text-[10px] text-slate-500">
          {componentId}
        </span>
      </span>
      {state.kind === "loading" ? (
        <Loader2 size={12} className="shrink-0 animate-spin text-slate-500" aria-label="loading" />
      ) : state.kind === "error" ? (
        <span
          className="inline-flex items-center gap-1 rounded border border-rose-400/40 bg-rose-500/10 px-1.5 py-0.5 text-[10px] text-rose-200"
          title={state.message}
        >
          <AlertTriangle size={10} aria-hidden /> err
        </span>
      ) : (
        <StatusPill status={state.status} />
      )}
    </button>
  );
}
