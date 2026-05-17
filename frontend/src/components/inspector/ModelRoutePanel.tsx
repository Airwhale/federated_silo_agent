import type { ProviderHealthSnapshot } from "@/api/types";
import { KeyValueGrid, type KeyValueRow } from "@/components/inspector/KeyValueGrid";

type Props = {
  providerHealth: ProviderHealthSnapshot;
  trustDomainLabel?: string;
  lastResult?: string;
};

export function ModelRoutePanel({ providerHealth, trustDomainLabel, lastResult }: Props) {
  const configured = providerHealth.lobster_trap_configured && providerHealth.litellm_configured;
  const keySummary = credentialSummary(providerHealth);
  const rows: KeyValueRow[] = [];
  if (trustDomainLabel) {
    rows.push({ label: "Trust domain", value: trustDomainLabel });
  }
  rows.push(
    {
      label: "Route state",
      value: providerHealth.status === "live" ? "LT and model proxy reachable" : "configuration incomplete",
      tone: providerHealth.status === "live" ? "good" : "muted",
    },
    {
      label: "Lobster Trap",
      value: providerHealth.lobster_trap_configured ? "configured" : "missing",
      tone: providerHealth.lobster_trap_configured ? "good" : "muted",
    },
    {
      label: "LiteLLM proxy",
      value: providerHealth.litellm_configured ? "configured" : "missing",
      tone: providerHealth.litellm_configured ? "good" : "muted",
    },
    {
      label: "Model credentials",
      value: keySummary,
      tone: keySummary === "none reported" ? "muted" : "good",
    },
    {
      label: "Secret values",
      value: providerHealth.secret_values,
      tone: "good",
    },
  );
  if (lastResult) {
    rows.push({ label: "Last interaction", value: lastResult });
  }
  rows.push(
    {
      label: "Live adapter",
      value: providerHealth.status === "live" ? "live local route checks enabled" : "waiting for local proxy reachability",
      tone: providerHealth.status === "live" ? "good" : "muted",
    },
  );

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px] text-slate-400">{providerHealth.detail}</p>
      <KeyValueGrid rows={rows} />
    </div>
  );
}

function credentialSummary(providerHealth: ProviderHealthSnapshot): string {
  const providers = [
    providerHealth.gemini_api_key_present ? "Gemini" : null,
    providerHealth.openrouter_api_key_present ? "OpenRouter" : null,
  ].filter(Boolean);
  return providers.length > 0 ? `${providers.join(", ")} present` : "none reported";
}
