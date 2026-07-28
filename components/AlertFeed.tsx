"use client";
/** Live alert toasts driven by the Server-Sent Events stream. */
import { AlertTriangle, Crosshair, Radio, X } from "lucide-react";

import { useAuth } from "@/lib/auth-context";
import { useAlertStream, type AlertEvent } from "@/lib/use-alert-stream";

function describe(event: AlertEvent) {
  const d = event.data;
  if (event.type === "threat_assessment") {
    const level = String(d.threat_level ?? "");
    return {
      icon: AlertTriangle,
      title: `${level} threat assessed`,
      body: `${d.object} in ${d.terrain} at ${d.distance_km} km — score ${d.threat_score}`,
      critical: level === "CRITICAL",
    };
  }
  if (event.type === "detection") {
    return {
      icon: Crosshair,
      title: `${d.total_objects} object(s) detected`,
      body: `${d.top_object} at ${d.top_confidence}% in ${d.filename}`,
      critical: false,
    };
  }
  return { icon: Radio, title: event.type, body: JSON.stringify(d).slice(0, 80), critical: false };
}

export default function AlertFeed() {
  const { isAuthenticated } = useAuth();
  const { events, isConnected, dismiss } = useAlertStream(isAuthenticated);

  if (!isAuthenticated) return null;

  // Only the newest few are shown as toasts; the rest stay in the buffer.
  const visible = events.slice(0, 4);

  return (
    <>
      {/* Connection indicator, bottom-left so it never covers the toasts. */}
      <div
        className="fixed bottom-4 left-4 z-40 flex items-center gap-2 px-3 py-1.5 rounded-full glass-panel text-xs"
        role="status"
        aria-live="off"
      >
        <span
          className={`w-2 h-2 rounded-full ${
            isConnected ? "bg-aegis-success animate-pulse" : "bg-aegis-muted"
          }`}
          aria-hidden="true"
        />
        <span className="text-aegis-muted">
          {isConnected ? "Live feed connected" : "Live feed reconnecting"}
        </span>
      </div>

      <div
        className="fixed top-20 right-4 z-40 w-[min(22rem,calc(100vw-2rem))] space-y-2.5"
        role="region"
        aria-label="Live alerts"
      >
        {visible.map((event) => {
          const { icon: Icon, title, body, critical } = describe(event);
          return (
            <article
              key={event.key}
              className={`glass-panel rounded-xl p-3.5 border-l-4 ${
                critical ? "border-aegis-danger" : "border-aegis-accent"
              }`}
              // Assertive only for CRITICAL; routine detections shouldn't
              // interrupt a screen-reader user mid-sentence.
              aria-live={critical ? "assertive" : "polite"}
            >
              <div className="flex items-start gap-3">
                <Icon
                  className={`w-4 h-4 mt-0.5 shrink-0 ${
                    critical ? "text-aegis-danger" : "text-aegis-accent"
                  }`}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-white">{title}</p>
                  <p className="text-xs text-gray-300 mt-0.5 break-words">{body}</p>
                  <p className="text-[11px] text-aegis-muted mt-1 font-mono">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </p>
                </div>
                <button
                  onClick={() => dismiss(event.key)}
                  className="text-aegis-muted hover:text-white transition-colors shrink-0"
                  aria-label="Dismiss alert"
                >
                  <X className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}
