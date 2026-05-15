import type { ComponentSnapshot, ProviderHealthSnapshot } from "../../api/types";
import { InspectorSection } from "./InspectorSection";
import { ModelRoutePanel } from "./ModelRoutePanel";

type Props = {
  snapshot?: ComponentSnapshot;
  providerHealth?: ProviderHealthSnapshot;
};

export function ProviderHealthPanel({ snapshot, providerHealth }: Props) {
  const health = providerHealth ?? snapshot?.provider_health;
  if (!health) return null;
  return (
    <InspectorSection title="Provider and model route" status={health.status}>
      <ModelRoutePanel providerHealth={health} />
    </InspectorSection>
  );
}
