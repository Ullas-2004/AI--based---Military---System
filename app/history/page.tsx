"use client";
import { useCallback, useEffect, useState } from "react";
import { Check, RotateCcw, ShieldAlert, X } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useAsyncData } from "@/lib/use-async-data";
import type { ReviewMetrics, ReviewStatus } from "@/lib/types";
import {
  AuthRequired, EmptyState, ErrorState, PageHeader, Pagination, SeverityBadge, Spinner,
} from "@/components/ui";

type Tab = "detections" | "predictions";

const PAGE_SIZE = 25;

const REVIEW_LABELS: Record<string, { text: string; className: string }> = {
  confirmed: { text: "Confirmed", className: "bg-aegis-success/20 text-aegis-success border-aegis-success/40" },
  false_positive: { text: "False positive", className: "bg-aegis-danger/20 text-aegis-danger border-aegis-danger/40" },
  pending_analyst_review: { text: "Pending", className: "bg-white/10 text-aegis-muted border-white/20" },
};

function ReviewBadge({ status }: { status: string }) {
  const style = REVIEW_LABELS[status] ?? REVIEW_LABELS.pending_analyst_review;
  return (
    <span className={`inline-block text-xs font-semibold px-2.5 py-1 rounded-full border whitespace-nowrap ${style.className}`}>
      {style.text}
    </span>
  );
}

function ReviewActions({
  id, current, busy, onReview,
}: {
  id: string;
  current: string;
  busy: boolean;
  onReview: (id: string, status: ReviewStatus) => void;
}) {
  const reviewed = current === "confirmed" || current === "false_positive";
  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={() => onReview(id, "confirmed")}
        disabled={busy || current === "confirmed"}
        title="Confirm as a genuine contact"
        className="p-1.5 rounded-lg bg-white/5 border border-white/15 text-aegis-success hover:bg-aegis-success/15 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Confirm detection"
      >
        <Check className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
      <button
        onClick={() => onReview(id, "false_positive")}
        disabled={busy || current === "false_positive"}
        title="Reject as a false positive"
        className="p-1.5 rounded-lg bg-white/5 border border-white/15 text-aegis-danger hover:bg-aegis-danger/15 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Mark as false positive"
      >
        <X className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
      {reviewed && (
        <button
          onClick={() => onReview(id, "pending_analyst_review")}
          disabled={busy}
          title="Return to the review queue"
          className="p-1.5 rounded-lg bg-white/5 border border-white/15 text-aegis-muted hover:bg-white/10 transition-colors disabled:opacity-30"
          aria-label="Undo review"
        >
          <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

function formatTimestamp(iso: string | undefined) {
  if (!iso) return "N/A";
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? "N/A"
    : date.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

export default function HistoryPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const [tab, setTab] = useState<Tab>("detections");
  // Independent offsets so switching tabs preserves each one's position.
  const [detectionSkip, setDetectionSkip] = useState(0);
  const [predictionSkip, setPredictionSkip] = useState(0);

  const { data, isLoading, error, refresh } = useAsyncData(
    async () => {
      const [detectionsRes, predictionsRes] = await Promise.all([
        api.threats.history(PAGE_SIZE, detectionSkip),
        api.predict.history(PAGE_SIZE, predictionSkip),
      ]);
      return { detections: detectionsRes, predictions: predictionsRes };
    },
    { enabled: isAuthenticated, errorMessage: "Could not load history." },
  );

  // Re-fetch when either offset changes.
  useEffect(() => {
    if (isAuthenticated) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh is stable
  }, [detectionSkip, predictionSkip]);

  // Model-quality metrics derived from analyst verdicts.
  const { data: metrics, refresh: refreshMetrics } = useAsyncData<ReviewMetrics>(
    async () => (await api.threats.reviewMetrics()).metrics,
    { enabled: isAuthenticated, errorMessage: "Could not load review metrics." },
  );

  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const submitReview = useCallback(
    async (id: string, status: ReviewStatus) => {
      setReviewingId(id);
      setReviewError(null);
      try {
        await api.threats.review(id, status);
        refresh();         // pull the authoritative record back
        refreshMetrics();  // keep the metrics strip in step
      } catch (err) {
        setReviewError(
          err instanceof ApiError ? err.message : "Could not record the review.",
        );
      } finally {
        setReviewingId(null);
      }
    },
    [refresh, refreshMetrics],
  );

  if (authLoading) return <Spinner label="Checking session" />;
  if (!isAuthenticated) return <AuthRequired />;

  const detections = data?.detections.data ?? [];
  const predictions = data?.predictions.data ?? [];
  const detectionTotal = data?.detections.pagination.total ?? 0;
  const predictionTotal = data?.predictions.pagination.total ?? 0;

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: "detections", label: "Vision detections", count: detectionTotal },
    { id: "predictions", label: "Threat assessments", count: predictionTotal },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Audit trail"
        icon={ShieldAlert}
        title="Threat"
        accent="Intelligence"
        actions={
          <button
            onClick={refresh}
            className="px-5 py-2.5 rounded-xl bg-white/5 border border-white/15 text-gray-200 font-medium hover:bg-white/10 transition-colors"
          >
            Refresh
          </button>
        }
      />

      {/* Model quality, measured from analyst verdicts rather than assumed. */}
      {metrics && metrics.total > 0 && (
        <section
          className="glass-panel rounded-2xl p-4 grid grid-cols-2 sm:grid-cols-4 gap-4"
          aria-label="Model review metrics"
        >
          {[
            { label: "Reviewed", value: `${metrics.reviewed} / ${metrics.total}`, tone: "text-white" },
            { label: "Confirmed", value: metrics.confirmed, tone: "text-aegis-success" },
            { label: "False positives", value: metrics.false_positive, tone: "text-aegis-danger" },
            {
              label: "False-positive rate",
              value: metrics.false_positive_rate === null
                ? "no data"
                : `${metrics.false_positive_rate}%`,
              tone: "text-aegis-warning",
            },
          ].map(({ label, value, tone }) => (
            <div key={label}>
              <p className="text-xs uppercase tracking-wide text-aegis-muted">{label}</p>
              <p className={`text-xl font-bold mt-1 ${tone}`}>{value}</p>
            </div>
          ))}
        </section>
      )}

      {reviewError && (
        <p role="alert" className="px-4 py-3 rounded-xl bg-aegis-danger/10 border border-aegis-danger/30 text-sm text-aegis-danger">
          {reviewError}
        </p>
      )}

      <div role="tablist" aria-label="History type" className="flex flex-wrap gap-2">
        {tabs.map(({ id, label, count }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            onClick={() => setTab(id)}
            className={`px-5 py-2.5 rounded-xl font-semibold text-sm transition-colors ${
              tab === id
                ? "bg-gradient-to-r from-aegis-accent/20 to-aegis-accent-secondary/20 border border-aegis-accent/40 text-white"
                : "bg-white/5 border border-white/10 text-gray-400 hover:text-white"
            }`}
          >
            {label}
            <span className="ml-2 text-xs text-aegis-muted">({count})</span>
          </button>
        ))}
      </div>

      {isLoading ? (
        <Spinner label="Loading history" />
      ) : error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : (
        <section
          id={`panel-${tab}`}
          role="tabpanel"
          className="glass-panel rounded-2xl overflow-hidden"
        >
          {tab === "detections" ? (
            detections.length === 0 ? (
              <EmptyState
                title="No detections recorded"
                hint="Upload an image in the Vision Engine to create a record."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Vision detection history</caption>
                  <thead className="text-xs uppercase tracking-wider text-aegis-muted border-b border-white/10">
                    <tr>
                      <th scope="col" className="p-4">Timestamp</th>
                      <th scope="col" className="p-4">Source file</th>
                      <th scope="col" className="p-4">Objects</th>
                      <th scope="col" className="p-4">Top detection</th>
                      <th scope="col" className="p-4">Review</th>
                      <th scope="col" className="p-4">Analyst verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detections.map((record, i) => {
                      const top = record.detections[0];
                      return (
                        <tr
                          key={record.id ?? i}
                          className="border-b border-white/5 hover:bg-white/5 transition-colors"
                        >
                          <td className="p-4 text-gray-300 font-mono text-xs whitespace-nowrap">
                            {formatTimestamp(record.created_at)}
                          </td>
                          <td className="p-4 text-gray-200 max-w-[14rem] truncate">
                            {record.original_filename}
                          </td>
                          <td className="p-4 text-white font-semibold tabular-nums">
                            {record.total_objects}
                          </td>
                          <td className="p-4 text-gray-300">
                            {top ? `${top.object} (${top.confidence}%)` : "None"}
                          </td>
                          <td className="p-4">
                            <ReviewBadge status={record.status} />
                          </td>
                          <td className="p-4">
                            {record.id && (
                              <ReviewActions
                                id={record.id}
                                current={record.status}
                                busy={reviewingId === record.id}
                                onReview={submitReview}
                              />
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <Pagination
                  total={detectionTotal}
                  limit={PAGE_SIZE}
                  skip={detectionSkip}
                  onChange={setDetectionSkip}
                  isLoading={isLoading}
                />
              </div>
            )
          ) : predictions.length === 0 ? (
            <EmptyState
              title="No assessments recorded"
              hint="Score telemetry in the Predictive Intel module to create a record."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Threat assessment history</caption>
                <thead className="text-xs uppercase tracking-wider text-aegis-muted border-b border-white/10">
                  <tr>
                    <th scope="col" className="p-4">Timestamp</th>
                    <th scope="col" className="p-4">Object</th>
                    <th scope="col" className="p-4">Conditions</th>
                    <th scope="col" className="p-4">Distance</th>
                    <th scope="col" className="p-4">Score</th>
                    <th scope="col" className="p-4">Level</th>
                  </tr>
                </thead>
                <tbody>
                  {predictions.map((record, i) => (
                    <tr
                      key={record.id ?? i}
                      className="border-b border-white/5 hover:bg-white/5 transition-colors"
                    >
                      <td className="p-4 text-gray-300 font-mono text-xs whitespace-nowrap">
                        {formatTimestamp(record.created_at)}
                      </td>
                      <td className="p-4 text-white font-medium">{record.telemetry.object}</td>
                      <td className="p-4 text-gray-300 text-xs">
                        {record.telemetry.terrain} / {record.telemetry.weather} /{" "}
                        {record.telemetry.time_of_day}
                      </td>
                      <td className="p-4 text-gray-300 tabular-nums">
                        {record.telemetry.distance_km.toFixed(1)} km
                      </td>
                      <td className="p-4 text-white font-semibold tabular-nums">
                        {record.ml_output.threat_score}
                      </td>
                      <td className="p-4">
                        {/* Severity now uses semantic tokens, so CRITICAL is
                            visibly red rather than inheriting body colour. */}
                        <SeverityBadge level={record.ml_output.threat_level} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination
                total={predictionTotal}
                limit={PAGE_SIZE}
                skip={predictionSkip}
                onChange={setPredictionSkip}
                isLoading={isLoading}
              />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
