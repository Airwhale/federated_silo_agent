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
      <header className="sticky top-0 z-20 border-b border-slate-800 bg-slate-950/95 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] flex-wrap items-center justify-between gap-3">
          <TabBar active={activeTab} onChange={onTabChange} />
          <div className="text-xs text-slate-500">P9b structural console</div>
        </div>
      </header>
      <main className="mx-auto flex max-w-[1800px] flex-col gap-4 px-4 py-4">
        <RunControls />
        {children}
      </main>
    </div>
  );
}
