import { ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { describeError } from "@/api/errors";
import { useProbe } from "@/api/hooks";
import type { AttackerProfile, ComponentId, ProbeResult } from "@/api/types";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";
import { TRUST_INSTANCES, componentLabel, type TrustDomain } from "@/domain/instances";
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

export function ProbeForm({ config }: Props) {
  const { sessionId } = useSessionContext();
  const [instanceId, setInstanceId] = useState<TrustDomain>(config.defaultInstance);
  const [componentId, setComponentId] = useState<ComponentId>(config.defaultComponent);
  const [attackerProfile, setAttackerProfile] =
    useState<AttackerProfile>(config.defaultProfile);
  const [payloadText, setPayloadText] = useState(config.payload ?? "");
  const [lastResult, setLastResult] = useState<ProbeResult | null>(null);
  const mutation = useProbe(sessionId);

  const instance = TRUST_INSTANCES.find((item) => item.id === instanceId) ?? TRUST_INSTANCES[0];
  const allowedComponents = useMemo(() => instance.mechanisms, [instance]);
  const visibleComponentId = allowedComponents.some((item) => item.componentId === componentId)
    ? componentId
    : allowedComponents[0]?.componentId ?? config.defaultComponent;

  return (
    <article className="flex min-h-[420px] flex-col rounded-lg border border-slate-800 bg-slate-950 p-4">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-white">{config.label}</h3>
          <p className="mt-1 text-xs text-slate-400">{config.summary}</p>
        </div>
        <code className="shrink-0 rounded-md bg-slate-900 px-2 py-1 text-[10px] text-slate-500">
          {config.probeKind}
        </code>
      </header>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatusPill label={config.expectedLayer} />
        {config.availableAfter ? <StatusPill status="not_built" label={config.availableAfter} /> : null}
      </div>

      <div className="mt-4 grid gap-2">
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="grid gap-1 text-xs text-slate-400">
            Target instance
            <select
              value={instanceId}
              onChange={(event) => {
                const next = event.target.value as TrustDomain;
                const nextInstance =
                  TRUST_INSTANCES.find((item) => item.id === next) ?? TRUST_INSTANCES[0];
                setInstanceId(next);
                setComponentId(nextInstance.mechanisms[0]?.componentId ?? config.defaultComponent);
              }}
              className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
            >
              {TRUST_INSTANCES.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="grid gap-1 text-xs text-slate-400">
            Component
            <select
              value={visibleComponentId}
              onChange={(event) => setComponentId(event.target.value as ComponentId)}
              className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
            >
              {allowedComponents.map((item) => (
                <option key={`${item.id}-${item.componentId}`} value={item.componentId}>
                  {componentLabel(item.componentId)}
                </option>
              ))}
            </select>
          </label>

          <label className="grid gap-1 text-xs text-slate-400">
            Profile
            <select
              value={attackerProfile}
              onChange={(event) => setAttackerProfile(event.target.value as AttackerProfile)}
              className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm text-slate-100"
            >
              {ATTACKER_PROFILES.map((item) => (
                <option key={item} value={item}>
                  {item.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        </div>

        {config.acceptsPayload ? (
          <textarea
            value={payloadText}
            onChange={(event) => setPayloadText(event.target.value)}
            maxLength={4096}
            className="min-h-24 resize-y rounded-md border border-slate-700 bg-slate-900 p-3 text-sm text-slate-100"
            placeholder={config.payload ?? "Probe payload"}
          />
        ) : null}

        <button
          type="button"
          disabled={!sessionId || mutation.isPending}
          onClick={() =>
            mutation.mutate(
              {
                probe_kind: config.probeKind,
                target_component: visibleComponentId,
                attacker_profile: attackerProfile,
                payload_text: config.acceptsPayload ? payloadText.trim() || undefined : undefined,
                target_instance_id: instanceId,
              },
              {
                onSuccess: (result) => setLastResult(result),
              },
            )
          }
          className="inline-flex items-center justify-center gap-2 rounded-md bg-rose-500 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ShieldAlert size={16} aria-hidden />
          {mutation.isPending ? "Launching" : "Launch Probe"}
        </button>
      </div>

      {mutation.error instanceof Error ? (
        <div className="mt-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-100">
          {describeError(mutation.error)}
        </div>
      ) : null}

      <div className="mt-4">
        <ProbeResultCard result={lastResult} />
      </div>
    </article>
  );
}
