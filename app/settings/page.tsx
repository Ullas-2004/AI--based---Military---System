"use client";
import { CheckCircle2, Settings, XCircle } from "lucide-react";

import { api } from "@/lib/api";
import { useAsyncData } from "@/lib/use-async-data";
import { useAuth } from "@/lib/auth-context";
import type { HealthResponse } from "@/lib/types";
import { ErrorState, PageHeader, Spinner } from "@/components/ui";

function StatusRow({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-4 border-b border-white/5 last:border-0">
      <div className="min-w-0">
        <p className="text-white font-medium">{label}</p>
        <p className="text-xs text-aegis-muted mt-0.5">{detail}</p>
      </div>
      <span
        className={`inline-flex items-center gap-1.5 text-sm font-semibold shrink-0 ${
          ok ? "text-aegis-success" : "text-aegis-warning"
        }`}
      >
        {ok
          ? <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
          : <XCircle className="w-4 h-4" aria-hidden="true" />}
        {ok ? "Online" : "Offline"}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const { user, isAuthenticated } = useAuth();
  const { data: health, isLoading, error, refresh } = useAsyncData<HealthResponse>(
    () => api.health(),
    { errorMessage: "Could not reach the backend." },
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Configuration"
        icon={Settings}
        title="System"
        accent="Settings"
        actions={
          <button
            onClick={refresh}
            className="px-5 py-2.5 rounded-xl bg-white/5 border border-white/15 text-gray-200 font-medium hover:bg-white/10 transition-colors"
          >
            Refresh
          </button>
        }
      />

      {isLoading ? (
        <Spinner label="Querying subsystems" />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="glass-panel rounded-2xl p-6" aria-labelledby="subsystems-heading">
            <h2 id="subsystems-heading" className="text-lg font-bold text-white mb-4">
              Subsystem status
            </h2>
            <StatusRow
              label="MongoDB"
              ok={health?.subsystems.database ?? false}
              detail="Persistence for detections, predictions, users and the audit trail."
            />
            <StatusRow
              label="Threat prediction model"
              ok={health?.subsystems.threat_model ?? false}
              detail="XGBoost regressor. Regenerate with: python api/train_threat_model.py"
            />
            <StatusRow
              label="Generative assistant"
              ok={health?.subsystems.assistant ?? false}
              detail="Requires GROQ_API_KEY. Offline mode returns raw telemetry only."
            />
          </section>

          <section className="glass-panel rounded-2xl p-6" aria-labelledby="session-heading">
            <h2 id="session-heading" className="text-lg font-bold text-white mb-4">
              Session
            </h2>
            <dl className="space-y-3 text-sm">
              {[
                ["Signed in", isAuthenticated ? "Yes" : "No"],
                ["Username", user?.username ?? "n/a"],
                ["Role", user?.role ?? "n/a"],
                ["Backend version", health?.version ?? "unknown"],
                ["Environment", health?.environment ?? "unknown"],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between gap-4">
                  <dt className="text-aegis-muted">{label}</dt>
                  <dd className="text-white font-medium capitalize">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="text-xs text-aegis-muted mt-5 pt-4 border-t border-white/10 leading-relaxed">
              Tokens are held in <code className="text-aegis-accent">sessionStorage</code>{" "}
              and expire with the browser tab. Configuration is managed through
              the <code className="text-aegis-accent">.env</code> file on the
              server; see <code className="text-aegis-accent">.env.example</code>.
            </p>
          </section>

          <section
            className="glass-panel rounded-2xl p-6 lg:col-span-2 border-l-4 border-aegis-warning"
            aria-labelledby="limitations-heading"
          >
            <h2 id="limitations-heading" className="text-lg font-bold text-white mb-3">
              Known limitations
            </h2>
            <ul className="space-y-2.5 text-sm text-gray-300 list-disc list-inside leading-relaxed">
              <li>
                Threat scores come from a model trained on <strong>synthetic</strong>{" "}
                telemetry, not real operational data.
              </li>
              <li>
                Object detection uses stock COCO-trained YOLO weights. COCO has no
                tank, UAV or military helicopter class; military labels are a
                documented proxy mapping.
              </li>
              <li>
                Map tiles are fetched from a public CDN and require internet access.
              </li>
              <li>
                This is a demonstration system and is not accredited for
                operational use.
              </li>
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
