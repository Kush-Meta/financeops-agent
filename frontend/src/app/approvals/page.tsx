"use client";

import { useEffect, useState } from "react";
import { Approval, api } from "@/lib/api";
import { Button } from "@/components/ui";

export default function ApprovalsPage() {
  const [items, setItems] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setItems(await api.approvals());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const decide = async (id: string, decision: "approved" | "rejected") => {
    setBusy(id);
    setError(null);
    try {
      await api.decide(id, decision, decision === "approved" ? "Controller approved" : "Rejected after review");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl sm:text-4xl">Approvals</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Sensitive actions — reconcile marks, adjustments, journal proposals — stay pending until a
          human decides.
        </p>
      </header>

      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}

      <div className="space-y-3">
        {items.map((a) => (
          <div key={a.request_id} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-wide text-[var(--muted)]">
                  {a.action_type} · {a.status}
                </div>
                <h2 className="mt-1 font-display text-xl">{a.title}</h2>
                <p className="mt-1 text-sm text-[var(--muted)]">{a.description}</p>
                <pre className="mt-3 max-h-40 overflow-auto rounded-md bg-[var(--panel)] p-3 text-xs">
                  {JSON.stringify(a.payload, null, 2)}
                </pre>
              </div>
              {a.status === "pending" && (
                <div className="flex gap-2">
                  <Button
                    variant="success"
                    size="sm"
                    disabled={busy === a.request_id}
                    onClick={() => void decide(a.request_id, "approved")}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={busy === a.request_id}
                    onClick={() => void decide(a.request_id, "rejected")}
                  >
                    Reject
                  </Button>
                </div>
              )}
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-sm text-[var(--muted)]">
            No approval requests yet. Run an investigation that proposes an adjustment.
          </p>
        )}
      </div>
    </div>
  );
}
