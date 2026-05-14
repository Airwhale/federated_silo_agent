import { RunControls } from "@/components/RunControls";
import { Timeline } from "@/components/Timeline";
import { SwimlaneTopology } from "@/components/topology/SwimlaneTopology";

export function ConsoleView() {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <RunControls />
      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 flex-1 overflow-hidden">
          <SwimlaneTopology />
        </div>
        <div className="w-[26rem] min-w-[20rem]">
          <Timeline />
        </div>
      </div>
    </div>
  );
}
