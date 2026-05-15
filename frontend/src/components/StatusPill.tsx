import type { SecurityLayer, SnapshotStatus } from "../api/types";
import { layerClass, statusClass } from "../lib/statusColor";

type Props = {
  status?: SnapshotStatus | null;
  layer?: SecurityLayer | null;
  label?: string;
};

export function StatusPill({ status, layer, label }: Props) {
  const value = label ?? layer ?? status ?? "unknown";
  const classes = layer ? layerClass(layer) : statusClass(status);
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium tracking-normal ${classes}`}
    >
      <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-80" />
      <span className="truncate">{value.replaceAll("_", " ")}</span>
    </span>
  );
}
