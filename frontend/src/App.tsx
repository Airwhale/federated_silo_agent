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

const tabFromHash = (): AppTab => {
  const value = window.location.hash.replace(/^#\/?/, "");
  if (value === "attack-lab" || value === "llm-route" || value === "system") {
    return value;
  }
  return "console";
};

export function App() {
  const [activeTab, setActiveTab] = useState<AppTab>(tabFromHash);
  const [sessionId, setSessionId] = useState<string | null>(() =>
    window.localStorage.getItem("federated_silo_session_id"),
  );
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
          window.localStorage.setItem("federated_silo_session_id", created.session_id);
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
    if (nextSessionId) {
      window.localStorage.setItem("federated_silo_session_id", nextSessionId);
    } else {
      window.localStorage.removeItem("federated_silo_session_id");
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
