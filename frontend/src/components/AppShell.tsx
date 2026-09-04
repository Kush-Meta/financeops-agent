"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  FileSearch,
  GitCompare,
  LayoutDashboard,
  MessageSquareText,
  Scale,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/investigate", label: "Investigate", icon: MessageSquareText },
  { href: "/reconciliation", label: "Reconciliation", icon: Scale },
  { href: "/anomalies", label: "Anomalies", icon: ShieldAlert },
  { href: "/approvals", label: "Approvals", icon: GitCompare },
  { href: "/audit", label: "Audit trail", icon: Activity },
  { href: "/records", label: "Records", icon: FileSearch },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
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
      </aside>
      <main className="relative min-h-screen">
        <div className="pointer-events-none absolute inset-0 bg-grid opacity-40" />
        <div className="relative mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">{children}</div>
      </main>
    </div>
  );
}
