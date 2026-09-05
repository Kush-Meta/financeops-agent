"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  Activity,
  FileSearch,
  GitCompare,
  LayoutDashboard,
  MessageSquareText,
  Scale,
  ShieldAlert,
  Upload,
  Cable,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getApiKey, setApiKey, getOrgId, setOrgId } from "@/lib/api";

const links = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/investigate", label: "Investigate", icon: MessageSquareText },
  { href: "/reconciliation", label: "Reconciliation", icon: Scale },
  { href: "/anomalies", label: "Anomalies", icon: ShieldAlert },
  { href: "/approvals", label: "Approvals", icon: GitCompare },
  { href: "/audit", label: "Audit trail", icon: Activity },
  { href: "/imports", label: "Imports", icon: Upload },
  { href: "/connectors", label: "Connectors", icon: Cable },
  { href: "/records", label: "Records", icon: FileSearch },
];

const ROLES = [
  { key: "fo_controller_dev", label: "Controller" },
  { key: "fo_investigator_dev", label: "Investigator" },
  { key: "fo_admin_dev", label: "Admin" },
  { key: "fo_viewer_dev", label: "Viewer" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [roleKey, setRoleKey] = useState("fo_controller_dev");
  const [orgId, setOrgIdState] = useState("org_demo");

  useEffect(() => {
    setRoleKey(getApiKey() || "fo_controller_dev");
    setOrgIdState(getOrgId() || "org_demo");
  }, []);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-b border-[var(--border)] bg-[var(--panel)] lg:border-b-0 lg:border-r">
        <div className="px-5 py-6">
          <div className="font-display text-2xl tracking-tight text-[var(--ink)]">
            FinanceOps
          </div>
          <p className="mt-1 text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
            Agent
          </p>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-4 lg:flex-col">
          {links.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm whitespace-nowrap transition",
                  active
                    ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                    : "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto hidden border-t border-[var(--border)] px-4 py-4 lg:block">
          <label className="text-[10px] uppercase tracking-wide text-[var(--muted)]">
            Acting as
          </label>
          <select
            className="mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-xs"
            value={roleKey}
            onChange={(e) => {
              setRoleKey(e.target.value);
              setApiKey(e.target.value);
            }}
          >
            {ROLES.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
          <p className="mt-2 text-[10px] leading-snug text-[var(--muted)]">
Demo API keys map to roles. Enable AUTH_ENABLED on the API for enforcement.
          </p>
          <label className="mt-4 text-[10px] uppercase tracking-wide text-[var(--muted)]">
            Tenant
          </label>
          <select
            className="mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-xs"
            value={orgId}
            onChange={(e) => {
              setOrgIdState(e.target.value);
              setOrgId(e.target.value);
            }}
          >
            <option value="org_demo">org_demo — FinanceOps Demo</option>
            <option value="org_acme">org_acme — Acme Industrial</option>
          </select>
          <p className="mt-2 text-[10px] leading-snug text-[var(--muted)]">
            X-Org-Id scopes connector sync cursors (demo tenancy).
          </p>
        </div>
      </aside>
      <main className="relative min-h-screen">
        <div className="pointer-events-none absolute inset-0 bg-grid opacity-40" />
        <div className="relative mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">{children}</div>
      </main>
    </div>
  );
}
