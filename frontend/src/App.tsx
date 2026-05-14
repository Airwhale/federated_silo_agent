import { useEffect, useMemo, useState } from "react";

import type { ComponentId } from "@/api/types";
import { InspectorDrawer } from "@/components/InspectorDrawer";
import { SessionContext } from "@/components/SessionContext";
import { TabBar, type TabId, TABS } from "@/components/TabBar";
import type { TrustDomain } from "@/domain/instances";
import { AttackLabView } from "@/views/AttackLabView";
import { ConsoleView } from "@/views/ConsoleView";
import { LlmRouteView } from "@/views/LlmRouteView";
import { SystemView } from "@/views/SystemView";

const HASH_TO_TAB: Record<string, TabId> = Object.fromEntries(
  TABS.map((t) => [t.href, t.id]),
);

function parseHashTab(): TabId {
  const tab = HASH_TO_TAB[window.location.hash];
  return tab ?? "console";
}

export function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selection, setSelection] = useState<{
    domain: TrustDomain;
    componentId: ComponentId;
  } | null>(null);
  const [tab, setTab] = useState<TabId>(parseHashTab);

  useEffect(() => {
    function onHashChange() {
      setTab(parseHashTab());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const ctx = useMemo(
    () => ({ sessionId, setSessionId, selection, setSelection }),
    [sessionId, selection],
  );

  return (
    <SessionContext.Provider value={ctx}>
      <div className="flex h-full flex-col">
        <header className="flex items-baseline justify-between border-b border-slate-800 bg-slate-950/80 px-4 py-2">
          <div className="flex items-baseline gap-3">
            <h1 className="text-sm font-semibold text-slate-100">
              Federated Silo Agent · Judge Console
            </h1>
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              P9b
            </span>
          </div>
          <p className="text-[11px] text-slate-500">
            Read-only observability + safe probes. Polish lands with P18.
          </p>
        </header>
        <TabBar active={tab} onSelect={setTab} />
        <main className="min-h-0 flex-1">
          {tab === "console" ? <ConsoleView /> : null}
          {tab === "attack-lab" ? <AttackLabView /> : null}
          {tab === "llm-route" ? <LlmRouteView /> : null}
          {tab === "system" ? <SystemView /> : null}
        </main>
        <InspectorDrawer />
      </div>
    </SessionContext.Provider>
  );
}
