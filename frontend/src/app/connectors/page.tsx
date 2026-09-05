"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  ConnectorInfo,
  ConnectorSync,
  ConnectorSyncResult,
  getOrgId,
} from "@/lib/api";

export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [syncs, setSyncs] = useState<ConnectorSync[]>([]);
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<ConnectorSyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [org, setOrg] = useState("org_demo");

  const refresh = useCallback(() => {
    setOrg(getOrgId());
    Promise.all([api.connectors(), api.connectorSyncs()])
      .then(([c, s]) => {
        setConnectors(c);
        setSyncs(s);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function runSync() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.bankFeedSync(3);
      setLast(res);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-3xl sm:text-4xl">Connectors</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">
          Customer-shaped bank-feed ingest. The sandbox connector mirrors a Plaid/QBO nightly
          pull: each sync advances a cursor and lands new transactions for tenant{" "}
          <code className="text-[var(--ink)]">{org}</code>. Wire real credentials later — the
          sync receipt model stays the same.
        </p>
      </header>

      <section className="rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/5 p-5">
        <h2 className="font-display text-xl">Run bank-feed sync</h2>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Simulates the job your cron / Render cron hits at 06:00 UTC. Switch to{" "}
          <strong>Admin</strong> in the sidebar first.
        </p>
        <button
          disabled={busy}
          onClick={() => void runSync()}
          className="mt-4 rounded-md bg-[var(--accent)] px-3 py-2 text-sm text-[var(--accent-fg)] disabled:opacity-60"
        >
          {busy ? "Syncing…" : "Sync now (batch of 3)"}
        </button>
        {last && (
          <p className="mt-3 text-sm tabular-nums text-[var(--ink)]">
            Last run {last.run_id}: fetched {last.records_fetched}, created {last.records_created},
            skipped {last.records_skipped}, cursor {last.cursor}
            {last.exhausted ? " (feed exhausted)" : ""}
          </p>
        )}
      </section>

      {error && (
        <p className="rounded-md border border-[var(--danger)]/30 bg-[var(--danger)]/5 px-3 py-2 text-sm text-[var(--danger)]">
          {error}
        </p>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        {connectors.map((c) => (
          <div key={c.id} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{c.status}</div>
            <h3 className="mt-1 font-display text-lg">{c.name}</h3>
            <p className="mt-2 text-xs text-[var(--muted)]">{c.provider_shape}</p>
            {c.env && (
              <ul className="mt-2 space-y-1 text-[10px] text-[var(--muted)]">
                {c.env.map((e) => (
                  <li key={e}>
                    <code>{e}</code>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </section>

      <section>
        <h2 className="font-display text-xl">Sync receipts</h2>
        <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
          <table className="min-w-full text-sm">
            <thead className="bg-[var(--panel)] text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2 text-left">When</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Created</th>
                <th className="px-3 py-2 text-left">Cursor</th>
                <th className="px-3 py-2 text-left">Run</th>
              </tr>
            </thead>
            <tbody>
              {syncs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-[var(--muted)]">
                    No syncs yet for this tenant.
                  </td>
                </tr>
              )}
              {syncs.map((s) => (
                <tr key={s.run_id} className="border-t border-[var(--border)]">
                  <td className="px-3 py-2 whitespace-nowrap">
                    {s.finished_at ? new Date(s.finished_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-3 py-2">{s.status}</td>
                  <td className="px-3 py-2 tabular-nums">{s.records_created}</td>
                  <td className="px-3 py-2 tabular-nums">{s.cursor}</td>
                  <td className="px-3 py-2 font-mono text-xs">{s.run_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
