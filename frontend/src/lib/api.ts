const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "/api";

const API_KEY_STORAGE = "financeops_api_key";

export function getApiKey(): string {
  if (typeof window === "undefined") return "fo_controller_dev";
  return window.localStorage.getItem(API_KEY_STORAGE) || "fo_controller_dev";
}

export function setApiKey(key: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(API_KEY_STORAGE, key);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": getApiKey(),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export type AskResponse = {
  workflow_id: string;
  status: string;
  plan: {
    intent: string;
    period: string;
    steps: { tool: string; args: Record<string, unknown> }[];
    rationale: string;
    planner: string;
  };
  tools_used: string[];
  tool_results: { tool: string; ok: boolean; summary: string; data: unknown }[];
  answer: string;
  citations: { type: string; id?: string | number; name?: string; value?: number }[];
  verification: {
    ok: boolean;
    summary: string;
    unsupported_claim_rate: number;
  };
  requires_approval: boolean;
  approval_request_id: string | null;
  latency_ms: number;
  estimated_cost_usd: number;
};

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),
  stats: () =>
    request<{
      vendors: number;
      invoices: number;
      bank_transactions: number;
      journal_entries: number;
      documents: number;
      workflows: number;
      pending_approvals: number;
    }>("/stats"),
  ask: (question: string) =>
    request<AskResponse>("/ask", {
      method: "POST",
      body: JSON.stringify({ question, auto_propose_actions: true }),
    }),
  workflows: () => request<Array<Record<string, unknown>>>("/workflows"),
  workflow: (id: string) => request<Record<string, unknown>>(`/workflows/${id}`),
  reconcile: (period = "2024-08") =>
    request<{ data: ReconData; summary: string }>("/reconcile", {
      method: "POST",
      body: JSON.stringify({ period, persist: true }),
    }),
  anomalies: () => request<Anomaly[]>("/anomalies"),
  detectAnomalies: (period = "2024-08") =>
    request<{ data: { findings: Anomaly[]; count: number }; summary: string }>("/anomalies/detect", {
      method: "POST",
      body: JSON.stringify({ period }),
    }),
  variance: (period = "2024-08") =>
    request<{ data: VarianceData; summary: string }>(`/variance?period=${period}`),
  transactions: (period?: string, status?: string) => {
    const qs = new URLSearchParams();
    if (period) qs.set("period", period);
    if (status) qs.set("status", status);
    return request<Txn[]>(`/transactions?${qs}`);
  },
  invoices: () => request<Invoice[]>("/invoices"),
  documents: (q?: string) =>
    request<Doc[]>(q ? `/documents?q=${encodeURIComponent(q)}` : "/documents"),
  document: (id: number) => request<Doc & { content: string }>(`/documents/${id}`),
  approvals: (status?: string) =>
    request<Approval[]>(status ? `/approvals?status=${status}` : "/approvals"),
  decide: (requestId: string, decision: "approved" | "rejected", note = "") =>
    request<Approval>(`/approvals/${requestId}/decide`, {
      method: "POST",
      body: JSON.stringify({ decision, reviewed_by: "controller", review_note: note }),
    }),
  imports: () => request<ImportBatch[]>("/imports"),
  importCustomerErp: () =>
    request<ImportResult>("/imports/customer-erp", { method: "POST", body: "{}" }),
  historicCases: () => request<HistoricCase[]>("/imports/historic-cases"),
  importHistoricCase: (caseId: string) =>
    request<ImportResult>(`/imports/historic-case/${caseId}`, { method: "POST", body: "{}" }),
  importRealPublic: () =>
    request<ImportResult>("/imports/real-public", { method: "POST", body: "{}" }),
  importCsvFiles: async (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await fetch(`${API_BASE}/imports/csv`, {
      method: "POST",
      headers: { "X-API-Key": getApiKey() },
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    return (await res.json()) as ImportResult;
  },
};

export type ImportBatch = {
  batch_id: string;
  source: string;
  description: string;
  record_count: number;
  details: Record<string, unknown>;
  created_at: string | null;
};

export type ImportResult = {
  status: string;
  imported_by?: string;
  batch_id?: string;
  created?: Record<string, number>;
  meta?: Record<string, unknown>;
};

export type ReconData = {
  run_id: string;
  period: string;
  counts: Record<string, number>;
  bank_total: number;
  ledger_cash_net: number;
  bank_minus_ledger: number;
  results: Array<{
    bank_txn_id: number;
    bank_amount: number;
    bank_date: string;
    bank_description: string;
    match_category: string;
    score: number;
    reasons: string[];
    amount_diff: number | null;
  }>;
  unmatched_gl: Array<{
    journal_line_id: number;
    amount: number;
    description: string;
    reference: string | null;
  }>;
};

export type Anomaly = {
  id?: number;
  entity_type: string;
  entity_id: string;
  anomaly_type: string;
  severity: string;
  score: number;
  explanation: string;
};

export type VarianceData = {
  period: string;
  compare_to_period: string;
  total_mom_change: number;
  variances: Array<{
    account_code: string;
    account_name: string;
    current: number;
    prior: number;
    mom_change: number;
    mom_pct: number | null;
  }>;
};

export type Txn = {
  id: number;
  txn_date: string;
  amount: number;
  description: string;
  counterparty: string | null;
  reconciliation_status: string;
  match_score: number | null;
};

export type Invoice = {
  id: number;
  invoice_number: string;
  amount: number;
  status: string;
  vendor_name: string | null;
  invoice_date: string;
};

export type Doc = {
  id: number;
  doc_type: string;
  title: string;
  filename: string;
  period: string | null;
  snippet: string;
};

export type Approval = {
  request_id: string;
  action_type: string;
  title: string;
  description: string;
  payload: Record<string, unknown>;
  status: string;
  workflow_id: string | null;
  review_note: string | null;
  created_at: string | null;
};


export type HistoricCase = {
  case_id: string;
  title?: string;
  tagline?: string;
  period?: string;
  expected_bank_minus_ledger?: number;
  demo_script?: string[];
};
