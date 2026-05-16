import { ShieldAlert, Shuffle } from "lucide-react";
import { useMemo, useState } from "react";
import { describeError } from "@/api/errors";
import { useProbe } from "@/api/hooks";
import type { AttackerProfile, ComponentId, ProbeResult } from "@/api/types";
import { FieldLabel } from "@/components/forms/FieldLabel";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";
import { TRUST_INSTANCES, componentLabel, type TrustDomain } from "@/domain/instances";
import { nextSample } from "@/domain/sampleInputs";
import type { ProbeDefinition } from "./ProbeRegistry";
import { ProbeResultCard } from "./ProbeResultCard";

type Props = {
  config: ProbeDefinition;
};

const ATTACKER_PROFILES: AttackerProfile[] = [
  "valid_but_malicious",
  "unknown",
  "wrong_role",
];

const BUSINESS_COMPONENTS = new Set<ComponentId>([
  "A1",
  "A2",
  "F1",
  "F2",
  "F3",
  "F4",
  "F5",
  "bank_alpha.A3",
  "bank_beta.A3",
  "bank_gamma.A3",
  "P7",
]);

function targetComponentForProbe(
  defaultComponent: ComponentId,
  businessTarget: ComponentId,
  policyGateEnabled: boolean | null,
): ComponentId {
  if (policyGateEnabled !== null) {
    return policyGateEnabled ? "lobster_trap" : "litellm";
  }
  if (
    defaultComponent === "bank_alpha.A3"
    || defaultComponent === "bank_beta.A3"
    || defaultComponent === "bank_gamma.A3"
  ) {
    return businessTarget;
  }
  return defaultComponent;
}

export function ProbeForm({ config }: Props) {
  const { sessionId } = useSessionContext();
  const [instanceId, setInstanceId] = useState<TrustDomain>(config.defaultInstance);
  const [businessTarget, setBusinessTarget] = useState<ComponentId>(config.defaultBusinessTarget);
  const [runThroughLobsterTrap, setRunThroughLobsterTrap] = useState(
    Boolean(config.policyGateToggle),
  );
  const [attackerProfile, setAttackerProfile] =
    useState<AttackerProfile>(config.defaultProfile);
  const normalPayloads = config.normalPayloads ?? [];
  const attackPayloads = config.attackPayloads ?? (config.payload ? [config.payload] : []);
  const [payloadText, setPayloadText] = useState(
    config.payload ?? attackPayloads[0] ?? normalPayloads[0] ?? "",
  );
  const [lastResult, setLastResult] = useState<ProbeResult | null>(null);
  const mutation = useProbe(sessionId);

  const instance = TRUST_INSTANCES.find((item) => item.id === instanceId) ?? TRUST_INSTANCES[0];
  const allowedComponents = useMemo(() => {
    return instance.mechanisms.filter((item) => {
      const allowedByProbe =
        !config.businessTargets || config.businessTargets.includes(item.componentId);
      return allowedByProbe && BUSINESS_COMPONENTS.has(item.componentId);
    });
  }, [config.businessTargets, instance]);
  const visibleBusinessTarget = allowedComponents.some((item) => item.componentId === businessTarget)
    ? businessTarget
    : allowedComponents[0]?.componentId ?? config.defaultBusinessTarget;
  const targetComponent = targetComponentForProbe(
    config.defaultComponent,
    visibleBusinessTarget,
    config.policyGateToggle ? runThroughLobsterTrap : null,
  );

  return (
    <article className="flex flex-col rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex items-start justify-between gap-2 border-b border-slate-800/70 px-3 py-2">
        <div className="min-w-0">
          <h3 className="truncate text-xs font-semibold uppercase tracking-wide text-slate-200">
            {config.label}
          </h3>
          <p className="mt-0.5 text-[11px] text-slate-500">{config.summary}</p>
        </div>
        <code className="shrink-0 rounded bg-slate-900 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
          {config.probeKind}
        </code>
      </header>

      <div className="flex flex-col gap-2 p-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-wide text-slate-500">Expected</span>
          <StatusPill label={config.expectedLayer} />
          {config.availableAfter ? <StatusPill status="not_built" label={config.availableAfter} /> : null}
        </div>

        {/*
          Three-up control row at sm+, stacked on narrow. Each control
          carries a tiny uppercase label so the form is scannable
          without focus-tabbing through every field.
        */}
        <div className="grid gap-2 sm:grid-cols-3">
          <FieldLabel label="Target instance">
            <select
              value={instanceId}
              onChange={(event) => {
                const next = event.target.value as TrustDomain;
                const nextInstance =
                  TRUST_INSTANCES.find((item) => item.id === next) ?? TRUST_INSTANCES[0];
                setInstanceId(next);
                const nextBusinessTarget = nextInstance.mechanisms.find(
                  (mechanism) =>
                    BUSINESS_COMPONENTS.has(mechanism.componentId)
                    && (!config.businessTargets
                      || config.businessTargets.includes(mechanism.componentId)),
                );
                setBusinessTarget(nextBusinessTarget?.componentId ?? config.defaultBusinessTarget);
              }}
              className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100"
            >
              {TRUST_INSTANCES.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </FieldLabel>

          <FieldLabel label="Business target">
            <select
              value={visibleBusinessTarget}
              onChange={(event) => setBusinessTarget(event.target.value as ComponentId)}
              className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100"
            >
              {allowedComponents.map((item) => (
                <option key={`${item.id}-${item.componentId}`} value={item.componentId}>
                  {componentLabel(item.componentId)}
                </option>
              ))}
            </select>
          </FieldLabel>

          <FieldLabel label="Profile">
            <select
              value={attackerProfile}
              onChange={(event) => setAttackerProfile(event.target.value as AttackerProfile)}
              className="rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-100"
            >
              {ATTACKER_PROFILES.map((item) => (
                <option key={item} value={item}>
                  {item.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </FieldLabel>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
          <div className="mb-1.5 flex items-baseline justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Protection stage
            </span>
            <span className="text-[10px] text-slate-600">
              not a destination
            </span>
          </div>
          <label className="flex gap-2 rounded border border-slate-800/70 bg-slate-950/70 px-2 py-1.5 text-[10px] text-slate-300">
            <input
              type="checkbox"
              checked={config.policyGateToggle ? runThroughLobsterTrap : true}
              disabled={!config.policyGateToggle}
              onChange={(event) => setRunThroughLobsterTrap(event.target.checked)}
              className="mt-0.5 h-3.5 w-3.5 rounded border-slate-600 bg-slate-950 text-sky-400 disabled:opacity-50"
            />
            <span>
              <span className="block font-medium text-slate-200">{config.stageLabel}</span>
              <span className="block text-slate-500">{config.stageDescription}</span>
            </span>
          </label>
          <div className="mt-1.5 text-[10px] text-slate-500">
            Backend probe target: <code className="text-slate-300">{targetComponent}</code>
          </div>
        </div>

        {config.acceptsPayload ? (
          <>
            <textarea
              value={payloadText}
              onChange={(event) => setPayloadText(event.target.value)}
              maxLength={4096}
              rows={3}
              className="resize-y rounded border border-slate-700 bg-slate-900 px-2 py-1.5 font-mono text-[11px] text-slate-100"
              placeholder={config.payload ?? "Probe payload"}
            />
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setPayloadText(nextSample(payloadText, normalPayloads))}
                disabled={normalPayloads.length === 0}
                aria-label={`Use normal sample for ${config.label}`}
                className="inline-flex items-center gap-1 rounded border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-[10px] font-medium text-emerald-200 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Shuffle size={11} aria-hidden />
                Normal sample
              </button>
              <button
                type="button"
                onClick={() => setPayloadText(nextSample(payloadText, attackPayloads))}
                disabled={attackPayloads.length === 0}
                aria-label={`Use attack sample for ${config.label}`}
                className="inline-flex items-center gap-1 rounded border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] font-medium text-rose-200 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Shuffle size={11} aria-hidden />
                Attack sample
              </button>
            </div>
          </>
        ) : null}

        <button
          type="button"
          disabled={!sessionId || mutation.isPending}
          onClick={() =>
            mutation.mutate(
              {
                probe_kind: config.probeKind,
                target_component: targetComponent,
                attacker_profile: attackerProfile,
                payload_text: config.acceptsPayload ? payloadText.trim() || undefined : undefined,
                target_instance_id: instanceId,
              },
              {
                onSuccess: (result) => setLastResult(result),
              },
            )
          }
          // Outline-only rose styling -- still reads as "this is an
          // attack" via the icon + rose hue, but doesn't shout like a
          // marketing CTA. Restrained per the ops-console polish
          // brief.
          className="inline-flex items-center justify-center gap-1.5 self-start rounded border border-rose-400/50 bg-rose-500/10 px-3 py-1 text-xs font-medium text-rose-200 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ShieldAlert size={12} aria-hidden />
          {mutation.isPending ? "Launching" : "Launch probe"}
        </button>
      </div>

      {mutation.error instanceof Error ? (
        <div className="mx-3 mb-3 rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-100">
          {describeError(mutation.error)}
        </div>
      ) : null}

      <div className="border-t border-slate-800/70 p-3">
        <ProbeResultCard result={lastResult} />
      </div>
    </article>
  );
}

