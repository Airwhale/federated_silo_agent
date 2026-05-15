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
      className={`inline-flex max-w-full items-center rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-normal ${classes}`}
    >
      <span className="truncate">{value.replaceAll("_", " ")}</span>
    </span>
  );
}
