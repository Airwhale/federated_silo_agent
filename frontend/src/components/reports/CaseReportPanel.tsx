import { BookOpen, Code2, ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import { describeError } from "@/api/errors";
import type { CaseNotebookReportSnapshot, SnapshotStatus } from "@/api/types";
import { StatusPill } from "@/components/StatusPill";

export type ReportKind = "notebook" | "artifacts";

type Props = {
  activeKind: ReportKind;
  report: CaseNotebookReportSnapshot | null | undefined;
  pending: boolean;
  error: unknown;
  disabled: boolean;
  heightClass?: string;
  showKindTabs?: boolean;
  showPageLinks?: boolean;
  onKindChange?: (kind: ReportKind) => void;
  onGenerate: () => void;
};

const FALLBACK_HTML = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><style>
body{margin:0;font-family:Inter,system-ui,sans-serif;background:#f8fafc;color:#0f172a}
main{padding:20px}section{margin-top:12px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;padding:14px}
p{color:#334155;line-height:1.55}
</style></head>
<body><main><h1>Case report preview</h1><section><p>Create a session or generate the report to load the notebook HTML.</p></section></main></body>
</html>`;

export function CaseReportPanel({
  activeKind,
  report,
  pending,
  error,
  disabled,
  heightClass = "h-[420px]",
  showKindTabs = true,
  showPageLinks = true,
  onKindChange,
  onGenerate,
}: Props) {
  const [showCode, setShowCode] = useState(false);
  const rawHtml =
    activeKind === "notebook"
      ? report?.notebook_html ?? FALLBACK_HTML
      : report?.artifact_html ?? FALLBACK_HTML;
  const html = useMemo(() => applyCodeVisibility(rawHtml, showCode), [rawHtml, showCode]);
  const status: SnapshotStatus = report?.status ?? (pending ? "pending" : "simulated");
  const path =
    activeKind === "notebook"
      ? report?.notebook_html_path
      : report?.artifact_html_path;

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/70 px-3 py-2">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            {activeKind === "notebook" ? "Notebook report" : "Artifact report"}
          </h2>
          <p className="text-[11px] text-slate-500">
            Static HTML generated from the federation-safe notebook and artifact bundle.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={status} label={report?.status === "live" ? "generated" : "sample"} />
          <label className="inline-flex items-center gap-1.5 rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200">
            <input
              type="checkbox"
              checked={showCode}
              onChange={(event) => setShowCode(event.target.checked)}
              className="h-3.5 w-3.5 accent-sky-400"
            />
            <Code2 size={13} aria-hidden />
            Show code
          </label>
          <button
            type="button"
            disabled={disabled || pending}
            onClick={onGenerate}
            className="inline-flex items-center gap-1.5 rounded border border-emerald-400/50 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-100 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <BookOpen size={13} aria-hidden />
            {pending ? "Generating" : "Generate report"}
          </button>
        </div>
      </header>
      <div className="space-y-2 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          {showKindTabs ? (
            <div className="grid grid-cols-2 gap-1 rounded-lg border border-slate-800 bg-slate-900/50 p-1 text-xs">
              <ReportTabButton
                label="Notebook HTML"
                active={activeKind === "notebook"}
                onClick={() => onKindChange?.("notebook")}
              />
              <ReportTabButton
                label="Artifact HTML"
                active={activeKind === "artifacts"}
                onClick={() => onKindChange?.("artifacts")}
              />
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            {showPageLinks ? (
              <>
                <a
                  href="#/notebook"
                  className="inline-flex items-center gap-1 rounded border border-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-800"
                >
                  Notebook page
                  <ExternalLink size={11} aria-hidden />
                </a>
                <a
                  href="#/artifacts"
                  className="inline-flex items-center gap-1 rounded border border-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-800"
                >
                  Artifact page
                  <ExternalLink size={11} aria-hidden />
                </a>
              </>
            ) : null}
            <span>{path ? <code>{path}</code> : "Showing sample HTML."}</span>
          </div>
        </div>
        {error ? <ErrorBox error={error} /> : null}
        <iframe
          title={activeKind === "notebook" ? "Generated notebook HTML" : "Generated artifact HTML"}
          sandbox=""
          srcDoc={html}
          className={`${heightClass} w-full rounded-lg border border-slate-800 bg-white`}
        />
      </div>
    </section>
  );
}

function ReportTabButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded px-2 py-1.5 ${
        active
          ? "border border-sky-400/70 bg-sky-500/15 text-sky-100"
          : "border border-transparent text-slate-300 hover:bg-slate-800/80"
      }`}
    >
      {label}
    </button>
  );
}

function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-100">
      {describeError(error)}
    </div>
  );
}

function applyCodeVisibility(html: string, showCode: boolean): string {
  if (showCode) {
    return html.replaceAll(
      '<details class="case-card code-cell"',
      '<details open class="case-card code-cell"',
    );
  }
  return html.replaceAll(
    '<details open class="case-card code-cell"',
    '<details class="case-card code-cell"',
  );
}
