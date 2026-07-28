"use client";
/**
 * Data-fetching hook with cancellation.
 *
 * Two things this gets right that hand-rolled effects usually do not:
 *
 *  1. No synchronous setState in the effect body. Doing that triggers a
 *     cascading re-render before the browser paints (and React 19's
 *     `set-state-in-effect` rule flags it).
 *  2. In-flight requests are cancelled on unmount and on re-run, so a slow
 *     response cannot resolve against an unmounted component or overwrite a
 *     newer result.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

interface AsyncState<T> {
  data: T | null;
  isLoading: boolean;
  error: string | null;
}

function toMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function useAsyncData<T>(
  loader: () => Promise<T>,
  options: { enabled?: boolean; errorMessage?: string } = {},
) {
  const { enabled = true, errorMessage = "Request failed." } = options;

  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    isLoading: enabled,
    error: null,
  });
  const [reloadKey, setReloadKey] = useState(0);

  // The loader is usually an inline arrow, so keep it in a ref rather than in
  // the dependency array — otherwise every render would refetch.
  const loaderRef = useRef(loader);
  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    // The IIFE awaits immediately, so nothing sets state synchronously here.
    (async () => {
      try {
        const data = await loaderRef.current();
        if (!cancelled) setState({ data, isLoading: false, error: null });
      } catch (error) {
        if (!cancelled) {
          setState({ data: null, isLoading: false, error: toMessage(error, errorMessage) });
        }
      }
    })();

    return () => { cancelled = true; };
  }, [enabled, reloadKey, errorMessage]);

  /** Re-run the loader. Safe to pass straight to onClick. */
  const refresh = useCallback(() => {
    setState((previous) => ({ ...previous, isLoading: true, error: null }));
    setReloadKey((key) => key + 1);
  }, []);

  /** Replace the cached value locally, e.g. after a mutation. */
  const setData = useCallback((data: T) => {
    setState({ data, isLoading: false, error: null });
  }, []);

  return { ...state, refresh, setData };
}
