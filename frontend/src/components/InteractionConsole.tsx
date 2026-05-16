import { Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { describeError } from "@/api/errors";
import { useInteraction } from "@/api/hooks";
import type { ComponentId, ComponentInteractionKind } from "@/api/types";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";
import { TRUST_INSTANCES, type TrustDomain } from "@/domain/instances";

const interactionKinds: ComponentInteractionKind[] = [
  "prompt",
  "inspect",
  "explain_state",
  "safe_input",
];

// Hardcoded to a known core component instead of indexing TRUST_INSTANCES
// at module load. If the registry is ever misconfigured with an empty
// instance, the UI should still render and report the interaction through
// a valid component endpoint rather than crashing during import.
const FALLBACK_COMPONENT_ID: ComponentId = "F1";

export function InteractionConsole() {
  const { sessionId } = useSessionContext();
  const [instanceId, setInstanceId] = useState<TrustDomain>("federation");
  // Fallback to ``TRUST_INSTANCES[0]`` for consistency with the
  // ``onChange`` handler below and with ``ProbeForm`` / other instance
  // selectors. The default state is ``"federation"`` and ``find`` will
  // hit; this branch only runs if the registry ever loses the federation
  // entry. Keeping all fallbacks aligned avoids surprising UX drift.
  const instance = TRUST_INSTANCES.find((item) => item.id === instanceId) ?? TRUST_INSTANCES[0];
  // Fall back to the first known instance's first mechanism if the chosen
  // instance somehow has none. The hardcoded ``TRUST_INSTANCES`` registry
  // guarantees at least one mechanism per instance today, but the dynamic
  // ``setComponentId`` call inside the instance ``onChange`` below has to
  // handle the empty case defensively, so we keep the initializer aligned
  // with that contract rather than crashing if the registry ever drifts.
  const [componentId, setComponentId] = useState<ComponentId>(
    instance.mechanisms[0]?.componentId ?? FALLBACK_COMPONENT_ID,
  );
  const [interactionKind, setInteractionKind] =
    useState<ComponentInteractionKind>("inspect");
  const [payloadText, setPayloadText] = useState("");
  const interaction = useInteraction(sessionId, componentId);

  // Reset mutation state (data/error chip in the header) when the
  // selected component changes. Without this, a stale "API said" /
  // "Executed" / "Placeholder" badge from a prior component bleeds
  // into the new component's view until the user fires another
  // interaction.
  useEffect(() => {
    interaction.reset();
    // ``interaction.reset`` is stable per hook instance; we only
    // want to fire on componentId change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [componentId]);

  const components = useMemo(() => instance.mechanisms, [instance]);

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-slate-800/70 px-3 py-2">
        <div className="flex items-baseline gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Interaction console
          </h2>
          <span className="text-[11px] text-slate-500">
            Target &times; action &times; optional payload &rarr; result + timeline event
          </span>
        </div>
        {interaction.data ? <StatusPill status={interaction.data.status} /> : null}
      </header>
      <div className="flex flex-col gap-2 p-3">
        <div className="grid gap-2 lg:grid-cols-4">
          <select
            value={instanceId}
            onChange={(event) => {
              const next = event.target.value as TrustDomain;
              const nextInstance = TRUST_INSTANCES.find((item) => item.id === next) ?? TRUST_INSTANCES[0];
              setInstanceId(next);
              // Guard against an instance with no mechanisms: ``[0]`` would
              // be ``undefined`` and the property access would throw a
              // TypeError at runtime. The registry is static today, but
              // the indirection keeps the component robust to drift.
              const firstMechanism = nextInstance.mechanisms[0];
              setComponentId(firstMechanism?.componentId ?? FALLBACK_COMPONENT_ID);
            }}
            className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs"
          >
            {TRUST_INSTANCES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <select
            value={componentId}
            onChange={(event) => setComponentId(event.target.value as ComponentId)}
            className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs"
          >
            {components.map((item) => (
              <option key={item.id} value={item.componentId}>
                {item.label}
              </option>
            ))}
          </select>
          <select
            value={interactionKind}
            onChange={(event) => setInteractionKind(event.target.value as ComponentInteractionKind)}
            className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs"
          >
            {interactionKinds.map((kind) => (
              <option key={kind} value={kind}>
                {kind.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!sessionId || interaction.isPending}
            onClick={() =>
              interaction.mutate({
                interaction_kind: interactionKind,
                payload_text: payloadText.trim() || undefined,
                target_instance_id: instanceId,
                attacker_profile: "valid_but_malicious",
              })
            }
            className="inline-flex items-center justify-center gap-1.5 rounded border border-sky-400/60 bg-sky-500/15 px-3 py-1 text-xs font-medium text-sky-100 hover:bg-sky-500/25 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Send size={12} aria-hidden />
            Submit
          </button>
        </div>
        <textarea
          value={payloadText}
          onChange={(event) => setPayloadText(event.target.value)}
          maxLength={4096}
          rows={3}
          className="w-full resize-y rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-[11px] text-slate-100"
          placeholder="Demo-safe input"
        />
        {interaction.data ? (
          <div className="rounded border border-slate-800/70 bg-slate-900/40 px-2.5 py-1.5 text-xs">
            <div className="flex flex-wrap items-center gap-1.5">
              <StatusPill status={interaction.data.status} />
              {interaction.data.blocked_by ? <StatusPill layer={interaction.data.blocked_by} /> : null}
              {interaction.data.accepted && !interaction.data.executed ? (
                <span
                  className="inline-flex items-center rounded border border-amber-400/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-200"
                  title="Recorded but not executed. Live handler lands with P14/P15"
                >
                  Placeholder ({interaction.data.available_after ?? "P14/P15"})
                </span>
              ) : null}
              {interaction.data.accepted && interaction.data.executed ? (
                <span className="inline-flex items-center rounded border border-emerald-400/40 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-200">
                  Executed
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-slate-300">{interaction.data.reason}</p>
          </div>
        ) : null}
        {interaction.error instanceof Error ? (
          <div className="rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-100">
            {describeError(interaction.error)}
          </div>
        ) : null}
      </div>
    </section>
  );
}
