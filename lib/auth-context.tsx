"use client";
/** Client-side session state, shared across the app. */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";

import { api, clearSession, getStoredUser, getToken, setSession } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  /** True until the stored session has been checked, to avoid a login flash. */
  isLoading: boolean;
  login: (username: string, password: string) => Promise<User>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore and validate any session left in this tab.
  useEffect(() => {
    let cancelled = false;

    async function restore() {
      if (!getToken()) {
        if (!cancelled) setIsLoading(false);
        return;
      }
      // Show the cached identity immediately, then confirm with the server.
      const cached = getStoredUser();
      if (cached && !cancelled) setUser(cached);
      try {
        const { user: fresh } = await api.auth.me();
        if (!cancelled) setUser(fresh);
      } catch {
        // Expired or revoked: api.ts has already cleared storage.
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    restore();

    // Keep every consumer in sync when another component logs out.
    const onSessionChange = () => setUser(getStoredUser());
    window.addEventListener("aegis:session", onSessionChange);
    return () => {
      cancelled = true;
      window.removeEventListener("aegis:session", onSessionChange);
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await api.auth.login(username, password);
    setSession(result.token, result.user);
    setUser(result.user);
    return result.user;
  }, []);

  const register = useCallback(async (username: string, password: string) => {
    await api.auth.register(username, password);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, isAuthenticated: user !== null, isLoading, login, register, logout }),
    [user, isLoading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside an <AuthProvider>.");
  }
  return context;
}
