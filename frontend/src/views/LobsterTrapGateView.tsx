import { LobsterTrapGateCard } from "@/components/attack/LobsterTrapGateCard";
import { useSystem } from "@/api/hooks";
import { ModelRoutePanel } from "@/components/inspector/ModelRoutePanel";
import { StatusPill } from "@/components/StatusPill";

const MODEL_ROUTE_ORIGINS = [
  {
    id: "A1",
    label: "A1 monitor",
    detail: "Optional alert-summary model use after local privacy checks.",
  },
  {
    id: "A2",
    label: "A2 investigator",
    detail: "Can use a model to draft narrow hash-only Section 314(b) questions.",
  },
  {
    id: "F2",
    label: "F2 graph fallback",
    detail: "Uses deterministic graph rules first; model fallback sees DP summaries only.",
  },
  {
    id: "F4",
    label: "F4 SAR drafter",
    detail: "Uses the model for narrative wording from validated facts and provenance.",
  },
];

const ROUTE_STEPS = [
  {
    label: "Agent",
    detail: "A model-using node creates a bounded prompt from approved inputs.",
  },
  {
    label: "Lobster Trap",
    detail: "The local policy gate blocks prompt injection and raw-data requests.",
  },
  {
    label: "LiteLLM",
    detail: "The local route/proxy sends a schema-bound request to the provider.",
  },
  {
    label: "Provider",
    detail: "Gemini/OpenRouter receives only narrowed, policy-checked content.",
  },
];

const JUDGE_GATE_SUMMARY = [
  "Sender proof decides whether policy should even run.",
  "Lobster Trap/F6 blocks unsafe prompt content before LiteLLM sees it.",
  "Schema, route, and silo rules still decide whether the target may act.",
];

const POLICY_RULES = [
  {
    id: "Sender proof",
    label: "Unsigned / wrong-role",
    detail: "Unsigned requests stop at signature; wrong-role requests stop at allowlist.",
  },
  {
    id: "F6-B1",
    label: "Prompt injection",
    detail: "Blocks jailbreaks, policy bypasses, hidden prompt requests, and encoded evasion.",
  },
  {
    id: "F6-B2",
    label: "Private data extraction",
    detail: "Blocks raw customer, account, transaction, SSN, API-key, or private-key requests.",
  },
  {
    id: "F6-B4",
    label: "Evidence fabrication",
    detail: "Blocks invented hashes, fabricated findings, and prompts to make a case look stronger.",
  },
  {
    id: "F6-REDACT",
    label: "Customer-name redaction",
    detail: "Redacts recognized demo customer names when redaction is enough and blocking is not needed.",
  },
  {
    id: "F6-B3/B4",
    label: "Role and route shape",
    detail: "Checks that A1, A2, F1, A3, and local contribution messages follow their allowed routes.",
  },
  {
    id: "F6-B5/B6/B7/B8",
    label: "Envelope security",
    detail: "Blocks replayed nonces, bad signatures, disallowed principals, and invalid envelopes.",
  },
  {
    id: "F6-B9",
    label: "314(b) purpose",
    detail: "Requires declared AML authority and suspicion rationale for governed federation requests.",
  },
  {
    id: "F6-RATE",
    label: "Rate advisory",
    detail: "Escalates when an investigator exceeds the configured hourly Section 314(b) query threshold.",
  },
  {
    id: "Live LT",
    label: "Proxy base policy",
    detail: "The live proxy also carries generic harm, malware, phishing, exfiltration, PII, and egress rules.",
  },
];

export function LobsterTrapGateView() {
  const system = useSystem();
  const providerHealth = system.data?.provider_health ?? null;

  return (
    <div className="flex flex-col gap-3">
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.85fr)]">
          <div>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
                Lobster Trap gate
              </h2>
              <span className="text-[11px] text-slate-500">
                Prompt policy check before model execution
              </span>
            </div>
            <p className="mt-1 max-w-4xl text-[11px] leading-5 text-slate-400">
              Send normal or malicious prompts through the same Lobster Trap gate that
              protects model-bound nodes. Sender proof controls whether the request reaches
              policy; prompt text controls whether policy allows it onward.
            </p>
            <p className="mt-2 max-w-4xl text-[11px] leading-5 text-slate-400">
              Lobster Trap is a policy checkpoint in front of model calls. It proves that a
              prompt can be blocked for governance reasons before any LLM can follow
              malicious instructions or expose private data.
            </p>
          </div>
          <ul className="grid gap-1.5 sm:grid-cols-3 xl:grid-cols-1">
            {JUDGE_GATE_SUMMARY.map((item) => (
              <li
                key={item}
                className="rounded border border-slate-800 bg-slate-900/50 px-2 py-1.5 text-[11px] leading-5 text-slate-300"
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>
      <LobsterTrapGateCard />
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Rules demonstrated here
          </h3>
          <span className="text-[11px] text-slate-500">
            Crypto first, content second, component authority last
          </span>
        </div>
        <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-5">
          {POLICY_RULES.map((rule) => (
            <div
              key={rule.id}
              className="rounded border border-slate-800 bg-slate-900/50 p-2"
            >
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-[10px] font-semibold text-sky-200">
                  {rule.id}
                </span>
                <span className="text-[11px] font-semibold text-slate-100">
                  {rule.label}
                </span>
              </div>
              <p className="mt-1 text-[11px] leading-5 text-slate-400">{rule.detail}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
              Model route map
            </h3>
            <span className="text-[11px] text-slate-500">
              Agent to local LT to LiteLLM to provider
            </span>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-4">
            {ROUTE_STEPS.map((step, index) => (
              <div
                key={step.label}
                className="relative rounded border border-slate-800 bg-slate-900/50 p-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    Step {index + 1}
                  </span>
                  {index === 1 ? <StatusPill label="gate" /> : null}
                </div>
                <div className="mt-1 text-xs font-semibold text-slate-100">{step.label}</div>
                <p className="mt-1 text-[11px] leading-5 text-slate-400">{step.detail}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {MODEL_ROUTE_ORIGINS.map((origin) => (
              <div
                key={origin.id}
                className="rounded border border-sky-900/60 bg-sky-500/5 p-2"
              >
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[10px] font-semibold text-sky-200">
                    {origin.id}
                  </span>
                  <span className="text-xs font-semibold text-slate-100">{origin.label}</span>
                </div>
                <p className="mt-1 text-[11px] leading-5 text-slate-400">{origin.detail}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-200">
            Provider health
          </h3>
          {providerHealth ? (
            <ModelRoutePanel providerHealth={providerHealth} />
          ) : (
            <p className="text-[11px] text-slate-500">Loading model-route health.</p>
          )}
        </div>
      </section>
    </div>
  );
}
