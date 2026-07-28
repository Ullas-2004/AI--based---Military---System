"use client";
import { useMemo } from "react";
import dynamic from "next/dynamic";
import { Activity, AlertTriangle, MapPin, Radio, Shield } from "lucide-react";

import { api } from "@/lib/api";
import { useAsyncData } from "@/lib/use-async-data";
import { useAuth } from "@/lib/auth-context";
import type { MapMarker } from "@/lib/types";
import { AuthRequired, ErrorState, PageHeader, Spinner } from "@/components/ui";

// Leaflet touches `window` at module scope, so it must not be server-rendered.
const MapComponent = dynamic(() => import("./MapComponent"), {
  ssr: false,
  loading: () => <Spinner label="Loading tactical map" />,
});

export default function MapsPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const { data, isLoading, error, refresh } = useAsyncData(
    () => api.data.mapMarkers(),
    { enabled: isAuthenticated, errorMessage: "Could not load map markers." },
  );

  const markers: MapMarker[] = useMemo(() => data?.markers ?? [], [data]);
  const centre = data?.centre ?? { lat: 34.05, lng: 72.4 };
  const isDemo = data?.is_demo ?? false;

  // Counts are derived from the actual marker set rather than hardcoded.
  const stats = useMemo(() => {
    const threats = markers.filter((m) => m.type === "Threat");
    const critical = threats.filter((m) => m.severity === "CRITICAL").length;
    return [
      {
        label: "Active threats", value: String(threats.length),
        icon: AlertTriangle, colour: "text-aegis-danger",
      },
      {
        label: "Patrol units",
        value: String(markers.filter((m) => m.type === "Patrol").length),
        icon: Shield, colour: "text-aegis-success",
      },
      {
        label: "Sensors online",
        value: String(markers.filter((m) => m.type === "Sensor").length),
        icon: Radio, colour: "text-aegis-accent",
      },
      {
        label: "Critical alerts", value: String(critical),
        icon: Activity, colour: critical > 0 ? "text-aegis-danger" : "text-aegis-warning",
      },
    ];
  }, [markers]);

  if (authLoading) return <Spinner label="Checking session" />;
  if (!isAuthenticated) return <AuthRequired />;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Geographical intelligence"
        icon={MapPin}
        title="GIS"
        accent="Tactical Map"
        actions={
          <button
            onClick={refresh}
            className="px-5 py-2.5 rounded-xl bg-white/5 border border-white/15 text-gray-200 font-medium hover:bg-white/10 transition-colors"
          >
            Refresh
          </button>
        }
      />

      {isDemo && !isLoading && (
        <p className="px-4 py-3 rounded-xl bg-aegis-warning/10 border border-aegis-warning/30 text-sm text-aegis-warning">
          Showing demonstration markers: no georeferenced predictions are stored yet.
        </p>
      )}

      <div className="grid gap-4 grid-cols-2 xl:grid-cols-4">
        {stats.map(({ label, value, icon: Icon, colour }) => (
          <div key={label} className="glass-panel rounded-2xl p-4 flex items-center gap-4">
            <div className={`w-11 h-11 shrink-0 rounded-xl bg-white/5 flex items-center justify-center ${colour}`}>
              <Icon className="w-5 h-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-aegis-muted truncate">{label}</p>
              <p className={`text-xl font-bold ${colour}`}>{value}</p>
            </div>
          </div>
        ))}
      </div>

      {error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : (
        <div className="glass-panel rounded-2xl overflow-hidden relative h-[60vh] min-h-[420px]">
          {isLoading ? (
            <Spinner label="Loading markers" />
          ) : (
            <>
              <MapComponent markers={markers} centre={centre} />
              <div className="absolute bottom-5 left-5 glass-panel rounded-xl p-4 z-[1000]">
                <p className="text-xs text-aegis-muted font-semibold mb-2.5 uppercase tracking-wider">
                  Legend
                </p>
                <ul className="space-y-1.5">
                  {[
                    ["#ff3366", "Threat detection"],
                    ["#00ff9d", "Patrol unit"],
                    ["#00e5ff", "Sensor / radar"],
                  ].map(([colour, label]) => (
                    <li key={label} className="flex items-center gap-2">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: colour }}
                        aria-hidden="true"
                      />
                      <span className="text-xs text-gray-300">{label}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
