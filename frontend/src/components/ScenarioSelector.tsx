import type { SessionMode } from "@/api/types";

type Props = {
  scenarioId: string;
  mode: SessionMode;
  disabled?: boolean;
  onScenarioChange: (scenarioId: string) => void;
  onModeChange: (mode: SessionMode) => void;
};

const SCENARIOS: { id: string; label: string }[] = [
  { id: "s1_structuring_ring", label: "S1: Structuring ring" },
  { id: "s2_layering", label: "S2: Layering chain" },
  { id: "s3_sanctions_evasion", label: "S3: Sanctions evasion" },
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
