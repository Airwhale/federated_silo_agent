import type { SessionMode } from "@/api/types";

interface Props {
  scenarioId: string;
  mode: SessionMode;
  onScenarioChange: (id: string) => void;
  onModeChange: (m: SessionMode) => void;
  disabled?: boolean;
}

const SCENARIOS: readonly { id: string; label: string }[] = [
  { id: "s1_structuring_ring", label: "S1 — Structuring ring (hero)" },
  { id: "s2_layering", label: "S2 — Layering chain" },
  { id: "s3_sanctions_evasion", label: "S3 — Sanctions evasion" },
] as const;

const MODES: readonly { id: SessionMode; label: string }[] = [
  { id: "stub", label: "Stub (deterministic)" },
  { id: "live", label: "Live (Gemini)" },
  { id: "live_with_stub_fallback", label: "Live w/ stub fallback" },
] as const;

export function ScenarioSelector({
  scenarioId,
  mode,
  onScenarioChange,
  onModeChange,
  disabled,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <label className="flex items-center gap-2 text-slate-300">
        <span className="text-xs uppercase tracking-wide text-slate-500">Scenario</span>
        <select
          value={scenarioId}
          onChange={(e) => onScenarioChange(e.target.value)}
          disabled={disabled}
          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:opacity-50"
        >
          {SCENARIOS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2 text-slate-300">
        <span className="text-xs uppercase tracking-wide text-slate-500">Mode</span>
        <select
          value={mode}
          onChange={(e) => onModeChange(e.target.value as SessionMode)}
          disabled={disabled}
          className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 disabled:opacity-50"
        >
          {MODES.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
