import { useComponent } from "@/api/hooks";
import type { ComponentId } from "@/api/types";
import { isMechanism, labelFor } from "@/lib/componentLabels";
import { statusPillClass } from "@/lib/statusColor";

import { useSessionContext } from "../SessionContext";

interface Props {
  componentId: ComponentId;
  /**
   * For mechanism tiles (signing, replay, etc.) we still want to show them in
   * the per-instance column even though the backend ComponentId is singleton.
   * The visual is a per-instance "card" but the data source is shared.
   */
  domain: import("@/domain/instances").TrustDomain;
}

export function InstanceTile({ componentId, domain }: Props) {
  const { sessionId, selection, setSelection } = useSessionContext();
  const query = useComponent(sessionId, componentId);

  const status = query.data?.status ?? "pending";
  const isSelected =
    selection?.componentId === componentId && selection?.domain === domain;
  const mechanism = isMechanism(componentId);

  return (
    <button
      type="button"
      onClick={() => setSelection({ domain, componentId })}
      className={[
        "group flex w-full items-center justify-between gap-2 rounded-md border px-2.5 py-1.5 text-left text-sm transition-colors",
        mechanism
          ? "border-slate-800 bg-slate-900/60 hover:border-slate-700"
          : "border-slate-700 bg-slate-800/70 hover:border-emerald-500/40",
        isSelected ? "ring-1 ring-emerald-400/70" : "",
      ].join(" ")}
    >
      <span className="flex flex-col leading-tight">
        <span className={mechanism ? "text-slate-400" : "text-slate-100"}>
          {labelFor(componentId)}
        </span>
        <span className="font-mono text-[10px] text-slate-500">{componentId}</span>
      </span>
      <span className={statusPillClass(status)}>
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
        {status}
      </span>
    </button>
  );
}
