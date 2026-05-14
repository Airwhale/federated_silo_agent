import type { SecurityLayer, SnapshotStatus } from "@/api/types";

/**
 * Semantic color tokens for status pills. Maps `SnapshotStatus` and
 * `SecurityLayer` values onto Tailwind class strings. Centralised so
 * P18 can re-skin without touching every panel.
 */

const STATUS_BG: Record<SnapshotStatus, string> = {
  live: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  blocked: "bg-orange-500/15 text-orange-300 ring-orange-500/30",
  not_built: "bg-slate-500/15 text-slate-400 ring-slate-500/30",
  pending: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  simulated: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  error: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
};

const LAYER_TONE: Record<SecurityLayer, string> = {
  schema: "text-violet-300",
  signature: "text-amber-300",
  allowlist: "text-orange-300",
  freshness: "text-sky-300",
  replay: "text-rose-300",
  route_approval: "text-pink-300",
  lobster_trap: "text-emerald-300",
  a3_policy: "text-indigo-300",
  p7_budget: "text-lime-300",
  not_built: "text-slate-400",
  accepted: "text-rose-400",
  internal_error: "text-rose-500",
};

export function statusPillClass(status: SnapshotStatus): string {
  return `inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BG[status]}`;
}

export function layerToneClass(layer: SecurityLayer): string {
  return LAYER_TONE[layer];
}
