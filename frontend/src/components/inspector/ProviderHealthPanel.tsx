import type { ComponentSnapshot, ProviderHealthSnapshot } from "../../api/types";
import { StatusPill } from "../StatusPill";
import { ModelRoutePanel } from "./ModelRoutePanel";

type Props = {
  snapshot?: ComponentSnapshot;
  providerHealth?: ProviderHealthSnapshot;
};

export function ProviderHealthPanel({ snapshot, providerHealth }: Props) {
  const health = providerHealth ?? snapshot?.provider_health;
  if (!health) return null;
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">Provider And Model Route</h3>
        <StatusPill status={health.status} />
      </div>
      <div className="mt-3">
        <ModelRoutePanel providerHealth={health} />
      </div>
    </section>
  );
}
