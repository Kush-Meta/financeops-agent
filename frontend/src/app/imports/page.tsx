"use client";

import { useCallback, useEffect, useState } from "react";
import { api, HistoricCase, ImportBatch, ImportResult } from "@/lib/api";

export default function ImportsPage() {
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [cases, setCases] = useState<HistoricCase[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    Promise.all([api.imports(), api.historicCases()])
      .then(([b, c]) => {
        setBatches(b);
        setCases(c);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function run(label: string, fn: () => Promise<ImportResult>) {
    setBusy(label);
    setError(null);
    setResult(null);
    try {
      const res = await fn();
      setResult(res);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  const aether = cases.find((c) => c.case_id === "aether_2018q3") || cases[0];

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-3xl sm:text-4xl">Imports</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">
          Land customer ERP CSVs — or replay a labeled historic retrospective built from public
          enforcement themes. Switch to <span className="text-[var(--ink)]">Admin</span> if auth is on.
        </p>
      </header>

      {aether && (
        <section className="rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/5 p-5 md:p-6">
          <p className="text-[10px] uppercase tracking-[0.2em] text-[var(--accent)]">
            Retrospective proof pack
          </p>
          <h2 className="mt-1 font-display text-2xl">{aether.title || aether.case_id}</h2>
          <p className="mt-2 max-w-3xl text-sm text-[var(--muted)]">
            {aether.tagline ||
              "Reconstructed cash cut-off case: phantom affiliate cash, period-end booking, unrecorded fee."}
          </p>
          <p className="mt-3 text-sm tabular-nums text-[var(--ink)]">
            Period {aether.period} · expected bank−ledger{" "}
            <strong>
              {typeof aether.expected_bank_minus_ledger === "number"
                ? aether.expected_bank_minus_ledger.toLocaleString("en-US", {
                    style: "currency",
                    currency: "USD",
                    maximumFractionDigits: 0,
                  })
                : "—"}
            </strong>
          </p>
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-xs text-[var(--muted)]">
            {(aether.demo_script || []).map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <button
            disabled={!!busy}
            onClick={() => run("historic", () => api.importHistoricCase(aether.case_id))}
            className="mt-4 rounded-md bg-[var(--accent)] px-3 py-2 text-sm text-[var(--accent-fg)] disabled:opacity-60"
          >
            {busy === "historic" ? "Loading case…" : "Load historic retrospective"}
          </button>
        </section>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
          <h2 className="font-display text-xl">Meridian Robotics pack</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Bundled Sep-2024 vendor / AP / bank / GL extract with a labeled $25,665 cash gap
            (deposit in transit, outstanding check, wire fee).
          </p>
          <button
            disabled={!!busy}
            onClick={() => run("customer", () => api.importCustomerErp())}
            className="mt-4 rounded-md bg-[var(--accent)] px-3 py-2 text-sm text-[var(--accent-fg)] disabled:opacity-60"
          >
            {busy === "customer" ? "Importing…" : "Load customer ERP CSVs"}
          </button>
        </div>

        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
          <h2 className="font-display text-xl">Upload your CSVs</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Filenames should include <code>vendor</code>, <code>invoice</code>/<code>ap</code>,{" "}
            <code>bank</code>, or <code>gl</code>/<code>journal</code>.
          </p>
          <label className="mt-4 inline-flex cursor-pointer rounded-md border border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-sm">
            {busy === "upload" ? "Uploading…" : "Choose CSV files"}
            <input
              type="file"
              accept=".csv,text/csv"
              multiple
              className="hidden"
              disabled={!!busy}
              onChange={(e) => {
                const files = Array.from(e.target.files || []);
                if (!files.length) return;
                run("upload", () => api.importCsvFiles(files));
                e.target.value = "";
              }}
            />
          </label>
          <button
            disabled={!!busy}
            onClick={() => run("public", () => api.importRealPublic())}
            className="ml-2 mt-4 rounded-md border border-[var(--border)] px-3 py-2 text-sm text-[var(--muted)] hover:text-[var(--ink)] disabled:opacity-60"
          >
            {busy === "public" ? "Importing…" : "Re-import public datasets"}
          </button>
        </div>
      </section>

      {error && (
        <p className="rounded-md border border-[var(--danger)]/30 bg-[var(--danger)]/5 px-3 py-2 text-sm text-[var(--danger)]">
          {error}
        </p>
      )}

      {result && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4 text-sm">
          <div className="font-medium text-[var(--ink)]">Last import</div>
          <pre className="mt-2 overflow-x-auto text-xs text-[var(--muted)]">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}

      <section>
        <h2 className="font-display text-xl">Import batches</h2>
        <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
          <table className="min-w-full text-sm">
            <thead className="bg-[var(--panel)] text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2 text-left">When</th>
                <th className="px-3 py-2 text-left">Source</th>
                <th className="px-3 py-2 text-left">Records</th>
                <th className="px-3 py-2 text-left">Batch</th>
              </tr>
            </thead>
            <tbody>
              {batches.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-[var(--muted)]">
                    No import batches yet.
                  </td>
                </tr>
              )}
              {batches.map((b) => (
                <tr key={b.batch_id} className="border-t border-[var(--border)]">
                  <td className="px-3 py-2 whitespace-nowrap">
                    {b.created_at ? new Date(b.created_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-3 py-2">{b.source}</td>
                  <td className="px-3 py-2 tabular-nums">{b.record_count}</td>
                  <td className="px-3 py-2 font-mono text-xs">{b.batch_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
