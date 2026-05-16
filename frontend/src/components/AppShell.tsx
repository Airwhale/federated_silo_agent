import type { ReactNode } from "react";
import type { AppTab } from "@/App";
import { RunControls } from "@/components/RunControls";
import { TabBar } from "@/components/TabBar";

type Props = {
  activeTab: AppTab;
  onTabChange: (tab: AppTab) => void;
  children: ReactNode;
};

export function AppShell({
  activeTab,
  onTabChange,
  children,
}: Props) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/*
        Single dense header row. Left: identity + tab bar. Right:
        scenario / mode / action buttons / session badge. Folding the
        former separate ``RunControls`` section into the header
        reclaims ~64px of vertical space for the main content (topology
        and timeline are the real story), and gives the console a
        single-glance "what session am I on, what scenario, what
        actions are available" strip that judges can read without
        scanning.

        The container intentionally drops the previous ``max-w-[1800px]``
        cap. At a 1920x1080 demo viewport the cap left ~120px of dead
        margin on each side; an operations console should fill the
        screen.
      */}
      <header className="sticky top-0 z-20 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
          <AppIdentity />
          <TabBar active={activeTab} onChange={onTabChange} />
          <RunControls />
        </div>
      </header>
      <main className="flex flex-col gap-3 px-4 py-3">
        {children}
      </main>
    </div>
  );
}

function AppIdentity() {
  return (
    <div className="flex items-center gap-2 pr-2">
      {/*
        Brand mark + name. The "ƒ" is a single-glyph identity for the
        Federated Silo Agent demo -- short, unique, and renders fine
        without a custom font asset. The full project name lives next
        to it for the (rare) case a viewer doesn't recognize the mark.
      */}
      <span className="grid h-7 w-7 place-items-center rounded border border-emerald-400/40 bg-emerald-500/10 font-serif text-base font-bold leading-none text-emerald-200">
        ƒ
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-[11px] font-semibold uppercase tracking-[0.15em] text-slate-300">
          Federated Silo Agent
        </span>
        <span className="text-[10px] uppercase tracking-wide text-slate-500">
          AML cross-bank demo
        </span>
      </span>
    </div>
  );
}
