"use client";

import { Suspense } from "react";
import InvestigateClient from "./InvestigateClient";

export default function Page() {
  return (
    <Suspense fallback={<div className="text-sm text-[var(--muted)]">Loading…</div>}>
      <InvestigateClient />
    </Suspense>
  );
}
