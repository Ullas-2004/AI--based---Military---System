"use client";
/**
 * "What would have to be different?" — counterfactual explanations.
 *
 * SHAP says what drove this score. This answers the question an analyst asks
 * next. Every candidate is re-scored through the real model, so each line is a
 * verified outcome rather than an estimate.
 */
import { ArrowRight, ShieldCheck } from "lucide-react";

import type { Counterfactual, ThreatLevel } from "@/lib/types";
import { SeverityBadge } from "./ui";

export default function CounterfactualPanel({
  counterfactuals, isRobust, currentLevel,
}: {
  counterfactuals: Counterfactual[];
  isRobust: boolean;
  currentLevel: ThreatLevel;
}) {
  return (
    <section className="glass-panel rounded-2xl p-6" aria-labelledby="cf-heading">
      <h2 id="cf-heading" className="text-lg font-bold text-white mb-1">
        What would change this?
      </h2>
      <p className="text-sm text-gray-400 mb-5">
        The smallest single change that would move this out of{" "}
        <span className="font-semibold text-gray-200">{currentLevel}</span>.
      </p>

      {isRobust ? (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-aegis-success/10 border border-aegis-success/30">
          <ShieldCheck className="w-5 h-5 text-aegis-success mt-0.5 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold text-aegis-success">Robust assessment</p>
            <p className="text-xs text-gray-300 mt-1 leading-relaxed">
              No single change to any one feature would move this out of{" "}
              {currentLevel}. The classification does not hinge on one variable.
            </p>
          </div>
        </div>
      ) : (
        <ul className="space-y-3">
          {counterfactuals.map((cf) => (
            <li
              key={cf.field}
              className="p-3.5 rounded-xl bg-white/5 border border-white/10"
            >
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-aegis-muted">{cf.label}</span>
                <span className="text-gray-300 font-medium">{String(cf.from)}</span>
                <ArrowRight className="w-3.5 h-3.5 text-aegis-accent" aria-hidden="true" />
                <span className="text-white font-semibold">{String(cf.to)}</span>
              </div>
              <div className="flex items-center gap-2.5 mt-2.5">
                <SeverityBadge level={cf.new_level} />
                <span className="text-sm text-gray-300 tabular-nums">
                  {cf.new_score}
                </span>
                <span
                  className={`text-xs font-semibold tabular-nums ${
                    cf.delta < 0 ? "text-aegis-success" : "text-aegis-danger"
                  }`}
                >
                  {cf.delta > 0 ? "+" : ""}{cf.delta}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-aegis-muted mt-5 pt-4 border-t border-white/10 leading-relaxed">
        Each alternative is re-scored through the model, so these are verified
        outcomes rather than estimates.
      </p>
    </section>
  );
}
