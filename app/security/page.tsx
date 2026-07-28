"use client";
import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle, ClipboardList, Eye, EyeOff, Lock, LogIn, Shield, UserPlus, XCircle,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { useAsyncData } from "@/lib/use-async-data";
import { useAuth } from "@/lib/auth-context";
import type { AuditLogEntry } from "@/lib/types";
import { EmptyState, ErrorState, PageHeader, Pagination, Spinner } from "@/components/ui";

type Tab = "login" | "register" | "audit";

const AUDIT_PAGE_SIZE = 25;

const ACTION_STYLES: Record<string, string> = {
  LOGIN_SUCCESS: "bg-aegis-success/20 text-aegis-success",
  LOGIN_FAILED: "bg-aegis-danger/20 text-aegis-danger",
  LOGIN_BLOCKED: "bg-aegis-danger/20 text-aegis-danger",
  AUTHZ_DENIED: "bg-aegis-danger/20 text-aegis-danger",
  USER_REGISTERED: "bg-aegis-accent/20 text-aegis-accent",
};

export default function SecurityPage() {
  const { user, isAuthenticated, login, register, logout } = useAuth();

  const [tab, setTab] = useState<Tab>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [isBusy, setBusy] = useState(false);

  const canViewAudit = user?.role === "admin" || user?.role === "commander";
  const [auditSkip, setAuditSkip] = useState(0);

  // Only fetched once the audit tab is open and the role permits it.
  const {
    data: auditData, isLoading: auditLoading,
    error: auditError, refresh: loadAuditLogs,
  } = useAsyncData(
    () => api.auth.auditLog(AUDIT_PAGE_SIZE, auditSkip),
    {
      enabled: tab === "audit" && canViewAudit,
      errorMessage: "Could not load the audit trail.",
    },
  );

  useEffect(() => {
    if (tab === "audit" && canViewAudit) loadAuditLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadAuditLogs is stable
  }, [auditSkip]);

  const auditLogs: AuditLogEntry[] = auditData?.data ?? [];
  const auditTotal = auditData?.pagination.total ?? 0;

  const submit = useCallback(async () => {
    setBusy(true);
    setMessage(null);
    try {
      if (tab === "login") {
        const signedIn = await login(username, password);
        setMessage({
          type: "success",
          text: `Signed in as ${signedIn.username} (${signedIn.role}).`,
        });
      } else {
        await register(username, password);
        setMessage({
          type: "success",
          text: `Account '${username}' created. You can now sign in.`,
        });
        setTab("login");
      }
      setPassword("");
    } catch (err) {
      setMessage({
        type: "error",
        text: err instanceof ApiError ? err.message : "Request failed.",
      });
    } finally {
      setBusy(false);
    }
  }, [tab, username, password, login, register]);

  const tabs: { id: Tab; label: string; icon: typeof LogIn }[] = [
    { id: "login", label: "Login", icon: LogIn },
    { id: "register", label: "Register", icon: UserPlus },
    { id: "audit", label: "Audit trail", icon: ClipboardList },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Cyber security"
        icon={Shield}
        title="Security"
        accent="Command Center"
      />

      <div role="tablist" aria-label="Security section" className="flex flex-wrap gap-2">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => { setTab(id); setMessage(null); }}
            className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm transition-colors ${
              tab === id
                ? "bg-gradient-to-r from-aegis-accent/20 to-aegis-accent-secondary/20 border border-aegis-accent/40 text-white"
                : "bg-white/5 border border-white/10 text-gray-400 hover:text-white"
            }`}
          >
            <Icon className="w-4 h-4" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>

      {message && (
        <p
          role="alert"
          className={`inline-flex items-center gap-3 w-full p-4 rounded-xl border text-sm font-medium ${
            message.type === "success"
              ? "bg-aegis-success/10 border-aegis-success/30 text-aegis-success"
              : "bg-aegis-danger/10 border-aegis-danger/30 text-aegis-danger"
          }`}
        >
          {message.type === "success"
            ? <CheckCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
            : <XCircle className="w-5 h-5 shrink-0" aria-hidden="true" />}
          {message.text}
        </p>
      )}

      {(tab === "login" || tab === "register") && (
        isAuthenticated && tab === "login" ? (
          <section className="max-w-lg mx-auto glass-panel rounded-2xl p-8 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-aegis-accent to-aegis-accent-secondary flex items-center justify-center">
              <CheckCircle className="w-8 h-8 text-aegis-bg" aria-hidden="true" />
            </div>
            <h2 className="text-xl font-bold text-white">
              Signed in as {user?.username}
            </h2>
            <p className="text-sm text-aegis-muted mt-1.5 capitalize">
              Role: {user?.role}
            </p>
            <button
              onClick={() => { logout(); setMessage(null); }}
              className="mt-6 px-6 py-3 rounded-xl bg-white/5 border border-white/15 text-white font-semibold hover:bg-white/10 transition-colors"
            >
              Sign out
            </button>
          </section>
        ) : (
          <section className="max-w-lg mx-auto glass-panel rounded-2xl p-6 sm:p-8">
            <div className="text-center mb-7">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-aegis-accent to-aegis-accent-secondary flex items-center justify-center">
                <Lock className="w-8 h-8 text-aegis-bg" aria-hidden="true" />
              </div>
              <h2 className="text-2xl font-bold text-white">
                {tab === "login" ? "Analyst login" : "Register new analyst"}
              </h2>
              <p className="text-aegis-muted text-sm mt-1.5">
                {tab === "login"
                  ? "Authenticate to access AegisAI modules."
                  : "Create a secure analyst account."}
              </p>
            </div>

            <form
              className="space-y-5"
              onSubmit={(e) => { e.preventDefault(); submit(); }}
            >
              <div>
                <label htmlFor="username" className="block text-sm text-gray-300 mb-2 font-medium">
                  Username
                </label>
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="3-32 characters"
                  className="w-full bg-white/5 border border-white/10 rounded-xl py-3 px-4 text-white placeholder-gray-500 focus:border-aegis-accent transition-colors"
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-sm text-gray-300 mb-2 font-medium">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete={tab === "login" ? "current-password" : "new-password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={tab === "register" ? "At least 8 characters" : "Enter password"}
                    className="w-full bg-white/5 border border-white/10 rounded-xl py-3 px-4 pr-12 text-white placeholder-gray-500 focus:border-aegis-accent transition-colors"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword
                      ? <EyeOff className="w-5 h-5" aria-hidden="true" />
                      : <Eye className="w-5 h-5" aria-hidden="true" />}
                  </button>
                </div>
                {tab === "register" && (
                  <p className="text-xs text-aegis-muted mt-2">
                    Must mix letters with numbers or symbols, and be at most 72 bytes.
                  </p>
                )}
              </div>

              <button
                type="submit"
                disabled={isBusy || !username || !password}
                className="w-full py-3.5 rounded-xl bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary text-aegis-bg font-bold hover:opacity-90 transition-opacity disabled:opacity-40"
              >
                {isBusy ? "Processing..." : tab === "login" ? "Authenticate" : "Create account"}
              </button>
            </form>
          </section>
        )
      )}

      {tab === "audit" && (
        <section className="glass-panel rounded-2xl overflow-hidden">
          <div className="p-5 sm:p-6 border-b border-white/10">
            <h2 className="text-lg font-bold text-white">Security audit trail</h2>
            <p className="text-sm text-aegis-muted">
              Authentication events and privileged access attempts.
            </p>
          </div>

          {!isAuthenticated ? (
            <EmptyState
              title="Authentication required"
              hint="Sign in with a commander or admin account to view the audit trail."
            />
          ) : !canViewAudit ? (
            <EmptyState
              title="Insufficient privileges"
              hint={`The audit trail is restricted to commander and admin roles. Your role is '${user?.role}'.`}
            />
          ) : auditLoading ? (
            <Spinner label="Loading audit events" />
          ) : auditError ? (
            <ErrorState message={auditError} onRetry={loadAuditLogs} />
          ) : auditLogs.length === 0 ? (
            <EmptyState title="No audit events recorded yet" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Security audit events</caption>
                <thead className="text-xs uppercase tracking-wider text-aegis-muted border-b border-white/10">
                  <tr>
                    <th scope="col" className="p-4">Timestamp</th>
                    <th scope="col" className="p-4">User</th>
                    <th scope="col" className="p-4">Action</th>
                    <th scope="col" className="p-4">Details</th>
                    <th scope="col" className="p-4">IP</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.map((log) => (
                    <tr key={log.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="p-4 text-gray-300 font-mono text-xs whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleString(undefined, {
                          dateStyle: "short", timeStyle: "medium",
                        })}
                      </td>
                      <td className="p-4 text-white font-mono text-xs">{log.user_id}</td>
                      <td className="p-4">
                        <span
                          className={`text-xs font-bold px-3 py-1 rounded-full ${
                            ACTION_STYLES[log.action] ?? "bg-white/10 text-gray-300"
                          }`}
                        >
                          {log.action}
                        </span>
                      </td>
                      <td className="p-4 text-gray-400 max-w-[22rem] truncate">{log.details}</td>
                      <td className="p-4 text-aegis-muted font-mono text-xs">
                        {log.ip_address || "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                total={auditTotal}
                limit={AUDIT_PAGE_SIZE}
                skip={auditSkip}
                onChange={setAuditSkip}
                isLoading={auditLoading}
              />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
