export type TabId = "console" | "attack-lab" | "llm-route" | "system";

export const TABS: readonly { id: TabId; label: string; href: string }[] = [
  { id: "console", label: "Console", href: "#/console" },
  { id: "attack-lab", label: "Attack Lab", href: "#/attack-lab" },
  { id: "llm-route", label: "LLM Routes", href: "#/llm-route" },
  { id: "system", label: "System", href: "#/system" },
] as const;

interface Props {
  active: TabId;
  onSelect: (tab: TabId) => void;
}

export function TabBar({ active, onSelect }: Props) {
  return (
    <nav className="flex items-center gap-1 border-b border-slate-800 bg-slate-900/60 px-3">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => {
            onSelect(tab.id);
            window.location.hash = tab.href;
          }}
          className={
            "border-b-2 px-3 py-2 text-sm font-medium transition-colors " +
            (active === tab.id
              ? "border-emerald-400 text-emerald-300"
              : "border-transparent text-slate-400 hover:text-slate-200")
          }
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
