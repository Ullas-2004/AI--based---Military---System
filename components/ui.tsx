"use client";
/** Small presentational primitives shared across pages. */
import { AlertTriangle, Inbox, Loader2, ShieldAlert } from "lucide-react";
import Link from "next/link";

import type { ThreatLevel } from "@/lib/types";

/** Severity -> token mapping. One source of truth for threat colouring. */
const SEVERITY_STYLES: Record<ThreatLevel, string> = {
  CRITICAL: "bg-aegis-danger/20 text-aegis-danger border-aegis-danger/40",
  HIGH: "bg-aegis-warning/20 text-aegis-warning border-aegis-warning/40",
  MEDIUM: "bg-aegis-info/20 text-aegis-info border-aegis-info/40",
  LOW: "bg-aegis-success/20 text-aegis-success border-aegis-success/40",
  UNKNOWN: "bg-white/10 text-aegis-muted border-white/20",
};

export function SeverityBadge({ level }: { level: ThreatLevel }) {
  const style = SEVERITY_STYLES[level] ?? SEVERITY_STYLES.UNKNOWN;
  return (
    <span
      className={`inline-block text-xs font-bold px-3 py-1 rounded-full border ${style}`}
    >
      {level}
    </span>
  );
}

export function SeverityText({ level }: { level: ThreatLevel }) {
  const colour =
    level === "CRITICAL" ? "text-aegis-danger"
      : level === "HIGH" ? "text-aegis-warning"
      : level === "MEDIUM" ? "text-aegis-info"
      : level === "LOW" ? "text-aegis-success"
      : "text-aegis-muted";
  return <span className={`font-bold ${colour}`}>{level}</span>;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 py-12 text-aegis-muted"
    >
      <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" />
      <span>{label}...</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-4 py-12 px-6 text-center"
    >
      <AlertTriangle className="w-10 h-10 text-aegis-danger" aria-hidden="true" />
      <p className="text-aegis-danger font-medium max-w-md">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-5 py-2 rounded-xl bg-white/10 border border-white/20 text-white font-medium hover:bg-white/15 transition-colors"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 px-6 text-center">
      <Inbox className="w-10 h-10 text-aegis-muted" aria-hidden="true" />
      <p className="text-gray-300 font-medium">{title}</p>
      {hint && <p className="text-sm text-aegis-muted max-w-md">{hint}</p>}
    </div>
  );
}

/** Shown in place of page content when the analyst is not signed in. */
export function AuthRequired() {
  return (
    <div className="flex flex-col items-center justify-center gap-5 py-24 px-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-aegis-accent to-aegis-accent-secondary flex items-center justify-center">
        <ShieldAlert className="w-8 h-8 text-aegis-bg" aria-hidden="true" />
      </div>
      <div>
        <h2 className="text-2xl font-bold text-white">Authentication required</h2>
        <p className="text-aegis-muted mt-2 max-w-md">
          This module contains operational intelligence. Sign in from the
          Security Command Center to continue.
        </p>
      </div>
      <Link
        href="/security"
        className="px-6 py-3 rounded-xl bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary text-aegis-bg font-bold hover:opacity-90 transition-opacity"
      >
        Go to sign in
      </Link>
    </div>
  );
}

/**
 * Pagination controls for server-paginated tables.
 *
 * Without these the UI silently capped at the first page, so records beyond it
 * were stored but unreachable.
 */
export function Pagination({
  total, limit, skip, onChange, isLoading = false,
}: {
  total: number;
  limit: number;
  skip: number;
  onChange: (nextSkip: number) => void;
  isLoading?: boolean;
}) {
  if (total <= limit) return null;

  const page = Math.floor(skip / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  const from = skip + 1;
  const to = Math.min(skip + limit, total);

  return (
    <nav
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-between gap-3 p-4 border-t border-white/10"
    >
      <p className="text-xs text-aegis-muted" aria-live="polite">
        Showing <span className="text-gray-200 font-medium">{from}-{to}</span> of{" "}
        <span className="text-gray-200 font-medium">{total}</span>
      </p>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onChange(Math.max(0, skip - limit))}
          disabled={skip === 0 || isLoading}
          className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/15 text-sm text-gray-200 hover:bg-white/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Previous
        </button>
        <span className="text-xs text-aegis-muted tabular-nums px-1">
          Page {page} / {pages}
        </span>
        <button
          onClick={() => onChange(skip + limit)}
          disabled={to >= total || isLoading}
          className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/15 text-sm text-gray-200 hover:bg-white/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </nav>
  );
}

/** Standard page heading with an eyebrow label. */
export function PageHeader({
  eyebrow, icon: Icon, title, accent, actions,
}: {
  eyebrow: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  accent: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:justify-between sm:items-end mb-6">
      <div>
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-aegis-accent text-sm font-semibold mb-3">
          <Icon className="w-4 h-4" aria-hidden="true" />
          <span>{eyebrow}</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
          {title} <span className="text-gradient">{accent}</span>
        </h1>
      </div>
      {actions}
    </div>
  );
}
