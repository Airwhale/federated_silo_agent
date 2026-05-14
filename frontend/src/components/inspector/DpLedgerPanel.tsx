import type { DpLedgerSnapshot } from "@/api/types";

interface Props {
  data: DpLedgerSnapshot;
}

export function DpLedgerPanel({ data }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-400">{data.detail}</p>
      {data.entries.length === 0 ? (
        <p className="text-xs text-slate-500">No rho debited in this session yet.</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-wide text-slate-500">
            <tr className="border-b border-slate-800">
              <th className="py-1 text-left font-medium">Requester (hashed)</th>
              <th className="py-1 text-left font-medium">Bank</th>
              <th className="py-1 text-right font-medium">ρ spent</th>
              <th className="py-1 text-right font-medium">ρ remaining</th>
              <th className="py-1 text-right font-medium">ρ max</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {data.entries.map((entry) => {
              const ratio =
                entry.rho_max > 0 ? entry.rho_spent / entry.rho_max : 0;
              return (
                <tr key={`${entry.requester_key}:${entry.responding_bank_id}`}>
                  <td className="py-1.5 font-mono text-slate-200">
                    {entry.requester_key}
                  </td>
                  <td className="py-1.5 text-slate-300">{entry.responding_bank_id}</td>
                  <td className="py-1.5 text-right font-mono text-slate-200">
                    {entry.rho_spent.toFixed(4)}
                  </td>
                  <td className="py-1.5 text-right font-mono text-slate-200">
                    {entry.rho_remaining.toFixed(4)}
                  </td>
                  <td className="py-1.5 text-right font-mono text-slate-400">
                    {entry.rho_max.toFixed(4)}
                  </td>
                  <td className="py-1.5 pl-2">
                    <div
                      className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-800"
                      title={`${(ratio * 100).toFixed(1)}% spent`}
                    >
                      <div
                        className="h-full bg-emerald-400/70"
                        style={{ width: `${Math.min(100, ratio * 100)}%` }}
                      />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <p className="text-[10px] text-slate-500">
        Per-bucket and serial-mode display land with P7 provenance (P10+).
      </p>
    </div>
  );
}
