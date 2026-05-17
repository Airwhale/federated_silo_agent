import { Activity, MonitorPlay, Network, ShieldCheck } from "lucide-react";
import type { AppTab } from "../App";

const tabs: Array<{ id: AppTab; label: string; icon: typeof Network }> = [
  { id: "demo-flow", label: "Demo Flow", icon: MonitorPlay },
  { id: "console", label: "Console", icon: Network },
  { id: "lobster-trap", label: "Lobster Trap", icon: ShieldCheck },
  { id: "system", label: "System", icon: Activity },
];

type Props = {
  active: AppTab;
  onChange: (tab: AppTab) => void;
};

export function TabBar({ active, onChange }: Props) {
  return (
    <nav className="flex items-center gap-0.5" aria-label="Console views">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const selected = active === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            aria-current={selected ? "page" : undefined}
            // Tighter padding (px-2.5 py-1) and a stronger active state
            // (filled emerald-tinted background instead of just an
            // underline) so the active view reads at a glance from the
            // demo distance. Unselected text uses slate-300 (was
            // slate-400) for better legibility on the near-black
            // header backdrop.
            className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium uppercase tracking-wide transition-colors ${
              selected
                ? "bg-emerald-500/15 text-emerald-200"
                : "text-slate-300 hover:bg-slate-800/70 hover:text-slate-100"
            }`}
          >
            <Icon size={13} aria-hidden />
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}
