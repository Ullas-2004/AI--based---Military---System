"use client";
/**
 * Renders the SHAP attribution behind a threat score.
 *
 * The bars are exact Shapley values from the model, not a narrative written
 * after the fact — they sum to the raw prediction. That distinction is the
 * whole point: the panel shows what the model actually did.
 */
import { Info } from "lucide-react";

import type { Explanation } from "@/lib/types";

export default function ExplanationPanel({ explanation }: { explanation: Explanation }) {
  const { baseline, factors, summary, method, raw_score, was_clamped } = explanation;

  // Scale bars against the largest absolute contribution.
  const maxMagnitude = Math.max(...factors.map((f) => Math.abs(f.contribution)), 1);

  return (
    <section
      className="glass-panel rounded-2xl p-6"
      aria-labelledby="explanation-heading"
    >
      <div className="flex items-start justify-between gap-3 mb-1">
        <h2 id="explanation-heading" className="text-lg font-bold text-white">
          Why this score?
        </h2>
        <span className="text-xs text-aegis-muted shrink-0">
          baseline {baseline.toFixed(1)}
        </span>
      </div>
      <p className="text-sm text-gray-300 mb-6 leading-relaxed">{summary}</p>

      <ul className="space-y-3" aria-label="Feature contributions">
        {factors.map((factor) => {
          const magnitude = Math.abs(factor.contribution);
          const width = (magnitude / maxMagnitude) * 50; // half-width each side
          const raises = factor.contribution > 0;
          return (
            <li key={factor.feature}>
              <div className="flex items-baseline justify-between gap-3 mb-1.5">
                <span className="text-sm text-gray-200 truncate">
                  {factor.label}
                  <span className="text-aegis-muted ml-2 text-xs">
                    {String(factor.value)}
                  </span>
                </span>
                <span
                  className={`text-sm font-semibold tabular-nums shrink-0 ${
                    raises ? "text-aegis-danger" : "text-aegis-success"
                  }`}
                >
                  {factor.contribution > 0 ? "+" : ""}
                  {factor.contribution.toFixed(2)}
                </span>
              </div>
              {/* Diverging bar: centre line is "no effect". */}
              <div className="relative h-2.5 rounded-full bg-white/5 overflow-hidden">
                <span
                  className="absolute top-0 bottom-0 w-px bg-white/25 left-1/2"
                  aria-hidden="true"
                />
                <span
                  className={`absolute top-0 bottom-0 rounded-full ${
                    raises ? "bg-aegis-danger" : "bg-aegis-success"
                  }`}
                  style={
                    raises
                      ? { left: "50%", width: `${width}%` }
                      : { right: "50%", width: `${width}%` }
                  }
                  aria-hidden="true"
                />
              </div>
            </li>
          );
        })}
      </ul>

      <div className="mt-6 pt-4 border-t border-white/10 flex items-start gap-2">
        <Info className="w-3.5 h-3.5 text-aegis-muted mt-0.5 shrink-0" aria-hidden="true" />
        <p className="text-xs text-aegis-muted leading-relaxed">
          {method}. Contributions sum exactly to the raw model output
          ({raw_score.toFixed(2)})
          {was_clamped && ", which was then clamped to the 0-99 reporting band"}.
          Red raises the threat score, green lowers it.
        </p>
      </div>
    </section>
  );
}
