"use client";
/**
 * Subscribes to the backend Server-Sent Events stream.
 *
 * EventSource is used rather than a WebSocket: alerts flow one way, and SSE
 * reconnects automatically, survives proxies, and needs no extra dependency.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { getToken } from "./api";

export interface AlertEvent {
  /** Client-side id, so React keys stay stable. */
  key: string;
  type: "detection" | "threat_assessment" | string;
  timestamp: string;
  data: Record<string, unknown>;
}

const MAX_RETAINED = 30;

export function useAlertStream(enabled: boolean) {
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [isConnected, setConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  const dismiss = useCallback((key: string) => {
    setEvents((prev) => prev.filter((e) => e.key !== key));
  }, []);

  const clear = useCallback(() => setEvents([]), []);

  useEffect(() => {
    if (!enabled) return;
    const token = getToken();
    if (!token) return;

    // EventSource cannot set headers, so the token travels as a query param.
    // The backend verifies it fully and keeps it out of the access log.
    const source = new EventSource(
      `/api/stream/alerts?token=${encodeURIComponent(token)}`,
    );
    sourceRef.current = source;

    source.addEventListener("connected", () => setConnected(true));

    source.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data);
        setEvents((prev) => [
          {
            key: `${parsed.timestamp}-${Math.random().toString(36).slice(2, 8)}`,
            type: parsed.type,
            timestamp: parsed.timestamp,
            data: parsed.data ?? {},
          },
          ...prev,
        ].slice(0, MAX_RETAINED));
      } catch {
        // A malformed frame should never take the stream down.
      }
    };

    source.onerror = () => {
      // EventSource retries on its own; reflect the gap in the UI meanwhile.
      setConnected(false);
    };

    return () => {
      source.close();
      sourceRef.current = null;
      setConnected(false);
    };
  }, [enabled]);

  return { events, isConnected, dismiss, clear };
}
