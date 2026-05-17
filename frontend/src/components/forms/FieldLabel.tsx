import type { ReactNode } from "react";

type Props = {
  label: string;
  children: ReactNode;
};

/**
 * Compact form-field wrapper used across the ops-console forms
 * (Demo Flow probe forms, LLM Route input, Interaction Console).
 * Renders a tiny uppercase label above the control so the field's
 * purpose reads at a glance without focus-tabbing through each input.
 *
 * Lives in ``forms/`` rather than alongside any one consumer because
 * three otherwise-unrelated views render it; consolidating here keeps
 * the typography choices (text size, color, tracking) in one place.
 */
export function FieldLabel({ label, children }: Props) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
      {children}
    </label>
  );
}
