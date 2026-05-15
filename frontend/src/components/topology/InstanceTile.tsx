import { ShieldCheck } from "lucide-react";
import { useComponent } from "../../api/hooks";
import type { ComponentId } from "../../api/types";
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

export function InstanceTile({
  sessionId,
  instanceId,
  componentId,
  label,
  kind,
  onSelect,
}: Props) {
  const component = useComponent(sessionId, componentId, instanceId);
  const status = component.data?.status ?? "pending";

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
      <StatusPill status={status} />
    </button>
  );
}
