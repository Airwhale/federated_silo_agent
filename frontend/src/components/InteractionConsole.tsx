import { Send } from "lucide-react";
import { useMemo, useState } from "react";
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

export function InteractionConsole() {
  const { sessionId } = useSessionContext();
  const [instanceId, setInstanceId] = useState<TrustDomain>("federation");
  const instance = TRUST_INSTANCES.find((item) => item.id === instanceId) ?? TRUST_INSTANCES[1];
  const [componentId, setComponentId] = useState<ComponentId>(instance.mechanisms[0].componentId);
  const [interactionKind, setInteractionKind] =
    useState<ComponentInteractionKind>("inspect");
  const [payloadText, setPayloadText] = useState("");
  const interaction = useInteraction(sessionId, componentId);

  const components = useMemo(() => instance.mechanisms, [instance]);

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-white">Interaction Console</h2>
        {interaction.data ? <StatusPill status={interaction.data.status} /> : null}
      </div>
      <div className="mt-3 grid gap-2 lg:grid-cols-4">
        <select
          value={instanceId}
          onChange={(event) => {
            const next = event.target.value as TrustDomain;
            const nextInstance = TRUST_INSTANCES.find((item) => item.id === next) ?? TRUST_INSTANCES[0];
            setInstanceId(next);
            setComponentId(nextInstance.mechanisms[0].componentId);
          }}
          className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
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
          className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
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
          className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
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
          className="inline-flex items-center justify-center gap-2 rounded-md bg-sky-500 px-3 py-2 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send size={16} aria-hidden />
          Submit
        </button>
      </div>
      <textarea
        value={payloadText}
        onChange={(event) => setPayloadText(event.target.value)}
        maxLength={4096}
        className="mt-2 min-h-24 w-full resize-y rounded-md border border-slate-700 bg-slate-900 p-3 text-sm text-slate-100"
        placeholder="Demo-safe input"
      />
      {interaction.data ? (
        <div className="mt-3 rounded-md border border-slate-800 bg-slate-900 p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={interaction.data.status} />
            {interaction.data.blocked_by ? <StatusPill layer={interaction.data.blocked_by} /> : null}
            {interaction.data.accepted && !interaction.data.executed ? (
              <span
                className="inline-flex items-center rounded-md border border-amber-400/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-200"
                title="Recorded but not executed — live handler lands with P14/P15"
              >
                Placeholder ({interaction.data.available_after ?? "P14/P15"})
              </span>
            ) : null}
            {interaction.data.accepted && interaction.data.executed ? (
              <span className="inline-flex items-center rounded-md border border-emerald-400/40 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-200">
                Executed
              </span>
            ) : null}
          </div>
          <p className="mt-2 text-slate-300">{interaction.data.reason}</p>
        </div>
      ) : null}
      {interaction.error instanceof Error ? (
        <div className="mt-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-100">
          {describeError(interaction.error)}
        </div>
      ) : null}
    </section>
  );
}
