"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui";

type Workflow = {
  workflow_id: string;
  user_request: string;
  status: string;
  latency_ms?: number;
  requires_approval?: boolean;
  created_at?: string;
};

export default function AuditPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .workflows()
      .then((rows) => setWorkflows(rows as Workflow[]))
      .catch((e) => setError(e.message));
  }, []);

  const open = async (id: string) => {
    setSelected(id);
    try {
      setDetail(await api.workflow(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  };

  const trail = (detail?.audit_trail as Array<Record<string, unknown>>) || [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl sm:text-4xl">Audit trail</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Inspect plans, tool invocations, evidence, verification, and approval events per workflow.
        </p>
      </header>

      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-2">
          {workflows.map((w) => (
            <button
              key={w.workflow_id}
              onClick={() => void open(w.workflow_id)}
              className={`w-full rounded-lg border px-3 py-3 text-left text-sm transition ${
                selected === w.workflow_id
                  ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                  : "border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-2)]"
              }`}
            >
              <div className="font-medium line-clamp-2">{w.user_request}</div>
              <div className="mt-1 text-xs text-[var(--muted)]">
                {w.workflow_id} · {w.latency_ms ? `${Math.round(w.latency_ms)} ms` : "—"}
              </div>
            </button>
          ))}
          {workflows.length === 0 && (
            <p className="text-sm text-[var(--muted)]">No workflows yet.</p>
          )}
        </div>

        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
          {!detail ? (
            <p className="text-sm text-[var(--muted)]">Select a workflow to inspect its audit trail.</p>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="text-xs uppercase tracking-wide text-[var(--muted)]">Workflow</div>
                <div className="font-display text-xl">{String(detail.workflow_id)}</div>
              </div>
              <ol className="relative space-y-4 border-l border-[var(--border)] pl-4">
                {trail.map((e) => (
                  <li key={String(e.id)} className="relative">
                    <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-[var(--accent)]" />
                    <div className="text-xs uppercase tracking-wide text-[var(--muted)]">
                      {String(e.event_type)} · {String(e.actor)}
                      {e.duration_ms ? ` · ${Math.round(Number(e.duration_ms))} ms` : ""}
                    </div>
                    <div className="text-sm">{String(e.message)}</div>
                  </li>
                ))}
              </ol>
              <Button variant="secondary" size="sm" onClick={() => setDetail(null)}>
                Clear
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
