import { useState } from "react";

import { useCreateSession, useRunUntilIdle, useStepSession } from "@/api/hooks";
import type { SessionMode } from "@/api/types";
import { describeError } from "@/api/errors";

import { ScenarioSelector } from "./ScenarioSelector";
import { useSessionContext } from "./SessionContext";

export function RunControls() {
  const { sessionId, setSessionId } = useSessionContext();
  const [scenarioId, setScenarioId] = useState("s1_structuring_ring");
  const [mode, setMode] = useState<SessionMode>("stub");

  const create = useCreateSession();
  const step = useStepSession();
  const runIdle = useRunUntilIdle();

  const lastError =
    create.error ?? step.error ?? runIdle.error ?? null;

  const busy = create.isPending || step.isPending || runIdle.isPending;

  return (
    <section className="flex flex-col gap-3 border-b border-slate-800 bg-slate-900/40 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <ScenarioSelector
          scenarioId={scenarioId}
          mode={mode}
          onScenarioChange={setScenarioId}
          onModeChange={setMode}
          disabled={busy}
        />
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              create.mutate(
                { scenario_id: scenarioId, mode },
                { onSuccess: (snap) => setSessionId(snap.session_id) },
              )
            }
            className="rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-sm font-medium text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {sessionId ? "Reset session" : "Create session"}
          </button>
          <button
            type="button"
            disabled={!sessionId || busy}
            onClick={() => sessionId && step.mutate(sessionId)}
            className="rounded border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-700/60 disabled:opacity-40"
          >
            Step
          </button>
          <button
            type="button"
            disabled={!sessionId || busy}
            onClick={() => sessionId && runIdle.mutate(sessionId)}
            className="rounded border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-700/60 disabled:opacity-40"
          >
            Run until idle
          </button>
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span className="uppercase tracking-wide text-slate-500">Session</span>
          {sessionId ? (
            <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-200">
              {sessionId.slice(0, 8)}
            </code>
          ) : (
            <span className="text-slate-500">none</span>
          )}
        </div>
      </div>
      {lastError ? (
        <p className="text-xs font-medium text-rose-300">
          <span className="uppercase tracking-wide text-rose-400">API said:</span>{" "}
          {describeError(lastError)}
        </p>
      ) : null}
    </section>
  );
}
