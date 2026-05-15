import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useComponent } from "@/api/hooks";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";
import { AuditChainPanel } from "@/components/inspector/AuditChainPanel";
import { DpLedgerPanel } from "@/components/inspector/DpLedgerPanel";
import { EnvelopePanel } from "@/components/inspector/EnvelopePanel";
import { GenericFieldsPanel } from "@/components/inspector/GenericFieldsPanel";
import { NotBuiltPanel } from "@/components/inspector/NotBuiltPanel";
import { ProviderHealthPanel } from "@/components/inspector/ProviderHealthPanel";
import { RawJsonPanel } from "@/components/inspector/RawJsonPanel";
import { ReplayPanel } from "@/components/inspector/ReplayPanel";
import { RouteApprovalPanel } from "@/components/inspector/RouteApprovalPanel";
import { SigningPanel } from "@/components/inspector/SigningPanel";
import { trustDomainLabel } from "@/domain/instances";

export function InspectorDrawer() {
  const { sessionId, selection, setSelection } = useSessionContext();
  const component = useComponent(
    sessionId,
    selection?.componentId ?? "F1",
    selection?.instanceId,
  );
  const snapshot = component.data;

  return (
    <Dialog.Root open={Boolean(selection)} onOpenChange={(open) => !open && setSelection(null)}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/70" />
        <Dialog.Content className="fixed right-0 top-0 z-50 flex h-full w-full max-w-xl flex-col border-l border-slate-800 bg-slate-950 shadow-2xl">
          {/*
            Compact drawer header: title + inline trust-domain badge +
            status pill + close button on one row. Dropped the previous
            ``Output: ...`` helper paragraph (the panels below already
            show what's available; the helper read as filler).
          */}
          <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-3 py-2">
            <div className="flex min-w-0 items-baseline gap-2">
              <Dialog.Title className="truncate text-sm font-semibold text-slate-100">
                {snapshot?.title ?? selection?.componentId ?? "Inspector"}
              </Dialog.Title>
              <Dialog.Description className="truncate text-[11px] uppercase tracking-wide text-slate-500">
                {selection?.instanceId ? trustDomainLabel(selection.instanceId) : "Global component"}
              </Dialog.Description>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {snapshot ? <StatusPill status={snapshot.status} /> : null}
              <Dialog.Close
                className="rounded border border-slate-800 p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                aria-label="Close inspector"
              >
                <X size={14} aria-hidden />
              </Dialog.Close>
            </div>
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto p-3 scrollbar-thin">
            {!snapshot ? (
              <div className="rounded-lg border border-slate-800 p-3 text-xs text-slate-500">
                Snapshot loading.
              </div>
            ) : (
              <>
                <NotBuiltPanel snapshot={snapshot} />
                <SigningPanel snapshot={snapshot} />
                <EnvelopePanel snapshot={snapshot} />
                <ReplayPanel snapshot={snapshot} />
                <RouteApprovalPanel snapshot={snapshot} />
                <DpLedgerPanel snapshot={snapshot} />
                <ProviderHealthPanel snapshot={snapshot} />
                <AuditChainPanel snapshot={snapshot} />
                <GenericFieldsPanel snapshot={snapshot} />
                <RawJsonPanel value={snapshot} />
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
