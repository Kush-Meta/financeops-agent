"use client";

import { useEffect, useState } from "react";
import { api, Doc, Invoice, Txn } from "@/lib/api";
import { money } from "@/lib/utils";

export default function RecordsPage() {
  const [tab, setTab] = useState<"txns" | "invoices" | "docs">("txns");
  const [txns, setTxns] = useState<Txn[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [doc, setDoc] = useState<(Doc & { content: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.transactions("2024-08"), api.invoices(), api.documents()])
      .then(([t, i, d]) => {
        setTxns(t);
        setInvoices(i);
        setDocs(d);
      })
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl sm:text-4xl">Records</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Browse bank transactions, invoices, and supporting documents used as evidence.
        </p>
      </header>

      <div className="flex gap-2">
        {(
          [
            ["txns", "Bank transactions"],
            ["invoices", "Invoices"],
            ["docs", "Documents"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              tab === id
                ? "bg-[var(--accent)] text-[var(--accent-fg)]"
                : "bg-[var(--surface)] text-[var(--muted)] border border-[var(--border)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}

      {tab === "txns" && (
        <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
          <table className="min-w-full text-sm">
            <thead className="bg-[var(--panel)] text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-left">Amount</th>
                <th className="px-3 py-2 text-left">Counterparty</th>
                <th className="px-3 py-2 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {txns.map((t) => (
                <tr key={t.id} className="border-t border-[var(--border)]">
                  <td className="px-3 py-2">{t.txn_date}</td>
                  <td className="px-3 py-2 tabular-nums">{money(t.amount)}</td>
                  <td className="px-3 py-2">{t.counterparty || t.description}</td>
                  <td className="px-3 py-2">{t.reconciliation_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "invoices" && (
        <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
          <table className="min-w-full text-sm">
            <thead className="bg-[var(--panel)] text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2 text-left">Invoice</th>
                <th className="px-3 py-2 text-left">Vendor</th>
                <th className="px-3 py-2 text-left">Amount</th>
                <th className="px-3 py-2 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id} className="border-t border-[var(--border)]">
                  <td className="px-3 py-2">{inv.invoice_number}</td>
                  <td className="px-3 py-2">{inv.vendor_name}</td>
                  <td className="px-3 py-2 tabular-nums">{money(inv.amount)}</td>
                  <td className="px-3 py-2">{inv.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "docs" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <ul className="space-y-2">
            {docs.map((d) => (
              <li key={d.id}>
                <button
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-3 text-left hover:bg-[var(--surface-2)]"
                  onClick={() => void api.document(d.id).then(setDoc)}
                >
                  <div className="text-xs uppercase text-[var(--muted)]">{d.doc_type}</div>
                  <div className="font-medium">{d.title}</div>
                </button>
              </li>
            ))}
          </ul>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
            {doc ? (
              <>
                <h2 className="font-display text-xl">{doc.title}</h2>
                <pre className="mt-3 whitespace-pre-wrap text-sm text-[var(--ink)]/90">{doc.content}</pre>
              </>
            ) : (
              <p className="text-sm text-[var(--muted)]">Select a document to read.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
