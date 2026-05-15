import { useState } from "react";
import { DEFAULT_SESSION_CREATE } from "@/api/client";
import { describeError } from "@/api/errors";
import { useCreateSession, useRunUntilIdle, useStepSession } from "@/api/hooks";
import type { SessionMode } from "@/api/types";
import { ScenarioSelector } from "@/components/ScenarioSelector";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";

/**
 * Header-friendly run controls. Renders inline in the AppShell header row
 * rather than as a separate full-width section -- reclaims vertical space
 * for the main content (topology, timeline) where the demo's actual story
 * lives. The control strip exposes scenario + mode pickers, the three
 * session actions (Reset / Step / Run-until-idle), the live session
 * badge with truncated UUID, and an inline error indicator when the most
 * recent mutation failed. Auxiliary "Refresh" button removed; the
 * browser's own reload handles that and the button was confusing next to
 * the agent-step actions.
 */
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
    <div className="ml-auto flex flex-wrap items-center gap-3 text-xs">
      <ScenarioSelector
        scenarioId={scenarioId}
        mode={mode}
        disabled={busy}
        onScenarioChange={setScenarioId}
        onModeChange={setMode}
      />
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={disabled || busy}
          onClick={() => stepSession.mutate()}
          // Primary action: Step. Filled emerald so it reads as the
          // canonical "advance the demo" button. Run-until-idle and
          // Reset are secondary (outline-only) so the action hierarchy
          // is visible at a glance.
          className="inline-flex items-center gap-1 rounded border border-emerald-500/60 bg-emerald-500/20 px-2.5 py-1 font-medium text-emerald-100 hover:bg-emerald-500/30 disabled:cursor-not-allowed disabled:opacity-40"
          title="Advance the session by one agent turn"
        >
          Step
        </button>
        <button
          type="button"
          disabled={disabled || busy}
          onClick={() => runUntilIdle.mutate()}
          className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800/60 px-2.5 py-1 font-medium text-slate-100 hover:bg-slate-700/80 disabled:cursor-not-allowed disabled:opacity-40"
          title="Run agent turns until the orchestrator reports idle"
        >
          Run
        </button>
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
          className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800/60 px-2.5 py-1 font-medium text-slate-200 hover:bg-slate-700/80 disabled:cursor-not-allowed disabled:opacity-50"
          title={session ? "Discard the current session and start a new one" : "Create a session against the selected scenario"}
        >
          {session ? "Reset" : "Create"}
        </button>
      </div>
      <div className="flex items-center gap-1.5 border-l border-slate-800 pl-3">
        <span className="text-[10px] uppercase tracking-wide text-slate-500">Session</span>
        {session ? (
          <>
            <StatusPill status="live" label={session.phase} />
            <code
              className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-200"
              title={session.session_id}
            >
              {session.session_id.slice(0, 8)}
            </code>
          </>
        ) : (
          <span className="text-slate-500">none</span>
        )}
      </div>
      {lastError ? (
        // Inline error indicator. The full error text is on the title
        // attribute so the header strip stays compact; if a judge needs
        // the full message they can hover. Detailed-error rendering
        // belongs in the relevant view (e.g. AttackLabView surfaces
        // probe failures inline next to the probe form).
        <span
          className="flex items-center gap-1 rounded border border-rose-400/40 bg-rose-500/10 px-2 py-0.5 text-[11px] font-medium text-rose-200"
          title={describeError(lastError)}
        >
          API error
        </span>
      ) : null}
    </div>
  );
}
