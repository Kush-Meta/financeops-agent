"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Anomaly, api } from "@/lib/api";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

export default function AnomaliesPage() {
  const [items, setItems] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSeeded = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await api.anomalies());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  const runDetect = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.detectAnomalies("2024-08");
      setItems(res.data.findings);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSeeded();
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-3xl sm:text-4xl">Anomalies</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Interpretable rules: weekend postings, unusual vendors, rounded amounts, duplicates, and
          MoM expense spikes.
        </p>
      </header>

      <div className="flex gap-2">
        <Button onClick={() => void runDetect()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Run detector
        </Button>
        <Button variant="secondary" onClick={() => void loadSeeded()} disabled={loading}>
          Show ground-truth flags
        </Button>
      </div>

      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}

      <div className="space-y-3">
        {items.map((a, i) => (
          <div
            key={`${a.entity_type}-${a.entity_id}-${a.anomaly_type}-${i}`}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
          >
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span
                className={cn(
                  "rounded-full px-2 py-0.5",
                  a.severity === "high"
                    ? "bg-rose-100 text-rose-800"
                    : "bg-amber-100 text-amber-900"
                )}
              >
                {a.severity}
              </span>
              <span className="rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-[var(--muted)]">
                {a.anomaly_type}
              </span>
              <span className="text-[var(--muted)]">
                {a.entity_type} #{a.entity_id}
              </span>
              <span className="ml-auto tabular-nums text-[var(--muted)]">
                score {(a.score * 100).toFixed(0)}%
              </span>
            </div>
            <p className="mt-2 text-sm">{a.explanation}</p>
          </div>
        ))}
        {!loading && items.length === 0 && (
          <p className="text-sm text-[var(--muted)]">No anomalies loaded yet.</p>
        )}
      </div>
    </div>
  );
}
