"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2, ShieldCheck, Wrench } from "lucide-react";
import { AskResponse, api } from "@/lib/api";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

function renderMarkdown(md: string) {
  const lines = md.split("\n");
  const nodes: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (!list.length) return;
    nodes.push(
      <ul key={`ul-${nodes.length}`} className="my-2 list-disc space-y-1 pl-5">
        {list.map((item, i) => (
          <li key={i} dangerouslySetInnerHTML={{ __html: inline(item) }} />
        ))}
      </ul>
    );
    list = [];
  };
  const inline = (s: string) =>
    s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  for (const line of lines) {
    if (line.startsWith("- ")) {
      list.push(line.slice(2));
      continue;
    }
    flush();
    if (line.startsWith("## ")) {
      nodes.push(
        <h2 key={nodes.length} className="mt-4 mb-2 font-display text-xl">
          {line.slice(3)}
        </h2>
      );
    } else if (line.startsWith("### ")) {
      nodes.push(
        <h3
          key={nodes.length}
          className="mt-3 mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]"
        >
          {line.slice(4)}
        </h3>
      );
    } else if (line.startsWith("---")) {
      nodes.push(<hr key={nodes.length} className="my-4 border-[var(--border)]" />);
    } else if (line.trim()) {
      nodes.push(
        <p
          key={nodes.length}
          className="text-sm leading-relaxed"
          dangerouslySetInnerHTML={{ __html: inline(line) }}
        />
      );
    }
  }
  flush();
  return nodes;
}

export default function InvestigateClient() {
  const params = useSearchParams();
  const initial = params.get("q") || "";
  const [question, setQuestion] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);

  const run = async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.ask(q.trim());
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initial) {
      setQuestion(initial);
      void run(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  const answerNodes = useMemo(() => (result ? renderMarkdown(result.answer) : null), [result]);

  return (
    <div className="space-y-6">
      <header className="animate-rise">
        <h1 className="font-display text-3xl sm:text-4xl">Investigate</h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--muted)]">
          Ask a finance question. The agent plans tool calls, runs deterministic reconciliation and
          SQL, then explains findings with verification.
        </p>
      </header>

      <form
        className="animate-rise-delay rounded-lg border border-[var(--border)] bg-[var(--surface)]/90 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void run(question);
        }}
      >
        <label className="text-xs uppercase tracking-wide text-[var(--muted)]">Question</label>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          className="mt-2 w-full resize-y rounded-md border border-[var(--border)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          placeholder="Why does the August bank balance not match the general ledger?"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-xs text-[var(--muted)]">Synthetic dataset period focus: 2024-06 → 2024-08</p>
          <Button type="submit" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Running
              </>
            ) : (
              "Investigate"
            )}
          </Button>
        </div>
      </form>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-[var(--danger)]">
          {error}
        </p>
      )}

      {result && (
        <div className="grid gap-4 lg:grid-cols-[1.4fr_0.8fr]">
          <article className="animate-rise rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded-full bg-[var(--accent-soft)] px-2 py-1 text-[var(--accent)]">
                {result.plan.intent}
              </span>
              <span className="rounded-full bg-[var(--surface-2)] px-2 py-1 text-[var(--muted)]">
                {result.workflow_id}
              </span>
              <span className="rounded-full bg-[var(--surface-2)] px-2 py-1 text-[var(--muted)]">
                {Math.round(result.latency_ms)} ms
              </span>
            </div>
            <div className="prose-finance space-y-1">{answerNodes}</div>
          </article>

          <aside className="space-y-4">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4">
              <div className="flex items-center gap-2 font-semibold">
                <Wrench className="h-4 w-4 text-[var(--accent)]" /> Tools used
              </div>
              <ol className="mt-3 space-y-2">
                {result.tool_results.map((t, i) => (
                  <li key={`${t.tool}-${i}`} className="text-sm">
                    <div className="font-medium">{t.tool}</div>
                    <div className={cn("text-xs", t.ok ? "text-[var(--muted)]" : "text-[var(--danger)]")}>
                      {t.summary}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
            <div className="rounded-lg border border-[var(--border)] bg-[var(--panel)] p-4">
              <div className="flex items-center gap-2 font-semibold">
                <ShieldCheck className="h-4 w-4 text-[var(--accent)]" /> Verification
              </div>
              <p className="mt-2 text-sm text-[var(--muted)]">{result.verification.summary}</p>
              <p className="mt-1 text-xs text-[var(--muted)]">
                Unsupported claim rate: {(result.verification.unsupported_claim_rate * 100).toFixed(1)}%
              </p>
              {result.requires_approval && (
                <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-[var(--warn)]">
                  Approval pending: {result.approval_request_id}. Review in Approvals.
                </p>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
