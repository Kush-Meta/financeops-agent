"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ImportBatch, ImportResult } from "@/lib/api";

export default function ImportsPage() {
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .imports()
      .then(setBatches)
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

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-3xl sm:text-4xl">Imports</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">
          Land customer ERP and bank CSVs the way a first engagement actually starts —
          alias-tolerant column mapping, idempotent upserts, and an import batch audit row.
          Switch to <span className="text-[var(--ink)]">Admin</span> in the sidebar if auth is enabled.
        </p>
      </header>

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
