"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, Clock3, Database } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui";

const prompts = [
  "Why is the August bank account $82,000 higher than the ledger?",
  "Which invoices are unreconciled?",
  "Find suspicious or unusual journal entries.",
  "Explain the largest month-over-month expense variances.",
  "Prepare a month-end variance summary.",
];

export default function HomePage() {
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .stats()
      .then(setStats)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-10">
      <section className="animate-rise">
        <p className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Finance operations</p>
        <h1 className="mt-2 max-w-3xl font-display text-4xl leading-tight text-[var(--ink)] sm:text-5xl">
          FinanceOps Agent
        </h1>
        <p className="mt-4 max-w-2xl text-base text-[var(--muted)]">
          Investigate cash gaps, reconcile bank activity, surface anomalies, and propose
          adjustments — with deterministic tools for the math and a full audit trail for every step.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/investigate">
            <Button>
              Start investigation <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link href="/reconciliation">
            <Button variant="secondary">Run reconciliation</Button>
          </Link>
        </div>
      </section>

      <section className="animate-rise-delay grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Bank txns", stats?.bank_transactions],
          ["Invoices", stats?.invoices],
          ["Journal entries", stats?.journal_entries],
          ["Pending approvals", stats?.pending_approvals],
        ].map(([label, value]) => (
          <div
            key={String(label)}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)]/80 px-4 py-4 backdrop-blur"
          >
            <div className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</div>
            <div className="mt-2 font-display text-3xl tabular-nums">
              {value === undefined ? "…" : value}
            </div>
          </div>
        ))}
      </section>

      {error && (
        <p className="rounded-md border border-[var(--danger)]/30 bg-red-50 px-4 py-3 text-sm text-[var(--danger)]">
          API unavailable: {error}. Start the backend on port 8765.
        </p>
      )}

      <section className="animate-rise-delay-2 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)]/90 p-5">
          <h2 className="font-display text-2xl">Try a controlled investigation</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            The planner selects tools; SQL and finance logic stay deterministic.
          </p>
          <ul className="mt-4 space-y-2">
            {prompts.map((p) => (
              <li key={p}>
                <Link
                  href={`/investigate?q=${encodeURIComponent(p)}`}
                  className="group flex items-start gap-2 rounded-md px-2 py-2 text-sm hover:bg-[var(--surface-2)]"
                >
                  <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent)] opacity-0 transition group-hover:opacity-100" />
                  <span>{p}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div className="space-y-4">
          <div className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-5">
            <div className="flex items-center gap-2 text-[var(--accent)]">
              <CheckCircle2 className="h-5 w-5" />
              <h3 className="font-semibold">Human approval gate</h3>
            </div>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Marking matches reconciled or posting adjustments always requires explicit controller
              approval before execution.
            </p>
          </div>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-5">
            <div className="flex items-center gap-2 text-[var(--accent)]">
              <Database className="h-5 w-5" />
              <h3 className="font-semibold">Synthetic Aug 2024 ledger</h3>
            </div>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Seeded with a known $82k bank-vs-ledger gap, duplicates, weekend wires, and MoM
              marketing spike for objective evaluation.
            </p>
          </div>
          <div className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-5">
            <div className="flex items-center gap-2 text-[var(--accent)]">
              <Clock3 className="h-5 w-5" />
              <h3 className="font-semibold">Full audit trail</h3>
            </div>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Every plan, tool call, calculation, and approval decision is persisted for review.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
