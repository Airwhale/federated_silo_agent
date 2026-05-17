import { useEffect, useId, useMemo, useState } from "react";

type MermaidApi = typeof import("mermaid").default;

let mermaidLoader: Promise<MermaidApi> | null = null;

function loadMermaid(): Promise<MermaidApi> {
  if (!mermaidLoader) {
    mermaidLoader = import("mermaid").then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "dark",
        themeVariables: {
          background: "#020617",
          mainBkg: "#0f172a",
          primaryColor: "#0f172a",
          primaryTextColor: "#e5edf8",
          primaryBorderColor: "#38bdf8",
          lineColor: "#94a3b8",
          secondaryColor: "#052e2b",
          tertiaryColor: "#172554",
          clusterBkg: "#020617",
          clusterBorder: "#334155",
          edgeLabelBackground: "#020617",
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        },
      });
      return mermaid;
    });
  }
  return mermaidLoader;
}

type Props = {
  chart: string;
  title: string;
};

export function MermaidDiagram({ chart, title }: Props) {
  const reactId = useId();
  const renderId = useMemo(
    () => `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, "")}`,
    [reactId],
  );
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    loadMermaid()
      .then((mermaid) => mermaid.render(renderId, chart))
      .then(({ svg: rendered }) => {
        if (!cancelled) {
          setSvg(rendered);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [chart, renderId]);

  if (error) {
    return (
      <figure className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3">
        <figcaption className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-100">
          {title}
        </figcaption>
        <pre className="whitespace-pre-wrap text-[11px] text-rose-200">{error}</pre>
      </figure>
    );
  }

  return (
    <figure className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <figcaption className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-200">
        {title}
      </figcaption>
      <div
        className="overflow-x-auto text-slate-100 [&_svg]:mx-auto [&_svg]:max-w-full"
        aria-label={title}
        dangerouslySetInnerHTML={{ __html: svg || '<div class="text-xs text-slate-500">Rendering diagram.</div>' }}
      />
    </figure>
  );
}
