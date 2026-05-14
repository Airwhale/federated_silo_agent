import * as Dialog from "@radix-ui/react-dialog";

import { useComponent } from "@/api/hooks";
import { describeError } from "@/api/errors";
import { labelFor } from "@/lib/componentLabels";
import { TRUST_DOMAIN_LABELS } from "@/lib/trustDomainLabels";

import { useSessionContext } from "./SessionContext";
import { StatusPill } from "./StatusPill";
import { AuditChainPanel } from "./inspector/AuditChainPanel";
import { DpLedgerPanel } from "./inspector/DpLedgerPanel";
import { EnvelopePanel } from "./inspector/EnvelopePanel";
import { GenericFieldsPanel } from "./inspector/GenericFieldsPanel";
import { LlmRoutePanel } from "./inspector/LlmRoutePanel";
import { NotBuiltPanel } from "./inspector/NotBuiltPanel";
import { ProviderHealthPanel } from "./inspector/ProviderHealthPanel";
import { RawJsonPanel } from "./inspector/RawJsonPanel";
import { ReplayPanel } from "./inspector/ReplayPanel";
import { RouteApprovalPanel } from "./inspector/RouteApprovalPanel";
import { SigningPanel } from "./inspector/SigningPanel";

export function InspectorDrawer() {
  const { sessionId, selection, setSelection } = useSessionContext();
  const open = selection !== null;

  const query = useComponent(
    sessionId,
    selection ? selection.componentId : null,
  );

  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && setSelection(null)}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm data-[state=open]:animate-in" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-slate-800 bg-slate-950 shadow-xl">
          {selection ? (
            <>
              <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
                <div className="flex flex-col">
                  <Dialog.Title className="text-base font-semibold text-slate-100">
                    {labelFor(selection.componentId)}
                  </Dialog.Title>
                  <Dialog.Description className="text-xs text-slate-500">
                    {TRUST_DOMAIN_LABELS[selection.domain]} ·{" "}
                    <code className="font-mono">{selection.componentId}</code>
                  </Dialog.Description>
                </div>
                {query.data ? <StatusPill status={query.data.status} /> : null}
                <Dialog.Close
                  className="ml-3 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700"
                  aria-label="Close inspector"
                >
                  Close
                </Dialog.Close>
              </header>

              <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
                {query.isLoading && !query.data ? (
                  <p className="text-xs text-slate-500">Loading snapshot…</p>
                ) : query.error ? (
                  <p className="text-xs text-rose-300">
                    Could not load — {describeError(query.error)}
                  </p>
                ) : query.data ? (
                  <>
                    {query.data.status === "not_built" ? (
                      <NotBuiltPanel detail={query.data.title} />
                    ) : null}
                    {query.data.signing ? <SigningPanel data={query.data.signing} /> : null}
                    {query.data.envelope ? (
                      <EnvelopePanel data={query.data.envelope} />
                    ) : null}
                    {query.data.replay ? <ReplayPanel data={query.data.replay} /> : null}
                    {query.data.route_approval ? (
                      <RouteApprovalPanel data={query.data.route_approval} />
                    ) : null}
                    {query.data.dp_ledger ? (
                      <DpLedgerPanel data={query.data.dp_ledger} />
                    ) : null}
                    {query.data.provider_health ? (
                      selection.componentId === "litellm" ? (
                        <LlmRoutePanel
                          provider={query.data.provider_health}
                          trustDomainLabel={TRUST_DOMAIN_LABELS[selection.domain]}
                        />
                      ) : (
                        <ProviderHealthPanel data={query.data.provider_health} />
                      )
                    ) : null}
                    {query.data.audit_chain ? (
                      <AuditChainPanel data={query.data.audit_chain} />
                    ) : null}
                    {/* Fall through to generic fields if the snapshot carries
                        only `fields[]` (no dedicated nested panel). */}
                    {!query.data.signing &&
                    !query.data.envelope &&
                    !query.data.replay &&
                    !query.data.route_approval &&
                    !query.data.dp_ledger &&
                    !query.data.provider_health &&
                    !query.data.audit_chain &&
                    query.data.status !== "not_built" ? (
                      <GenericFieldsPanel fields={query.data.fields} />
                    ) : null}

                    <RawJsonPanel data={query.data} />
                  </>
                ) : null}
              </div>
            </>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
