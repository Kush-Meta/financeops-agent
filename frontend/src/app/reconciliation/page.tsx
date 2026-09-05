"use client";

import { useState } from "react";
import { api, ReconData } from "@/lib/api";
import { Button } from "@/components/ui";
import { money, cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

const badge: Record<string, string> = {
  matched: "bg-emerald-100 text-emerald-800",
  probable: "bg-sky-100 text-sky-800",
  needs_review: "bg-amber-100 text-amber-900",
  unmatched: "bg-rose-100 text-rose-800",
};

export default function ReconciliationPage() {
  const [period, setPeriod] = useState("2024-09");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ReconData | null>(null);
  const [summary, setSummary] = useState("");
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.reconcile(period);
      setData(res.data);
      setSummary(res.summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl sm:text-4xl">Reconciliation</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Match bank transactions to ledger cash lines and invoices using amount, date, reference,
          and fuzzy counterparty scoring. After loading the Meridian ERP pack on Imports, use{" "}
          <span className="text-[var(--ink)]">2024-09</span> for Meridian ($25,665) or <span className="text-[var(--ink)]">2018-09</span> for the Aether retrospective (−$2.44M).
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <div>
          <label className="text-xs uppercase tracking-wide text-[var(--muted)]">Period</label>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="mt-1 block rounded-md border border-[var(--border)] bg-white px-3 py-2 text-sm"
          >
            <option value="2024-06">2024-06</option>
            <option value="2024-07">2024-07</option>
            <option value="2024-08">2024-08 (synthetic close)</option>
            <option value="2024-09">2024-09 (Meridian ERP)</option>
            <option value="2018-09">2018-09 (Aether retrospective)</option>
          </select>
        </div>
        <Button onClick={() => void run()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Run reconciliation
        </Button>
      </div>

      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
      {summary && <p className="text-sm text-[var(--muted)]">{summary}</p>}

      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Bank − ledger", money(data.bank_minus_ledger)],
              ["Matched", data.counts.matched],
              ["Unmatched bank", data.counts.unmatched],
              ["Needs review", data.counts.needs_review],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
                <div className="text-xs uppercase tracking-wide text-[var(--muted)]">{k}</div>
                <div className="mt-1 font-display text-2xl tabular-nums">{v}</div>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-[var(--border)] bg-[var(--panel)] text-xs uppercase tracking-wide text-[var(--muted)]">
                <tr>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Amount</th>
                  <th className="px-3 py-2">Description</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">Score</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((r) => (
                  <tr key={r.bank_txn_id} className="border-b border-[var(--border)]/70">
                    <td className="px-3 py-2 whitespace-nowrap">{r.bank_date}</td>
                    <td className="px-3 py-2 tabular-nums">{money(r.bank_amount)}</td>
                    <td className="px-3 py-2 max-w-md truncate">{r.bank_description}</td>
                    <td className="px-3 py-2">
                      <span className={cn("rounded-full px-2 py-0.5 text-xs", badge[r.match_category] || "bg-gray-100")}>
                        {r.match_category}
                      </span>
                    </td>
                    <td className="px-3 py-2 tabular-nums">{r.score?.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.unmatched_gl.length > 0 && (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
              <h2 className="font-display text-xl">Unmatched GL cash lines</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {data.unmatched_gl.map((g) => (
                  <li key={g.journal_line_id}>
                    {money(g.amount)} — {g.description}{" "}
                    <span className="text-[var(--muted)]">({g.reference})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
