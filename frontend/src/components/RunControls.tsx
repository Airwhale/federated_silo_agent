import { useState } from "react";
import { DEFAULT_SESSION_CREATE } from "@/api/client";
import { describeError } from "@/api/errors";
import { useCreateSession, useRunUntilIdle, useStepSession } from "@/api/hooks";
import type { SessionMode } from "@/api/types";
import { ScenarioSelector } from "@/components/ScenarioSelector";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";

export function RunControls() {
  const { session, setSessionId } = useSessionContext();
  const [scenarioId, setScenarioId] = useState(DEFAULT_SESSION_CREATE.scenario_id);
  const [mode, setMode] = useState<SessionMode>(DEFAULT_SESSION_CREATE.mode);
  const createSession = useCreateSession();
  const stepSession = useStepSession(session?.session_id ?? null);
  const runUntilIdle = useRunUntilIdle(session?.session_id ?? null);
  const busy = createSession.isPending || stepSession.isPending || runUntilIdle.isPending;
  const lastError = createSession.error ?? stepSession.error ?? runUntilIdle.error ?? null;

  const disabled = !session;

  return (
    <section className="flex flex-col gap-2 border border-slate-800 bg-slate-900/40 px-3 py-2">
      <div className="flex flex-wrap items-center gap-3">
        <ScenarioSelector
          scenarioId={scenarioId}
          mode={mode}
          disabled={busy}
          onScenarioChange={setScenarioId}
          onModeChange={setMode}
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              createSession.mutate(
                { scenario_id: scenarioId, mode },
                {
                  onSuccess: (created) => setSessionId(created.session_id),
                },
              );
            }}
            className="rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-sm font-medium text-emerald-200 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {session ? "Reset session" : "Create session"}
          </button>
          <button
            type="button"
            disabled={disabled || busy}
            onClick={() => stepSession.mutate()}
            className="rounded border border-slate-700 bg-slate-800/70 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-700/70 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Step
          </button>
          <button
            type="button"
            disabled={disabled || busy}
            onClick={() => runUntilIdle.mutate()}
            className="rounded border border-slate-700 bg-slate-800/70 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-700/70 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Run until idle
          </button>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded border border-slate-700 bg-slate-800/70 px-3 py-1.5 text-sm font-medium text-slate-100 hover:bg-slate-700/70"
          >
            Refresh
          </button>
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <span className="uppercase tracking-wide text-slate-500">Session</span>
          {session ? <StatusPill status="live" label={session.phase} /> : null}
          {session ? (
            <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-200">
              {session.session_id.slice(0, 8)}
            </code>
          ) : (
            <span className="text-slate-500">none</span>
          )}
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Input: choose scenario and mode, then create, step, or run. Output: the session badge shows phase and run id.
      </p>
      {lastError ? (
        <p className="text-xs font-medium text-rose-300">
          <span className="uppercase tracking-wide text-rose-400">API said:</span>{" "}
          {describeError(lastError)}
        </p>
      ) : null}
    </section>
  );
}
