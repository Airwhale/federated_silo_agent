import { INSTANCES } from "@/domain/instances";

import { TrustDomainColumn } from "./TrustDomainColumn";

/**
 * Five-column trust-domain topology. Each column owns one trust domain's
 * agents and mechanisms. P9b renders the static skeleton; future P15
 * supplies real per-instance data + cross-column message edges drawn over
 * the same grid.
 */
export function SwimlaneTopology() {
  return (
    <div className="flex h-full gap-3 overflow-x-auto p-3">
      {INSTANCES.map((spec) => (
        <TrustDomainColumn key={spec.id} spec={spec} />
      ))}
    </div>
  );
}
