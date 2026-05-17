import { Send, Shuffle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { describeError, isUnknownSessionError } from "@/api/errors";
import { useInteraction } from "@/api/hooks";
import type { AttackerProfile, ComponentId, ComponentInteractionKind, ComponentSnapshot } from "@/api/types";
import { ComponentGuidancePanel } from "@/components/inspector/ComponentGuidancePanel";
import { KeyValueGrid } from "@/components/inspector/KeyValueGrid";
import { RawJsonPanel } from "@/components/inspector/RawJsonPanel";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";
import { fieldGuidance } from "@/domain/fieldGuidance";
import { TRUST_INSTANCES, type TrustDomain } from "@/domain/instances";
import {
  firstSampleForInteraction,
  nextSample,
  samplesForComponent,
} from "@/domain/sampleInputs";

// Hardcoded to a known core component instead of indexing TRUST_INSTANCES
// at module load. If the registry is ever misconfigured with an empty
// instance, the UI should still render and report the interaction through
// a valid component endpoint rather than crashing during import.
const FALLBACK_COMPONENT_ID: ComponentId = "F1";
const PROMPT_NORMAL_COMPONENTS = new Set<ComponentId>(["A1", "A2", "F2", "F4", "litellm"]);
const PROMPT_INTERACTION_KINDS: ComponentInteractionKind[] = [
  "prompt",
  "safe_input",
  "inspect",
  "explain_state",
];
const READ_ONLY_INTERACTION_KINDS: ComponentInteractionKind[] = [
  "inspect",
  "explain_state",
];
const isInteractionDestination = (componentId: ComponentId) => componentId !== "lobster_trap";
const interactionKindsForComponent = (componentId: ComponentId) =>
  PROMPT_NORMAL_COMPONENTS.has(componentId)
    ? PROMPT_INTERACTION_KINDS
    : READ_ONLY_INTERACTION_KINDS;
const attackerProfiles: { value: AttackerProfile; label: string }[] = [
  { value: "valid_but_malicious", label: "Signed" },
  { value: "unknown", label: "Unsigned" },
  { value: "wrong_role", label: "Wrong role" },
];

type SnapshotResultPanelProps = {
  snapshot: ComponentSnapshot;
};

function SnapshotResultPanel({ snapshot }: SnapshotResultPanelProps) {
  const fieldRows = (snapshot.fields ?? []).map((field) => {
    const value = field.redacted ? "[redacted]" : String(field.value);
    const guidance = fieldGuidance(snapshot.component_id, field.name, value);
    return {
      label: field.name,
      value,
      tone: guidance.dangerous
        ? ("danger" as const)
        : field.redacted
          ? ("muted" as const)
          : ("default" as const),
      help: guidance.help,
    };
  });

  return (
    <div className="mt-2 space-y-2 rounded border border-slate-800/80 bg-slate-950/70 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Returned snapshot
        </span>
        <StatusPill status={snapshot.status} />
        <span className="text-xs text-slate-300">{snapshot.title}</span>
      </div>
      <ComponentGuidancePanel snapshot={snapshot} />
      <KeyValueGrid
        rows={[
          { label: "Component", value: snapshot.component_id },
          ...fieldRows,
        ]}
      />
      <RawJsonPanel value={snapshot} />
    </div>
  );
}

export function InteractionConsole() {
  const { sessionId, recoverSession } = useSessionContext();
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
  const [payloadText, setPayloadText] = useState(() =>
    "",
  );
  const [attackerProfile, setAttackerProfile] =
    useState<AttackerProfile>("valid_but_malicious");
  const [routeThroughLobsterTrap, setRouteThroughLobsterTrap] = useState(true);
  const interaction = useInteraction(sessionId, componentId);
  const sampleSet = samplesForComponent(componentId);
  const normalSampleAction: ComponentInteractionKind = PROMPT_NORMAL_COMPONENTS.has(componentId)
    ? "prompt"
    : "inspect";
  const attackSampleAction: ComponentInteractionKind = "prompt";
  const validInteractionKinds = useMemo(
    () => interactionKindsForComponent(componentId),
    [componentId],
  );
  const supportsPromptInput = validInteractionKinds.includes("prompt");
  const normalSample = sampleSet.normal[0] ?? "";
  const attackSample = sampleSet.attack[0] ?? "";
  const payloadEnabled = interactionKind === "prompt" || interactionKind === "safe_input";
  const components = useMemo(
    () => instance.mechanisms.filter((mechanism) => isInteractionDestination(mechanism.componentId)),
    [instance],
  );

  // Reset mutation state and seed a relevant sample when the selected
  // component or interaction mode changes. Without this, stale result
  // badges and stale sample text bleed into the next target.
  useEffect(() => {
    interaction.reset();
    if (!validInteractionKinds.includes(interactionKind)) {
      setInteractionKind(validInteractionKinds[0] ?? "inspect");
      return;
    }
    setPayloadText(payloadEnabled ? firstSampleForInteraction(componentId, interactionKind) : "");
    // ``interaction.reset`` is stable per hook instance; including the
    // full mutation object would loop across renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [componentId, interactionKind, payloadEnabled, validInteractionKinds]);

  useEffect(() => {
    if (isUnknownSessionError(interaction.error)) {
      interaction.reset();
      recoverSession();
    }
    // ``interaction.reset`` is stable per hook instance; including the
    // full mutation object would loop across renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interaction.error, recoverSession]);

  useEffect(() => {
    if (!components.some((mechanism) => mechanism.componentId === componentId)) {
      setComponentId(components[0]?.componentId ?? FALLBACK_COMPONENT_ID);
    }
  }, [componentId, components]);

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
        <div className="grid gap-2 lg:grid-cols-6">
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
              setComponentId(
                nextInstance.mechanisms.find((mechanism) =>
                  isInteractionDestination(mechanism.componentId),
                )?.componentId
                ?? firstMechanism?.componentId
                ?? FALLBACK_COMPONENT_ID,
              );
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
            {validInteractionKinds.map((kind) => (
              <option key={kind} value={kind}>
                {kind.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <select
            value={attackerProfile}
            onChange={(event) => setAttackerProfile(event.target.value as AttackerProfile)}
            className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs"
            title="Controls whether the interaction has cryptographic sender proof."
          >
            {attackerProfiles.map((profile) => (
              <option key={profile.value} value={profile.value}>
                {profile.label}
              </option>
            ))}
          </select>
          <label
            className="flex items-center justify-center gap-1.5 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-200"
            title="When enabled, prompt text is policy-scanned before it can reach a model or typed target."
          >
            <input
              type="checkbox"
              checked={routeThroughLobsterTrap}
              onChange={(event) => setRouteThroughLobsterTrap(event.target.checked)}
              className="h-3 w-3 accent-sky-400"
            />
            LT gate
          </label>
          <button
            type="button"
            disabled={!sessionId || interaction.isPending}
            onClick={() =>
              interaction.mutate({
                interaction_kind: interactionKind,
                payload_text: payloadEnabled ? payloadText.trim() || undefined : undefined,
                target_instance_id: instanceId,
                attacker_profile: attackerProfile,
                route_through_lobster_trap: routeThroughLobsterTrap,
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
          disabled={!payloadEnabled}
          maxLength={4096}
          rows={3}
          className="w-full resize-y rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-[11px] text-slate-100 disabled:cursor-not-allowed disabled:opacity-55"
          placeholder={payloadEnabled ? "Demo-safe input" : "Read-only action: payload is ignored"}
        />
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => {
              interaction.reset();
              setInteractionKind(normalSampleAction);
              setAttackerProfile("valid_but_malicious");
              setRouteThroughLobsterTrap(true);
              setPayloadText(
                normalSampleAction === "prompt"
                  ? sampleSet.normal.includes(payloadText)
                    ? nextSample(payloadText, sampleSet.normal)
                    : normalSample
                  : "",
              );
            }}
            aria-label="Use normal interaction sample"
            className="inline-flex items-center gap-1 rounded border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-[10px] font-medium text-emerald-200 hover:bg-emerald-500/20"
          >
            <Shuffle size={11} aria-hidden />
            Normal sample
          </button>
          <button
            type="button"
            disabled={!supportsPromptInput}
            onClick={() => {
              interaction.reset();
              setInteractionKind(attackSampleAction);
              setAttackerProfile("valid_but_malicious");
              setRouteThroughLobsterTrap(true);
              setPayloadText(
                attackSampleAction === "prompt" || attackSampleAction === "safe_input"
                  ? sampleSet.attack.includes(payloadText)
                    ? nextSample(payloadText, sampleSet.attack)
                    : attackSample
                  : "",
              );
            }}
            aria-label="Use attack interaction sample"
            title={supportsPromptInput ? "Use attack interaction sample" : "Select a graph node or edge on Demo Flow for mapped security probes"}
            className="inline-flex items-center gap-1 rounded border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] font-medium text-rose-200 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Shuffle size={11} aria-hidden />
            Attack sample
          </button>
        </div>
        {interaction.data ? (
          <div className="rounded border border-slate-800/70 bg-slate-900/40 px-2.5 py-1.5 text-xs">
            <div className="flex flex-wrap items-center gap-1.5">
              <StatusPill status={interaction.data.status} />
              {interaction.data.blocked_by ? <StatusPill layer={interaction.data.blocked_by} /> : null}
              {interaction.data.accepted && !interaction.data.executed ? (
                <span
                  className="inline-flex items-center rounded border border-amber-400/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-200"
                  title="Recorded but not executed by this component."
                >
                  Not executed
                </span>
              ) : null}
              {interaction.data.accepted && interaction.data.executed ? (
                <span className="inline-flex items-center rounded border border-emerald-400/40 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-200">
                  Executed
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-slate-300">{interaction.data.reason}</p>
            {interaction.data.component_snapshot ? (
              <SnapshotResultPanel snapshot={interaction.data.component_snapshot} />
            ) : null}
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
