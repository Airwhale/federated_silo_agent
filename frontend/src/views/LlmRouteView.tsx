import { useSystem } from "@/api/hooks";
import { describeError } from "@/api/errors";
import { LlmRoutePanel } from "@/components/inspector/LlmRoutePanel";
import { INSTANCES } from "@/domain/instances";
import { TRUST_DOMAIN_LABELS } from "@/lib/trustDomainLabels";

export function LlmRouteView() {
  const query = useSystem();

  return (
    <div className="flex h-full flex-col overflow-hidden p-4">
      <header className="mb-3 flex flex-col gap-1">
        <h2 className="text-base font-semibold text-slate-100">LLM routes</h2>
        <p className="text-xs text-slate-400">
          One model route per trust domain. Each card shows the redacted
          provider/key presence flags that P9a exposes today. P14 lands the
          per-domain route name + structured-output schema + last-request
          preview through this same surface.
        </p>
      </header>

      {query.isLoading ? (
        <p className="text-xs text-slate-500">Loading system snapshot…</p>
      ) : query.error ? (
        <p className="text-xs text-rose-300">
          Could not load — {describeError(query.error)}
        </p>
      ) : query.data ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {INSTANCES.map((spec) => (
            <article
              key={spec.id}
              className="rounded-lg border border-slate-800 bg-slate-900/40 p-3"
            >
              <h3 className="mb-2 text-sm font-semibold text-slate-100">
                {TRUST_DOMAIN_LABELS[spec.id]}
              </h3>
              <LlmRoutePanel
                provider={query.data.provider_health}
                trustDomainLabel={TRUST_DOMAIN_LABELS[spec.id]}
              />
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}
