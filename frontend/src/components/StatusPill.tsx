import type { SnapshotStatus } from "@/api/types";
import { statusPillClass } from "@/lib/statusColor";

interface Props {
  status: SnapshotStatus;
  label?: string;
}

export function StatusPill({ status, label }: Props) {
  return (
    <span className={statusPillClass(status)}>
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
      {label ?? status}
    </span>
  );
}
