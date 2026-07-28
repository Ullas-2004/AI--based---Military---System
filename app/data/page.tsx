"use client";
import { useCallback, useState } from "react";
import { Database, Download, FileText, Table } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { api, ApiError } from "@/lib/api";
import { useAsyncData } from "@/lib/use-async-data";
import { useAuth } from "@/lib/auth-context";
import type { Analytics } from "@/lib/types";
import {
  AuthRequired, EmptyState, ErrorState, PageHeader, Spinner,
} from "@/components/ui";

const PIE_COLOURS = ["#00e5ff", "#ff3366", "#ffb800", "#8a5cff", "#00ff9d", "#94a3b8"];
const TOOLTIP_STYLE = {
  backgroundColor: "rgba(5,7,13,0.95)",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: "12px",
  color: "#fff",
};

function riskColour(risk: number) {
  if (risk >= 80) return "#ff3366";
  if (risk >= 60) return "#ffb800";
  if (risk >= 40) return "#00e5ff";
  return "#00ff9d";
}

export default function DataHubPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const { data: analytics, isLoading, error, refresh } = useAsyncData<Analytics>(
    () => api.data.analytics(),
    { enabled: isAuthenticated, errorMessage: "Could not load analytics." },
  );

  const [isDownloading, setDownloading] = useState(false);
  const [isExporting, setExporting] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  /** Trigger a browser download for a fetched blob. */
  const saveBlob = useCallback((blob: Blob, filename: string) => {
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }, []);

  const exportCsv = useCallback(async () => {
    setExporting(true);
    setDownloadError(null);
    try {
      const blob = await api.data.exportCsv("predictions");
      saveBlob(blob, `aegisai_predictions_${new Date().toISOString().slice(0, 10)}.csv`);
    } catch (err) {
      setDownloadError(
        err instanceof ApiError ? err.message : "Could not export the dataset.",
      );
    } finally {
      setExporting(false);
    }
  }, [saveBlob]);

  const downloadReport = useCallback(async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const blob = await api.data.downloadReport();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `AegisAI_Situation_Report_${new Date()
        .toISOString()
        .slice(0, 19)
        .replace(/[:T]/g, "")}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Revoke on the next tick, once the browser has started the download.
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (err) {
      setDownloadError(
        err instanceof ApiError ? err.message : "Could not generate the report.",
      );
    } finally {
      setDownloading(false);
    }
  }, []);

  if (authLoading) return <Spinner label="Checking session" />;
  if (!isAuthenticated) return <AuthRequired />;

  return (
    <div className="space-y-6 pb-8">
      <PageHeader
        eyebrow="Analytics"
        icon={Database}
        title="Intelligence"
        accent="Data Hub"
        actions={
          <div className="flex flex-wrap gap-3">
          <button
            onClick={exportCsv}
            disabled={isExporting}
            className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-white/5 border border-white/15 text-gray-200 font-semibold hover:bg-white/10 transition-colors disabled:opacity-40"
          >
            <Table className="w-5 h-5" aria-hidden="true" />
            {isExporting ? "Exporting..." : "Export CSV"}
          </button>
          <button
            onClick={downloadReport}
            disabled={isDownloading}
            className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary text-aegis-bg font-bold hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {isDownloading
              ? <FileText className="w-5 h-5 animate-pulse" aria-hidden="true" />
              : <Download className="w-5 h-5" aria-hidden="true" />}
            {isDownloading ? "Compiling PDF..." : "Export situation report"}
          </button>
          </div>
        }
      />

      {downloadError && (
        <p role="alert" className="px-4 py-3 rounded-xl bg-aegis-danger/10 border border-aegis-danger/30 text-sm text-aegis-danger">
          {downloadError}
        </p>
      )}

      {isLoading ? (
        <Spinner label="Aggregating analytics" />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : !analytics?.available ? (
        <div className="glass-panel rounded-2xl">
          <EmptyState
            title="No activity to analyse"
            hint={
              analytics?.reason ??
              "Run detections and threat assessments to populate these charts."
            }
          />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="glass-panel rounded-2xl p-6" aria-labelledby="trend-heading">
            <h2 id="trend-heading" className="text-lg font-bold text-white mb-5">
              Activity over the last {analytics.window_hours} hours
            </h2>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={analytics.trend} margin={{ top: 5, right: 16, bottom: 5, left: -16 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                  <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} />
                  <YAxis stroke="#94a3b8" fontSize={11} allowDecimals={false} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ paddingTop: 12, fontSize: 12 }} />
                  <Line
                    type="monotone" dataKey="threats" name="Assessments"
                    stroke="#ff3366" strokeWidth={2.5} dot={{ r: 3 }}
                  />
                  <Line
                    type="monotone" dataKey="detections" name="Objects detected"
                    stroke="#00e5ff" strokeWidth={2.5} dot={{ r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="glass-panel rounded-2xl p-6" aria-labelledby="breakdown-heading">
            <h2 id="breakdown-heading" className="text-lg font-bold text-white mb-5">
              Object classification breakdown
            </h2>
            <div className="h-72">
              {analytics.object_breakdown.length === 0 ? (
                <EmptyState title="No classified objects yet" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={analytics.object_breakdown}
                      cx="50%" cy="45%" innerRadius={70} outerRadius={100}
                      paddingAngle={4} dataKey="value" stroke="none"
                    >
                      {analytics.object_breakdown.map((_, index) => (
                        <Cell key={index} fill={PIE_COLOURS[index % PIE_COLOURS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Legend wrapperStyle={{ paddingTop: 8, fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </section>

          <section
            className="glass-panel rounded-2xl p-6 lg:col-span-2"
            aria-labelledby="sector-heading"
          >
            <h2 id="sector-heading" className="text-lg font-bold text-white mb-5">
              Mean threat score by terrain
            </h2>
            <div className="h-72">
              {analytics.sector_risk.length === 0 ? (
                <EmptyState title="No scored assessments yet" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={analytics.sector_risk} margin={{ top: 5, right: 16, bottom: 5, left: -16 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" vertical={false} />
                    <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                    <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 100]} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.05)" }} />
                    <Bar dataKey="risk" name="Mean threat score" radius={[6, 6, 0, 0]}>
                      {analytics.sector_risk.map((entry, index) => (
                        <Cell key={index} fill={riskColour(entry.risk)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
