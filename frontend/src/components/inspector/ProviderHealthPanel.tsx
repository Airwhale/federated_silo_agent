import type { ProviderHealthSnapshot } from "@/api/types";

import { KeyValueGrid } from "./KeyValueGrid";

interface Props {
  data: ProviderHealthSnapshot;
}

function YesNo({ value }: { value: boolean }) {
  return (
    <span className={value ? "text-emerald-300" : "text-slate-500"}>
      {value ? "yes" : "no"}
    </span>
  );
}

export function ProviderHealthPanel({ data }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">{data.detail}</p>
      <KeyValueGrid
        rows={[
          {
            label: "Lobster Trap configured",
            value: <YesNo value={data.lobster_trap_configured} />,
          },
          {
            label: "LiteLLM configured",
            value: <YesNo value={data.litellm_configured} />,
          },
          {
            label: "Gemini API key present",
            value: <YesNo value={data.gemini_api_key_present} />,
          },
          {
            label: "OpenRouter API key present",
            value: <YesNo value={data.openrouter_api_key_present} />,
          },
          {
            label: "Secret values",
            value: data.secret_values,
            tone: "good",
          },
        ]}
      />
    </div>
  );
}
