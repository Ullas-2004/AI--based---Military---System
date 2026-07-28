"use client";
/** Visualises the 80% prediction interval around a threat score. */
import { AlertTriangle } from "lucide-react";

import type { PredictionInterval } from "@/lib/types";

const CONFIDENCE_COPY: Record<string, { label: string; tone: string }> = {
  high: { label: "High confidence", tone: "text-aegis-success" },
  moderate: { label: "Moderate confidence", tone: "text-aegis-warning" },
  low: { label: "Low confidence", tone: "text-aegis-danger" },
};

// Band boundaries, drawn as ticks so the interval can be read against them.
const BOUNDARIES = [40, 60, 80];

export default function UncertaintyBand({
  interval, score,
}: {
  interval: PredictionInterval;
  score: number;
}) {
  const { lower, upper, width, confidence_level, spans_bands } = interval;
  const confidence = CONFIDENCE_COPY[confidence_level] ?? CONFIDENCE_COPY.moderate;

  const pct = (value: number) => Math.min(100, Math.max(0, value));

  return (
    <div className="border-t border-white/10 pt-5">
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <h3 className="text-sm font-semibold text-white">
          Prediction interval
          <span className="text-aegis-muted font-normal ml-2">80% coverage</span>
        </h3>
        <span className={`text-xs font-semibold ${confidence.tone}`}>
          {confidence.label}
        </span>
      </div>

      <div className="relative h-9">
        {/* 0-99 track */}
        <div className="absolute inset-x-0 top-3.5 h-2 rounded-full bg-white/5" />

        {/* Band boundary ticks */}
        {BOUNDARIES.map((b) => (
          <span
            key={b}
            className="absolute top-2 h-5 w-px bg-white/20"
            style={{ left: `${pct(b)}%` }}
            aria-hidden="true"
          />
        ))}

        {/* The interval itself */}
        <div
          className="absolute top-3.5 h-2 rounded-full bg-aegis-accent/50"
          style={{ left: `${pct(lower)}%`, width: `${pct(upper) - pct(lower)}%` }}
          aria-hidden="true"
        />

        {/* Point estimate */}
        <div
          className="absolute top-1.5 w-1 h-6 rounded-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.6)]"
          style={{ left: `${pct(score)}%` }}
          aria-hidden="true"
        />
      </div>

      <p className="text-xs text-aegis-muted mt-1 tabular-nums">
        Likely range <span className="text-gray-200">{lower} – {upper}</span>
        <span className="mx-2">·</span>width {width}
      </p>

      {/* A band-straddling interval is the single most actionable caveat. */}
      {spans_bands && (
        <p className="mt-3 flex items-start gap-2 text-xs text-aegis-warning">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden="true" />
          This interval crosses a threat-band boundary — the classification is
          borderline and warrants analyst judgement.
        </p>
      )}
    </div>
  );
}
