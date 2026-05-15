import { Play, Plus, RotateCw, StepForward } from "lucide-react";
import { DEFAULT_SESSION_CREATE } from "@/api/client";
import { useCreateSession, useRunUntilIdle, useStepSession } from "@/api/hooks";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";

export function RunControls() {
  const { session, setSessionId } = useSessionContext();
  const createSession = useCreateSession();
  const stepSession = useStepSession(session?.session_id ?? null);
  const runUntilIdle = useRunUntilIdle(session?.session_id ?? null);

  const disabled = !session;

  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-950 px-4 py-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold text-white">Federated Silo Console</h1>
          {session ? <StatusPill status="live" label={session.phase} /> : null}
        </div>
        <p className="mt-1 truncate text-sm text-slate-400">
          {session ? `${session.scenario_id} - ${session.session_id}` : "No active session"}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            createSession.mutate(
              DEFAULT_SESSION_CREATE,
              {
                onSuccess: (created) => setSessionId(created.session_id),
              },
            );
          }}
          className="inline-flex items-center gap-2 rounded-md bg-sky-500 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-sky-400"
        >
          <Plus size={16} aria-hidden />
          New
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => stepSession.mutate()}
          className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <StepForward size={16} aria-hidden />
          Step
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => runUntilIdle.mutate()}
          className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Play size={16} aria-hidden />
          Idle
        </button>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-100 hover:bg-slate-800"
        >
          <RotateCw size={16} aria-hidden />
          Refresh
        </button>
      </div>
    </section>
  );
}
