import { useEffect, useMemo, useState } from "react";
import { DEFAULT_SESSION_CREATE } from "@/api/client";
import { ApiError, describeError } from "@/api/errors";
import { useCreateSession, useSession } from "@/api/hooks";
import { AppShell } from "@/components/AppShell";
import { InspectorDrawer } from "@/components/InspectorDrawer";
import { SessionContext, type InspectorSelection } from "@/components/SessionContext";
import { AttackLabView } from "@/views/AttackLabView";
import { ConsoleView } from "@/views/ConsoleView";
import { LlmRouteView } from "@/views/LlmRouteView";
import { SystemView } from "@/views/SystemView";

export type AppTab = "console" | "attack-lab" | "llm-route" | "system";

const SESSION_STORAGE_KEY = "federated_silo_session_id";
// Match the UUID shape FastAPI emits (uuid4 in canonical hyphenated form).
// A stricter regex (UUID v4 only) is overkill; this just guards against
// corrupted or hand-edited localStorage values fetching `/sessions/garbage`
// and producing a confusing 404 on first paint.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const tabFromHash = (): AppTab => {
  const value = window.location.hash.replace(/^#\/?/, "");
  if (value === "attack-lab" || value === "llm-route" || value === "system") {
    return value;
  }
  return "console";
};

const readStoredSessionId = (): string | null => {
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (raw && UUID_RE.test(raw)) {
      return raw;
    }
    if (raw) {
      // Corrupted or stale (e.g. from a different server instance). Drop
      // it now so the create-session effect can run with a clean slate.
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  } catch {
    // localStorage can throw in private-mode Safari, file:// origins, etc.
    // Falling back to a fresh session is the right behavior.
  }
  return null;
};

export function App() {
  const [activeTab, setActiveTab] = useState<AppTab>(tabFromHash);
  const [sessionId, setSessionId] = useState<string | null>(readStoredSessionId);
  const [selection, setSelection] = useState<InspectorSelection | null>(null);
  const createSession = useCreateSession();
  const session = useSession(sessionId);

  useEffect(() => {
    const listener = () => setActiveTab(tabFromHash());
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);

  useEffect(() => {
    // Only attempt to create a session when the mutation is in its
    // initial ``idle`` state. The previous guard
    // (``!isPending && !data``) let the effect re-fire after a failed
    // mutation: the mutation object is a fresh reference once
    // ``error`` is set, the dependency array detects that, and without
    // ``data`` to short-circuit the guard the effect calls
    // ``mutate`` again, looping indefinitely when the backend is down
    // on first load. ``status === "idle"`` is true exactly once before
    // any call, so we attempt at most one session creation per page
    // load and the user sees ``createSession.error`` rather than a
    // network-tab fire-hose.
    if (sessionId || createSession.status !== "idle") return;
    createSession.mutate(
      DEFAULT_SESSION_CREATE,
      {
        onSuccess: (created) => {
          setSessionId(created.session_id);
          try {
            window.localStorage.setItem(SESSION_STORAGE_KEY, created.session_id);
          } catch {
            // Private mode or file origin: session lives only for this tab.
          }
        },
      },
    );
  }, [createSession, sessionId]);

  // Recover from a stale ``sessionId`` in localStorage. If the server was
  // restarted, the in-memory session table was cleared and the stored UUID
  // now 404s. Without this effect ``sessionId`` stays truthy, the
  // create-session effect above stays gated off, and the UI is stuck on a
  // dead session. Detect the 404 from ``useSession`` and clear the stored
  // ID, which lets the create-session effect run on the next render.
  useEffect(() => {
    if (session.error instanceof ApiError && session.error.status === 404) {
      try {
        window.localStorage.removeItem(SESSION_STORAGE_KEY);
      } catch {
        // localStorage unavailable; state clear below is enough.
      }
      setSessionId(null);
    }
  }, [session.error]);

  const activeSession = useMemo(() => session.data ?? createSession.data ?? null, [
    createSession.data,
    session.data,
  ]);

  const changeTab = (tab: AppTab) => {
    // Setting ``window.location.hash`` fires a synchronous ``hashchange``
    // event that the listener above picks up and dispatches
    // ``setActiveTab``. Calling ``setActiveTab`` here as well would
    // schedule a redundant render; the URL hash is the single source of
    // truth for the active tab and the listener is the sole writer.
    window.location.hash = `/${tab}`;
  };

  const setStoredSessionId = (nextSessionId: string | null) => {
    setSessionId(nextSessionId);
    try {
      if (nextSessionId) {
        window.localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
      } else {
        window.localStorage.removeItem(SESSION_STORAGE_KEY);
      }
    } catch {
      // See readStoredSessionId for the cases this guards.
    }
  };

  return (
    <SessionContext.Provider
      value={{
        sessionId: activeSession?.session_id ?? sessionId,
        session: activeSession,
        setSessionId: setStoredSessionId,
        selection,
        setSelection,
      }}
    >
      <AppShell activeTab={activeTab} onTabChange={changeTab}>
        {activeTab === "console" ? <ConsoleView /> : null}
        {activeTab === "attack-lab" ? <AttackLabView /> : null}
        {activeTab === "llm-route" ? <LlmRouteView /> : null}
        {activeTab === "system" ? <SystemView /> : null}
        {createSession.error instanceof Error ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
            {describeError(createSession.error)}
          </div>
        ) : null}
      </AppShell>
      <InspectorDrawer />
    </SessionContext.Provider>
  );
}
