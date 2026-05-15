import { Activity, FlaskConical, Network, Route } from "lucide-react";
import type { AppTab } from "../App";

const tabs: Array<{ id: AppTab; label: string; icon: typeof Network }> = [
  { id: "console", label: "Console", icon: Network },
  { id: "attack-lab", label: "Attack Lab", icon: FlaskConical },
  { id: "llm-route", label: "LLM Routes", icon: Route },
  { id: "system", label: "System", icon: Activity },
];

type Props = {
  active: AppTab;
  onChange: (tab: AppTab) => void;
};

export function TabBar({ active, onChange }: Props) {
  return (
    <nav className="flex gap-1 rounded-lg border border-slate-700 bg-slate-950 p-1">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const selected = active === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
              selected
                ? "bg-sky-500 text-slate-950"
                : "text-slate-300 hover:bg-slate-800 hover:text-white"
            }`}
          >
            <Icon size={16} aria-hidden />
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}
