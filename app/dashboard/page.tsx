"use client";
import Link from "next/link";
import { Activity, Crosshair, Gauge, Home, Radar } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useAsyncData } from "@/lib/use-async-data";
import {
  AuthRequired, EmptyState, ErrorState, PageHeader, SeverityBadge, Spinner,
} from "@/components/ui";

const CHART_TOOLTIP = {
  backgroundColor: "rgba(5,7,13,0.95)",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: "12px",
  color: "#fff",
};

function scoreColour(score: number) {
  if (score >= 80) return "#ff3366";
  if (score >= 60) return "#ffb800";
  if (score >= 40) return "#00e5ff";
  return "#00ff9d";
}

export default function DashboardPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  // These three are independent, so fetch them concurrently rather than
  // serialising three round-trips.
  const { data, isLoading, error, refresh } = useAsyncData(
    async () => {
      const [forecastRes, predictionsRes, detectionsRes] = await Promise.all([
        api.predict.forecast(),
        api.predict.history(10),
        api.threats.history(10),
      ]);
      return {
        forecast: forecastRes.forecast,
        predictions: predictionsRes.data,
        detections: detectionsRes.data,
      };
    },
    { enabled: isAuthenticated, errorMessage: "Could not load dashboard data." },
  );

  if (authLoading) return <Spinner label="Checking session" />;
  if (!isAuthenticated) return <AuthRequired />;
  if (isLoading) return <Spinner label="Loading intelligence picture" />;
  if (error) return <ErrorState message={error} onRetry={refresh} />;

  const forecast = data?.forecast ?? null;
  const predictions = data?.predictions ?? [];
  const detections = data?.detections ?? [];

  const totalDetections = detections.reduce((sum, d) => sum + d.total_objects, 0);
  const criticalCount = predictions.filter(
    (p) => p.ml_output.threat_level === "CRITICAL",
  ).length;
  const meanScore = predictions.length
    ? predictions.reduce((sum, p) => sum + p.ml_output.threat_score, 0) / predictions.length
    : null;

  const kpis = [
    {
      label: "Critical predictions",
      value: String(criticalCount),
      caption: `of ${predictions.length} recent assessments`,
      colour: "text-aegis-danger",
      icon: Radar,
    },
    {
      label: "Objects detected",
      value: String(totalDetections),
      caption: `across ${detections.length} uploads`,
      colour: "text-aegis-accent",
      icon: Crosshair,
    },
    {
      label: "Mean threat score",
      value: meanScore === null ? "n/a" : meanScore.toFixed(1),
      caption: meanScore === null ? "no predictions yet" : "recent window",
      colour: "text-aegis-warning",
      icon: Gauge,
    },
    {
      label: "Border risk",
      value: forecast?.available ? (forecast.border_risk ?? "UNKNOWN") : "n/a",
      caption: forecast?.available
        ? `${forecast.sample_size} sample(s)`
        : "insufficient data",
      colour: "text-aegis-success",
      icon: Activity,
    },
  ];

  const chartData = predictions
    .slice()
    .reverse()
    .map((p, i) => ({
      name: `${p.telemetry.object} ${i + 1}`,
      score: p.ml_output.threat_score,
    }));

  return (
    <div className="space-y-6 pb-8">
      <PageHeader
        eyebrow="Real-time intelligence"
        icon={Home}
        title="Tactical"
        accent="Dashboard"
        actions={
          <button
            onClick={refresh}
            className="px-5 py-2.5 rounded-xl bg-white/5 border border-white/15 text-gray-200 font-medium hover:bg-white/10 transition-colors"
          >
            Refresh
          </button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map(({ label, value, caption, colour, icon: Icon }) => (
          <div key={label} className="glass-panel rounded-2xl p-5">
            <div className="flex items-start justify-between gap-3">
              <p className="text-xs font-medium tracking-wide uppercase text-aegis-muted">
                {label}
              </p>
              <Icon className={`w-4 h-4 shrink-0 ${colour}`} aria-hidden="true" />
            </div>
            <p className={`text-3xl font-black mt-3 ${colour}`}>{value}</p>
            <p className="text-xs text-aegis-muted mt-1.5">{caption}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <section
          className="glass-panel rounded-2xl p-6 lg:col-span-3"
          aria-labelledby="scores-heading"
        >
          <h2 id="scores-heading" className="text-lg font-bold text-white mb-5">
            Recent threat scores
          </h2>
          {chartData.length === 0 ? (
            <EmptyState
              title="No predictions recorded yet"
              hint="Score telemetry from the Predictive Intel module to populate this chart."
            />
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 5, right: 12, bottom: 40, left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis
                    dataKey="name" stroke="#94a3b8" fontSize={11}
                    angle={-35} textAnchor="end" interval={0}
                  />
                  <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 100]} />
                  <Tooltip contentStyle={CHART_TOOLTIP} cursor={{ fill: "rgba(255,255,255,0.05)" }} />
                  <Bar dataKey="score" name="Threat score" radius={[6, 6, 0, 0]}>
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={scoreColour(entry.score)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        <section
          className="glass-panel rounded-2xl p-6 lg:col-span-2"
          aria-labelledby="forecast-heading"
        >
          <h2 id="forecast-heading" className="text-lg font-bold text-white mb-5">
            24-hour outlook
          </h2>
          {!forecast?.available ? (
            <EmptyState
              title="Insufficient data"
              hint={forecast?.reason ?? "No prediction history recorded yet."}
            />
          ) : (
            <dl className="space-y-4">
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-aegis-muted">Border risk</dt>
                <dd><SeverityBadge level={forecast.border_risk ?? "UNKNOWN"} /></dd>
              </div>
              {[
                ["Mean threat score", forecast.mean_threat_score],
                ["Peak threat score", forecast.peak_threat_score],
                ["Aerial activity", `${forecast.aerial_activity_share}%`],
                ["Ground activity", `${forecast.ground_activity_share}%`],
                ["Sample size", forecast.sample_size],
              ].map(([label, value]) => (
                <div key={String(label)} className="flex items-center justify-between gap-4">
                  <dt className="text-sm text-aegis-muted">{label}</dt>
                  <dd className="font-bold text-white tabular-nums">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      </div>

      <section className="glass-panel rounded-2xl p-6" aria-labelledby="recent-heading">
        <div className="flex items-center justify-between gap-4 mb-5">
          <h2 id="recent-heading" className="text-lg font-bold text-white">
            Latest assessments
          </h2>
          <Link href="/history" className="text-sm text-aegis-accent hover:text-white transition-colors">
            View all
          </Link>
        </div>
        {predictions.length === 0 ? (
          <EmptyState title="No assessments yet" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-aegis-muted border-b border-white/10">
                <tr>
                  <th scope="col" className="py-3 pr-4">Object</th>
                  <th scope="col" className="py-3 pr-4">Terrain</th>
                  <th scope="col" className="py-3 pr-4">Distance</th>
                  <th scope="col" className="py-3 pr-4">Score</th>
                  <th scope="col" className="py-3">Level</th>
                </tr>
              </thead>
              <tbody>
                {predictions.slice(0, 5).map((p, i) => (
                  <tr key={p.id ?? i} className="border-b border-white/5">
                    <td className="py-3 pr-4 font-medium text-white">{p.telemetry.object}</td>
                    <td className="py-3 pr-4 text-gray-300">{p.telemetry.terrain}</td>
                    <td className="py-3 pr-4 text-gray-300 tabular-nums">
                      {p.telemetry.distance_km.toFixed(1)} km
                    </td>
                    <td className="py-3 pr-4 text-white font-semibold tabular-nums">
                      {p.ml_output.threat_score}
                    </td>
                    <td className="py-3">
                      <SeverityBadge level={p.ml_output.threat_level} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
