import type { ComponentSnapshot } from "../../api/types";

type Props = {
  snapshot: ComponentSnapshot;
};

export function NotBuiltPanel({ snapshot }: Props) {
  if (snapshot.status !== "not_built") return null;
  const available = snapshot.fields?.find((field) => field.name === "available_after")?.value ?? "later";
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <h3 className="text-sm font-semibold text-white">Not Built</h3>
      <p className="mt-2 text-sm text-slate-400">Available after {available}.</p>
    </section>
  );
}
