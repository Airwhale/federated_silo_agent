import { useCaseNotebookReport, useGenerateCaseNotebook } from "@/api/hooks";
import { CaseReportPanel, type ReportKind } from "@/components/reports/CaseReportPanel";
import { useSessionContext } from "@/components/SessionContext";

type Props = {
  kind: ReportKind;
};

export function CaseReportView({ kind }: Props) {
  const { sessionId } = useSessionContext();
  const report = useCaseNotebookReport(sessionId);
  const generate = useGenerateCaseNotebook(sessionId);
  const activeReport = generate.data ?? report.data;
  const error = generate.error ?? report.error;

  return (
    <section className="min-w-0 rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/70 px-3 py-2">
        <div>
          <h1 className="text-sm font-semibold uppercase tracking-wide text-slate-100">
            {kind === "notebook" ? "Notebook page" : "Artifact page"}
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            A separate report page for judge review. Generate runs the current demo path if needed,
            then refreshes this HTML from sanitized federation artifacts.
          </p>
        </div>
      </header>
      <div className="p-3">
        <CaseReportPanel
          activeKind={kind}
          report={activeReport}
          pending={generate.isPending || report.isPending}
          error={error}
          disabled={!sessionId}
          heightClass="h-[calc(100vh-15rem)] min-h-[560px]"
          showKindTabs={false}
          showPageLinks={false}
          onGenerate={() => generate.mutate()}
        />
      </div>
    </section>
  );
}
