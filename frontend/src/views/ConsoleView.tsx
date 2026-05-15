import type { ComponentId } from "@/api/types";
import { InteractionConsole } from "@/components/InteractionConsole";
import { useSessionContext } from "@/components/SessionContext";
import { Timeline } from "@/components/Timeline";
import { SwimlaneTopology } from "@/components/topology/SwimlaneTopology";
import type { TrustDomain } from "@/domain/instances";

export function ConsoleView() {
  const { sessionId, setSelection } = useSessionContext();
  const select = (componentId: ComponentId, instanceId?: TrustDomain) =>
    setSelection({ componentId, instanceId });
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="flex min-w-0 flex-col gap-4">
        <SwimlaneTopology sessionId={sessionId} onSelect={select} />
        <InteractionConsole />
      </div>
      <Timeline sessionId={sessionId} onSelect={select} />
    </div>
  );
}
