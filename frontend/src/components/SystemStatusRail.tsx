import { describeError } from "@/api/errors";
import { useHealth, useSystem } from "@/api/hooks";
import type { ComponentReadinessSnapshot, ProviderHealthSnapshot } from "@/api/types";
import { StatusPill } from "@/components/StatusPill";
import { componentLabel } from "@/domain/instances";

export function SystemStatusRail() {
  const health = useHealth();
  const system = useSystem();
  const providerHealth = system.data?.provider_health ?? null;

  return (
    <aside className="flex min-w-0 flex-col gap-3">
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
        <header className="mb-2 flex items-baseline justify-between gap-2">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
              System status
            </h2>
            <p className="mt-1 text-[11px] text-slate-500">
              API, model route, and component readiness.
            </p>
          </div>
          <StatusPill status={system.data?.status ?? (health.data?.status === "ok" ? "live" : "pending")} />
        </header>

        {system.error ? (
          <p className="mb-2 rounded border border-rose-500/30 bg-rose-500/10 p-2 text-[11px] text-rose-200">
            {describeError(system.error)}
          </p>
        ) : null}

        <div className="grid gap-2 text-[11px]">
          <StatusLine
            label="Control API"
            value={health.data?.status === "ok" ? "reachable" : "checking"}
            status={health.data?.status === "ok" ? "live" : "pending"}
          />
          {providerHealth ? <ProviderRouteSummary providerHealth={providerHealth} /> : null}
        </div>
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
        <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
              Readiness
            </h2>
            <p className="mt-1 text-[11px] text-slate-500">
              {system.data?.detail ?? "Loading system snapshot."}
            </p>
          </div>
          {system.data ? <StatusPill status={system.data.status} /> : null}
        </header>

        <div className="max-h-[19rem] overflow-y-auto pr-1 scrollbar-thin">
          <div className="flex flex-col gap-1.5">
            {(system.data?.components ?? []).map((component) => (
              <ReadinessRow key={component.component_id} component={component} />
            ))}
            {!system.data ? (
              <div className="rounded border border-slate-800/70 bg-slate-900/40 p-2 text-[11px] text-slate-500">
                Waiting for readiness rows.
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </aside>
  );
}

function ProviderRouteSummary({ providerHealth }: { providerHealth: ProviderHealthSnapshot }) {
  const credentials = [
    providerHealth.gemini_api_key_present ? "Gemini" : null,
    providerHealth.openrouter_api_key_present ? "OpenRouter" : null,
  ].filter(Boolean);

  return (
    <div className="rounded border border-slate-800/80 bg-slate-900/40 p-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-medium text-slate-300">Model route</span>
        <StatusPill status={providerHealth.status} />
      </div>
      <p className="mb-2 text-slate-500">{providerHealth.detail}</p>
      <div className="grid grid-cols-2 gap-1">
        <MiniState label="Lobster Trap" live={providerHealth.lobster_trap_configured} />
        <MiniState label="LiteLLM" live={providerHealth.litellm_configured} />
        <MiniState label="Keys" live={credentials.length > 0} value={credentials.join(", ") || "none"} />
        <MiniState label="Secrets" live value={providerHealth.secret_values} />
      </div>
    </div>
  );
}

function StatusLine({
  label,
  value,
  status,
}: {
  label: string;
  value: string;
  status: "live" | "pending";
}) {
  return (
    <div className="flex items-center justify-between gap-2 rounded border border-slate-800/80 bg-slate-900/40 p-2">
      <span className="font-medium text-slate-300">{label}</span>
      <span className="flex items-center gap-2">
        <span className="text-slate-500">{value}</span>
        <StatusPill status={status} />
      </span>
    </div>
  );
}

function MiniState({
  label,
  live,
  value,
}: {
  label: string;
  live: boolean;
  value?: string;
}) {
  return (
    <div className="rounded border border-slate-800/70 bg-slate-950/50 px-2 py-1">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={live ? "text-emerald-200" : "text-slate-500"}>
        {value ?? (live ? "configured" : "missing")}
      </div>
    </div>
  );
}

function ReadinessRow({ component }: { component: ComponentReadinessSnapshot }) {
  const notBuilt = component.status === "not_built";
  return (
    <div
      className={`rounded border border-slate-800/70 bg-slate-900/35 p-2 text-[11px] ${
        notBuilt ? "opacity-60" : ""
      }`}
    >
      <div className="mb-1 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className={`truncate font-medium ${notBuilt ? "italic text-slate-300" : "text-slate-100"}`}>
            {componentLabel(component.component_id)}
          </div>
          <div className="truncate font-mono text-[10px] text-slate-600">{component.component_id}</div>
        </div>
        <StatusPill status={component.status} />
      </div>
      <div className="line-clamp-2 text-slate-500">{component.detail}</div>
      {component.available_after ? (
        <div className="mt-1 text-[10px] uppercase tracking-wide text-slate-600">
          Available after {component.available_after}
        </div>
      ) : null}
    </div>
  );
}
