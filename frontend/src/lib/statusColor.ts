import type { SecurityLayer, SnapshotStatus } from "../api/types";

export function statusClass(status?: SnapshotStatus | null): string {
  switch (status) {
    case "live":
      return "border-emerald-500/40 bg-emerald-500/12 text-emerald-100";
    case "blocked":
      return "border-rose-500/50 bg-rose-500/12 text-rose-100";
    case "not_built":
      return "border-slate-500/40 bg-slate-500/12 text-slate-200";
    case "pending":
      return "border-amber-500/40 bg-amber-500/12 text-amber-100";
    case "simulated":
      return "border-cyan-500/40 bg-cyan-500/12 text-cyan-100";
    case "error":
      return "border-red-500/50 bg-red-500/12 text-red-100";
    default:
      return "border-slate-600 bg-slate-900 text-slate-200";
  }
}

export function layerClass(layer?: SecurityLayer | null): string {
  switch (layer) {
    case "signature":
    case "allowlist":
    case "route_approval":
    case "replay":
      return "border-sky-500/40 bg-sky-500/12 text-sky-100";
    case "p7_budget":
      return "border-violet-500/40 bg-violet-500/12 text-violet-100";
    case "lobster_trap":
    case "a3_policy":
      return "border-orange-500/40 bg-orange-500/12 text-orange-100";
    case "not_built":
      return "border-slate-500/40 bg-slate-500/12 text-slate-200";
    default:
      return "border-slate-600 bg-slate-900 text-slate-200";
  }
}
