import type { ProviderHealthSnapshot } from "@/api/types";

import { KeyValueGrid } from "./KeyValueGrid";

interface Props {
  /** Today the per-trust-domain LLM route info is sourced from the global
      `provider_health` snapshot. P14 will land per-instance metadata. */
  provider: ProviderHealthSnapshot;
  trustDomainLabel: string;
}

export function LlmRoutePanel({ provider, trustDomainLabel }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">
        Per-trust-domain LLM route observability. P14 wires the real provider /
        model / structured-output schema / last-request preview for each domain;
        P9b shows the redacted-presence checks that already exist.
      </p>
      <KeyValueGrid
        rows={[
          { label: "Trust domain", value: trustDomainLabel },
          {
            label: "Route configured",
            value: provider.litellm_configured ? "yes" : "no",
            tone: provider.litellm_configured ? "good" : "muted",
          },
          {
            label: "Gemini key",
            value: provider.gemini_api_key_present ? "present" : "absent",
            tone: provider.gemini_api_key_present ? "good" : "muted",
          },
          {
            label: "OpenRouter key",
            value: provider.openrouter_api_key_present ? "present" : "absent",
            tone: provider.openrouter_api_key_present ? "good" : "muted",
          },
          {
            label: "Secret values",
            value: provider.secret_values,
            tone: "good",
          },
        ]}
      />
      <p className="text-[10px] text-slate-500">
        Available after: P14 (Lobster Trap pack + LiteLLM verdict adapter).
      </p>
    </div>
  );
}
