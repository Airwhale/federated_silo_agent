import { useEffect, useMemo, useState } from "react";
import { DEFAULT_SESSION_CREATE } from "@/api/client";
import { describeError } from "@/api/errors";
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
    if (sessionId || createSession.isPending || createSession.data) return;
    createSession.mutate(
      DEFAULT_SESSION_CREATE,
      {
        onSuccess: (created) => {
          setSessionId(created.session_id);
          try {
            window.localStorage.setItem(SESSION_STORAGE_KEY, created.session_id);
          } catch {
            // Private mode / file:// origin — session lives only for this tab.
          }
        },
      },
    );
  }, [createSession, sessionId]);

  const activeSession = useMemo(() => session.data ?? createSession.data ?? null, [
    createSession.data,
    session.data,
  ]);

  const changeTab = (tab: AppTab) => {
    window.location.hash = `/${tab}`;
    setActiveTab(tab);
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
