import { CircleHelp } from "lucide-react";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { ComponentId } from "@/api/types";
import { fieldGuidance } from "@/domain/fieldGuidance";

export type KeyValueRow = {
  label: string;
  value: ReactNode;
  tone?: "default" | "muted" | "danger" | "good";
  help?: string;
  helpValue?: unknown;
};

type Props = {
  rows: KeyValueRow[];
  guidanceComponentId?: ComponentId;
};

const TONE_CLASS: Record<NonNullable<KeyValueRow["tone"]>, string> = {
  default: "text-slate-100",
  muted: "text-slate-400",
  danger: "text-rose-300",
  good: "text-emerald-300",
};

const GUIDANCE_VALUE_PHRASES = [
  "Origin -> Lobster Trap -> LiteLLM -> provider",
  "Origin -> LiteLLM -> provider",
  "dp_noised_aggregates",
  "local_contribution",
  "peer_314b",
  "not_checked",
  "model_only",
  "not_built",
  "lobster_trap",
  "LiteLLM",
  "Lobster Trap",
  "customer names",
  "raw transactions",
  "structuring-ring",
  "layering-chain",
  "configured",
  "deterministic",
  "hybrid",
  "provider",
  "redacted",
  "matched",
  "mismatched",
  "invalid",
  "missing",
  "expired",
  "valid",
  "fresh",
  "pending",
  "live",
  "now",
  "P12",
  "P13",
  "P14",
  "P15",
  "yes",
  "no",
  "F2-B1",
  "F2-B2",
].sort((left, right) => right.length - left.length);

const GUIDANCE_VALUE_RE = new RegExp(
  `(^|[^A-Za-z0-9_])(${GUIDANCE_VALUE_PHRASES.map(escapeRegExp).join("|")})(?=$|[^A-Za-z0-9_])`,
  "gi",
);

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function guidanceValue(value: unknown): string | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  if (["boolean", "number", "string"].includes(typeof value)) return String(value);
  return undefined;
}

function renderGuidanceText(text: string) {
  const parts: ReactNode[] = [];
  let lastIndex = 0;

  const possibleValuesPrefix = text.match(/^Possible values:/i)?.[0];
  if (possibleValuesPrefix) {
    parts.push(
      <span key="possible-values-prefix" className="text-slate-500">
        {possibleValuesPrefix}
      </span>,
    );
    lastIndex = possibleValuesPrefix.length;
  }

  text.replace(GUIDANCE_VALUE_RE, (match, prefix: string, valueName: string, offset: number) => {
    const valueStart = offset + prefix.length;
    if (valueStart > lastIndex) {
      parts.push(text.slice(lastIndex, valueStart));
    }
    parts.push(
      <strong
        key={`${valueName}-${offset}`}
        className="font-semibold text-slate-50 underline decoration-slate-400 underline-offset-2"
      >
        {valueName}
      </strong>,
    );
    lastIndex = valueStart + valueName.length;
    return match;
  });

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

function GuidanceTooltip({
  label,
  help,
  value,
}: {
  label: string;
  help: string;
  value: unknown;
}) {
  const currentValue = guidanceValue(value);
  const tooltipId = useId();
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const tooltipRef = useRef<HTMLSpanElement | null>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0, width: 288 });

  const updatePosition = useCallback(() => {
    const button = buttonRef.current;
    if (!button) return;

    const buttonRect = button.getBoundingClientRect();
    const drawerRect = button.closest("[data-inspector-drawer]")?.getBoundingClientRect();
    const bounds = drawerRect ?? {
      left: 8,
      right: window.innerWidth - 8,
      top: 8,
      bottom: window.innerHeight - 8,
      width: window.innerWidth - 16,
    };
    const gutter = 12;
    const tooltipWidth = Math.min(288, Math.max(220, bounds.width - gutter * 2));
    const tooltipHeight = tooltipRef.current?.getBoundingClientRect().height ?? 128;
    const minLeft = bounds.left + gutter;
    const maxLeft = Math.max(minLeft, bounds.right - tooltipWidth - gutter);
    const centeredLeft = buttonRect.left + buttonRect.width / 2 - tooltipWidth / 2;
    const left = Math.min(Math.max(centeredLeft, minLeft), maxLeft);
    const belowTop = buttonRect.bottom + 8;
    const aboveTop = buttonRect.top - tooltipHeight - 8;
    const top =
      belowTop + tooltipHeight <= bounds.bottom - gutter
        ? belowTop
        : Math.max(bounds.top + gutter, aboveTop);

    setPosition({ left, top, width: tooltipWidth });
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return undefined;
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, updatePosition]);

  return (
    <span className="inline-flex">
      <button
        ref={buttonRef}
        type="button"
        aria-label={`Help for ${label}`}
        aria-describedby={open ? tooltipId : undefined}
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="inline-flex rounded text-slate-600 outline-none transition hover:text-slate-300 focus-visible:text-slate-200 focus-visible:ring-1 focus-visible:ring-cyan-400"
      >
        <CircleHelp size={11} className="shrink-0" />
      </button>
      {open ? (
        <span
          ref={tooltipRef}
          id={tooltipId}
          role="tooltip"
          className="pointer-events-none fixed z-[70] rounded border border-slate-700 bg-slate-950 p-2 text-left text-[11px] leading-5 tracking-normal text-slate-300 shadow-xl normal-case"
          style={position}
        >
          {currentValue ? (
            <span className="mb-1 block">
              <span className="text-slate-500">Current value: </span>
              <strong className="font-semibold text-slate-50 underline decoration-slate-400 underline-offset-2">
                {currentValue}
              </strong>
            </span>
          ) : null}
          <span>{renderGuidanceText(help)}</span>
        </span>
      ) : null}
    </span>
  );
}

/**
 * Two-column label/value rows separated by thin dividers. Replaces the
 * previous one-card-per-row stack which was visually noisy and ate
 * vertical space disproportionately to the information density of each
 * row. Used by the console system-status rail and by every inspector
 * GenericFieldsPanel, so the density change cascades.
 *
 * Label column is fixed-width (10rem) on >= sm so the values align
 * vertically and a viewer's eye can scan down the value column to
 * find what they need. On mobile the labels stack above the values
 * (single column) to avoid horizontal squeeze.
 */
export function KeyValueGrid({ rows, guidanceComponentId }: Props) {
  return (
    <dl className="divide-y divide-slate-800/70 rounded border border-slate-800/70 bg-slate-900/40 text-xs">
      {rows.map((row, index) => {
        const inferredGuidance = guidanceComponentId
          ? fieldGuidance(guidanceComponentId, row.label, row.value)
          : {};
        const help = row.help ?? inferredGuidance.help;
        const tone = row.tone ?? (inferredGuidance.dangerous ? "danger" : undefined);
        return (
          <div
            key={`${row.label}-${index}`}
            className="grid gap-x-3 gap-y-0.5 px-2.5 py-1.5 sm:grid-cols-[10rem_minmax(0,1fr)]"
          >
            <dt className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-slate-500">
              <span>{row.label}</span>
              {help ? <GuidanceTooltip label={row.label} help={help} value={row.helpValue ?? row.value} /> : null}
            </dt>
            <dd className={`break-words ${TONE_CLASS[tone ?? "default"]}`}>
              {row.value ?? <span className="text-slate-600">not reported</span>}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
