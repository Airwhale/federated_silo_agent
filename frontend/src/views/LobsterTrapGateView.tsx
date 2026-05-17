import { LobsterTrapGateCard } from "@/components/attack/LobsterTrapGateCard";

export function LobsterTrapGateView() {
  return (
    <div className="flex flex-col gap-3">
      <section className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Lobster Trap gate
          </h2>
          <span className="text-[11px] text-slate-500">
            Prompt policy check before model execution
          </span>
        </div>
        <p className="mt-1 max-w-4xl text-[11px] leading-5 text-slate-400">
          Use this page to send normal or malicious prompts through the same Lobster Trap
          gate that protects model-bound nodes. Sender proof controls whether the request
          reaches policy; the prompt text controls whether policy allows it onward.
        </p>
      </section>
      <LobsterTrapGateCard />
    </div>
  );
}
