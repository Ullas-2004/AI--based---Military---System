"use client";
import { useEffect, useState } from "react";
import { LogOut, Menu, User as UserIcon } from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { HealthResponse } from "@/lib/types";

export default function Navbar({ onMenuClick }: { onMenuClick: () => void }) {
  const { user, isAuthenticated, logout } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState(false);

  // Poll backend health so the status pill reflects reality rather than a
  // decorative "Live Sync" animation that was always green.
  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const result = await api.health();
        if (!cancelled) { setHealth(result); setHealthError(false); }
      } catch {
        if (!cancelled) { setHealth(null); setHealthError(true); }
      }
    };

    check();
    const interval = setInterval(check, 30_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  const isDbUp = health?.subsystems.database ?? false;
  const statusLabel = healthError
    ? "Backend offline"
    : isDbUp
      ? "All systems nominal"
      : "Backend up - database offline";
  const statusColour = healthError
    ? "bg-aegis-danger"
    : isDbUp
      ? "bg-aegis-success"
      : "bg-aegis-warning";

  return (
    <header className="sticky top-0 z-20 h-16 sm:h-20 glass-panel border-b border-white/10 flex items-center justify-between gap-4 px-4 sm:px-6">
      <button
        onClick={onMenuClick}
        className="lg:hidden p-2 -ml-2 text-gray-300 hover:text-white transition-colors"
        aria-label="Open navigation"
        aria-controls="primary-navigation"
      >
        <Menu className="w-6 h-6" aria-hidden="true" />
      </button>

      {/* System status. Replaces the purely decorative pulsing dot. */}
      <div
        className="flex items-center gap-2.5 min-w-0"
        role="status"
        aria-live="polite"
      >
        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${statusColour}`} aria-hidden="true" />
        <span className="text-sm text-gray-300 truncate hidden sm:inline">{statusLabel}</span>
        {health && (
          <span className="hidden lg:inline text-xs text-aegis-muted font-mono">
            v{health.version} / {health.environment}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3 sm:gap-5 ml-auto">
        {isAuthenticated && user ? (
          <>
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-9 h-9 shrink-0 rounded-full bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary p-[2px]">
                <div className="w-full h-full bg-aegis-bg rounded-full flex items-center justify-center">
                  <UserIcon className="w-4 h-4 text-white" aria-hidden="true" />
                </div>
              </div>
              <div className="hidden sm:block min-w-0">
                <p className="text-sm font-medium text-gray-100 truncate">
                  {user.username ?? "Analyst"}
                </p>
                <p className="text-xs text-aegis-muted capitalize">{user.role}</p>
              </div>
            </div>
            <button
              onClick={logout}
              className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-sm text-gray-300 hover:text-white hover:bg-white/10 transition-colors"
            >
              <LogOut className="w-4 h-4" aria-hidden="true" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </>
        ) : (
          <a
            href="/security"
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary text-aegis-bg text-sm font-bold hover:opacity-90 transition-opacity"
          >
            Sign in
          </a>
        )}
      </div>
    </header>
  );
}
