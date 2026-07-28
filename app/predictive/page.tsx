"use client";
import { useCallback, useMemo, useState } from "react";
import { Brain, Calculator } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { useAsyncData } from "@/lib/use-async-data";
import ExplanationPanel from "@/components/ExplanationPanel";
import UncertaintyBand from "@/components/UncertaintyBand";
import CounterfactualPanel from "@/components/CounterfactualPanel";
import { useAuth } from "@/lib/auth-context";
import type { Categories, Counterfactual, PredictionRecord } from "@/lib/types";
import {
  AuthRequired, ErrorState, PageHeader, SeverityBadge, Spinner,
} from "@/components/ui";

interface FormState {
  object: string;
  weather: string;
  terrain: string;
  time_of_day: string;
  confidence: number;
  distance_km: number;
}

export default function PredictivePage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const [form, setForm] = useState<FormState | null>(null);
  const [result, setResult] = useState<PredictionRecord | null>(null);
  const [cfs, setCfs] = useState<{ list: Counterfactual[]; robust: boolean } | null>(null);
  const [isScoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Enum values come from the backend so the form can never offer a class the
  // model does not know about.
  const {
    data: categories, isLoading: categoriesLoading,
    error: loadError, refresh: reloadCategories,
  } = useAsyncData<Categories>(
    async () => (await api.predict.categories()).categories,
    { errorMessage: "Could not load model categories." },
  );

  // Seed the form once the vocabulary arrives, without a synchronous effect.
  const [seededFor, setSeededFor] = useState<Categories | null>(null);
  if (categories && categories !== seededFor) {
    setSeededFor(categories);
    setForm({
      object: categories.DetectedObject[0],
      weather: categories.Weather[0],
      terrain: categories.Terrain[0],
      time_of_day: categories.TimeOfDay[0],
      confidence: 85,
      distance_km: 10,
    });
  }

  const submit = useCallback(async () => {
    if (!form) return;
    setScoring(true);
    setError(null);
    try {
      // Score and counterfactuals are independent; fetch them together.
      const [response, cfResponse] = await Promise.all([
        api.predict.score(form),
        api.predict.counterfactuals(form),
      ]);
      setResult(response.data);
      setCfs({ list: cfResponse.counterfactuals, robust: cfResponse.is_robust });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Scoring failed.");
    } finally {
      setScoring(false);
    }
  }, [form]);

  const selects = useMemo(() => {
    if (!categories) return [];
    return [
      { key: "object" as const, label: "Detected object", options: categories.DetectedObject },
      { key: "terrain" as const, label: "Terrain", options: categories.Terrain },
      { key: "weather" as const, label: "Weather", options: categories.Weather },
      { key: "time_of_day" as const, label: "Time of day", options: categories.TimeOfDay },
    ];
  }, [categories]);

  if (authLoading) return <Spinner label="Checking session" />;
  if (!isAuthenticated) return <AuthRequired />;
  if (loadError) return <ErrorState message={loadError} onRetry={reloadCategories} />;
  if (categoriesLoading || !form || !categories) return <Spinner label="Loading model metadata" />;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Machine learning"
        icon={Brain}
        title="Predictive"
        accent="Intel"
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="glass-panel rounded-2xl p-6" aria-labelledby="telemetry-heading">
          <h2 id="telemetry-heading" className="text-lg font-bold text-white mb-1">
            Telemetry input
          </h2>
          <p className="text-sm text-gray-400 mb-6">
            All six features influence the score. Values are validated server-side.
          </p>

          <div className="space-y-5">
            {selects.map(({ key, label, options }) => (
              <div key={key}>
                <label htmlFor={key} className="block text-sm text-gray-300 mb-2 font-medium">
                  {label}
                </label>
                <select
                  id={key}
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  className="w-full bg-aegis-surface border border-white/15 rounded-xl py-3 px-4 text-white focus:border-aegis-accent transition-colors"
                >
                  {options.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </div>
            ))}

            <div>
              <label htmlFor="confidence" className="block text-sm text-gray-300 mb-2 font-medium">
                Detection confidence:{" "}
                <span className="text-aegis-accent tabular-nums">{form.confidence}%</span>
              </label>
              <input
                id="confidence"
                type="range"
                min={0}
                max={100}
                step={1}
                value={form.confidence}
                onChange={(e) => setForm({ ...form, confidence: Number(e.target.value) })}
                className="w-full accent-[#00e5ff]"
              />
            </div>

            <div>
              <label htmlFor="distance" className="block text-sm text-gray-300 mb-2 font-medium">
                Distance to border:{" "}
                <span className="text-aegis-accent tabular-nums">
                  {form.distance_km.toFixed(1)} km
                </span>
              </label>
              <input
                id="distance"
                type="range"
                min={0.1}
                max={50}
                step={0.1}
                value={form.distance_km}
                onChange={(e) => setForm({ ...form, distance_km: Number(e.target.value) })}
                className="w-full accent-[#00e5ff]"
              />
            </div>

            <button
              onClick={submit}
              disabled={isScoring}
              className="w-full inline-flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary text-aegis-bg font-bold hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              <Calculator className="w-5 h-5" aria-hidden="true" />
              {isScoring ? "Scoring..." : "Calculate threat score"}
            </button>

            {error && (
              <p role="alert" className="text-sm text-aegis-danger">{error}</p>
            )}
          </div>
        </section>

        <section className="glass-panel rounded-2xl p-6" aria-labelledby="result-heading">
          <h2 id="result-heading" className="text-lg font-bold text-white mb-6">
            Assessment
          </h2>

          {!result ? (
            <p className="text-aegis-muted text-sm py-12 text-center">
              Submit telemetry to generate an assessment.
            </p>
          ) : (
            <div className="space-y-6">
              <div className="text-center py-6">
                <p
                  className="text-6xl font-black tabular-nums"
                  style={{
                    color:
                      result.ml_output.threat_score >= 80 ? "#ff3366"
                        : result.ml_output.threat_score >= 60 ? "#ffb800"
                        : result.ml_output.threat_score >= 40 ? "#00e5ff"
                        : "#00ff9d",
                  }}
                >
                  {result.ml_output.threat_score}
                </p>
                <p className="text-sm text-aegis-muted mt-1">out of 99</p>
                <div className="mt-4">
                  <SeverityBadge level={result.ml_output.threat_level} />
                </div>
              </div>

              {result.ml_output.interval && (
                <UncertaintyBand
                  interval={result.ml_output.interval}
                  score={result.ml_output.threat_score}
                />
              )}

              <dl className="space-y-3 border-t border-white/10 pt-5">
                {Object.entries(result.telemetry).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-4 text-sm">
                    <dt className="text-aegis-muted capitalize">
                      {key.replace(/_/g, " ")}
                    </dt>
                    <dd className="text-white font-medium">
                      {typeof value === "number" ? value.toFixed(1) : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>

              <p className="text-xs text-aegis-muted leading-relaxed border-t border-white/10 pt-4">
                Model: {result.ml_output.model_version}. Trained on synthetic
                telemetry; the score is advisory decision support and requires
                analyst confirmation.
              </p>
            </div>
          )}
        </section>
      </div>

      {/* Attribution and counterfactuals for the most recent assessment. */}
      {result && (
        <div className="grid gap-6 lg:grid-cols-2">
          {result.ml_output.explanation && (
            <ExplanationPanel explanation={result.ml_output.explanation} />
          )}
          {cfs && (
            <CounterfactualPanel
              counterfactuals={cfs.list}
              isRobust={cfs.robust}
              currentLevel={result.ml_output.threat_level}
            />
          )}
        </div>
      )}
    </div>
  );
}
