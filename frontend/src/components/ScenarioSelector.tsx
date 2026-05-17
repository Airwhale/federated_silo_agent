import type { SessionMode } from "@/api/types";

type Props = {
  scenarioId: string;
  mode: SessionMode;
  disabled?: boolean;
  onScenarioChange: (scenarioId: string) => void;
  onModeChange: (mode: SessionMode) => void;
};

const SCENARIOS: { id: string; label: string; description: string }[] = [
  {
    id: "s1_structuring_ring",
    label: "S1: Structuring ring",
    description: "Small repeated transfers across banks that may be designed to avoid reporting thresholds.",
  },
  {
    id: "s2_layering",
    label: "S2: Layering chain",
    description: "Funds move through several hops to obscure where the money came from.",
  },
  {
    id: "s3_sanctions_evasion",
    label: "S3: Sanctions evasion",
    description: "Activity may be routed around a screened or watchlisted party.",
  },
];

const MODES: { id: SessionMode; label: string }[] = [
  { id: "stub", label: "Stub" },
  { id: "live", label: "Live" },
  { id: "live_with_stub_fallback", label: "Live with fallback" },
];

export function ScenarioSelector({
  scenarioId,
  mode,
  disabled,
  onScenarioChange,
  onModeChange,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2 text-xs text-slate-500">
        <span className="uppercase tracking-wide">Scenario</span>
        <span className="group relative inline-flex">
          <button
            type="button"
            aria-label="Scenario descriptions"
            aria-describedby="scenario-help"
            className="grid h-5 w-5 place-items-center rounded-full border border-slate-700 bg-slate-900 text-[11px] font-semibold text-slate-300 hover:border-sky-400 hover:text-sky-100 focus:outline-none focus:ring-2 focus:ring-sky-400/50"
          >
            ?
          </button>
          <span
            id="scenario-help"
            role="tooltip"
            className="pointer-events-none absolute left-0 top-full z-50 mt-2 hidden w-80 rounded-lg border border-slate-700 bg-slate-950 p-3 text-left text-xs shadow-xl shadow-black/30 group-focus-within:block group-hover:block"
          >
            <span className="mb-2 block text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              Scenario guide
            </span>
            <span className="grid gap-2">
              {SCENARIOS.map((scenario) => (
                <span key={scenario.id} className="block">
                  <span className="block font-semibold text-slate-100">{scenario.label}</span>
                  <span className="block leading-snug text-slate-400">
                    {scenario.description}
                  </span>
                </span>
              ))}
            </span>
          </span>
        </span>
        <select
          value={scenarioId}
          disabled={disabled}
          onChange={(event) => onScenarioChange(event.target.value)}
          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100 disabled:opacity-50"
        >
          {SCENARIOS.map((scenario) => (
            <option key={scenario.id} value={scenario.id}>
              {scenario.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2 text-xs text-slate-500">
        <span className="uppercase tracking-wide">Mode</span>
        <select
          value={mode}
          disabled={disabled}
          onChange={(event) => onModeChange(event.target.value as SessionMode)}
          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100 disabled:opacity-50"
        >
          {MODES.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
