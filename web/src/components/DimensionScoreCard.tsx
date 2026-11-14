import { motion } from "motion/react";
import { ArrowUpRight, HelpCircle, Layers, Sparkles } from "lucide-react";
import type { DimensionKey, Evidence, Family, Score } from "../lib/contracts";
import { describeConfidenceBand } from "../lib/evidence";
import { formatPct, formatSignedContribution } from "../lib/format";
import { DIMENSION_META, FAMILY_LABELS } from "../lib/labels";
import { SPATIAL_SPRING } from "../lib/motion";
import { cn } from "../lib/utils";

export interface DimensionScoreCardProps {
  readonly dimension: DimensionKey;
  readonly score: Score | null | undefined;
  readonly evidence: readonly Evidence[];
  readonly isPreliminaryEstimate: boolean;
  readonly cappedAt85: boolean;
  readonly onInspectCalculation: (dimension: DimensionKey) => void;
}

const SINGLE_FAMILY_MAP: Partial<Record<Family, true>> = {
  techniques: true,
  tone: true,
  claim_support: true,
  fact_checks: true,
  source_profile: true,
};

export function DimensionScoreCard({
  dimension,
  score,
  evidence,
  isPreliminaryEstimate,
  cappedAt85,
  onInspectCalculation,
}: Readonly<DimensionScoreCardProps>) {
  const meta = DIMENSION_META[dimension];
  const dimEvidence = evidence.filter((e) =>
    dimension === "single" ? Boolean(SINGLE_FAMILY_MAP[e.family]) : !SINGLE_FAMILY_MAP[e.family],
  );
  const evidenceCount = dimEvidence.length;

  const strongest =
    score?.breakdown
      .filter((b) => Math.abs(b.contribution) >= 0.01)
      .slice()
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))[0] ?? null;

  const isAbstained = !score || score.abstained || score.confidence == null;
  const confidence = score?.confidence ?? 0;
  const pct = Math.max(0, Math.min(100, confidence * 100));
  const band = !isAbstained ? describeConfidenceBand(confidence, evidenceCount) : null;

  return (
    <section
      aria-labelledby={`dim-${dimension}-heading`}
      className="editorial-card rounded-3xl p-5 sm:p-6 flex flex-col justify-between gap-5 relative overflow-hidden"
    >
      {/* Top Header */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
            {dimension === "single" ? (
              <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
            ) : (
              <Layers className="h-3.5 w-3.5 text-[var(--indigo)]" aria-hidden="true" />
            )}
            <span>{meta.shortTitle}</span>
          </span>

          {isPreliminaryEstimate && !isAbstained && (
            <span
              title="Combiner weights are currently hand-set priors pending benchmark calibration."
              className="px-2 py-0.5 rounded-full bg-[var(--caution-soft)] border border-[var(--caution-border)] text-[10px] font-medium text-[var(--caution)]"
            >
              Prior estimate
            </span>
          )}
        </div>

        <h2
          id={`dim-${dimension}-heading`}
          className="text-sm font-semibold text-[var(--fg-primary)] leading-snug m-0"
        >
          {meta.title}
        </h2>
      </div>

      {/* Main Confidence Readout or Honest Abstention */}
      {isAbstained ? (
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/65 p-4 space-y-1.5 my-auto">
          <div className="flex items-center gap-2 text-base font-bold text-[var(--fg-primary)]">
            <HelpCircle className="h-4 w-4 text-[var(--fg-muted)] shrink-0" aria-hidden="true" />
            <span>Not enough evidence</span>
          </div>
          <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
            {score?.reason ??
              "Too few independent reports or corroborating signals were found to compute a reliable confidence score."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className="flex items-baseline gap-2.5">
              <span className="font-mono-num text-4xl sm:text-[42px] font-bold tracking-tight text-[var(--fg-primary)] leading-none">
                {formatPct(confidence, 0)}
              </span>
              <span className="text-xs font-medium text-[var(--fg-muted)]">confidence</span>
            </div>

            {band && (
              <span
                className={cn(
                  "px-2.5 py-1 rounded-full text-xs font-semibold border",
                  band.tone === "teal"
                    ? "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)]"
                    : band.tone === "accent"
                      ? "bg-[var(--accent-soft)] text-[var(--accent)] border-[var(--accent-border)]"
                      : "bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-[var(--border-subtle)]",
                )}
              >
                {band.badge}
              </span>
            )}
          </div>

          {/* Calibrated Segmented Spectrum Track */}
          <div className="space-y-2">
            <div
              role="meter"
              aria-label={`${meta.shortTitle} confidence`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(pct)}
              className="relative h-3 rounded-full bg-[var(--bg-subtle)] border border-[var(--border-subtle)]"
            >
              {/* Quartile Hairline Ticks */}
              {[25, 50, 75].map((tick) => (
                <span
                  key={tick}
                  aria-hidden="true"
                  style={{ left: `${tick}%` }}
                  className="absolute top-0.5 bottom-0.5 w-px bg-[var(--border-strong)]/70 z-10"
                />
              ))}

              {/* Language Tier 85% Cap Indicator (D2) */}
              {cappedAt85 && (
                <span
                  title="Uncalibrated language tier: confidence capped at 85%"
                  style={{ left: "85%" }}
                  className="absolute -top-1 -bottom-1 w-0.5 bg-[var(--caution)] z-20"
                />
              )}

              {/* Active Fill */}
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={SPATIAL_SPRING}
                className={cn(
                  "h-full rounded-full",
                  confidence < 0.16
                    ? "bg-[var(--teal)]"
                    : dimension === "single"
                      ? "bg-[var(--accent)]"
                      : "bg-[var(--indigo)]",
                )}
              />

              {/* Crisp Thumb Indicator */}
              <motion.span
                initial={{ left: "0%" }}
                animate={{ left: `${pct}%` }}
                transition={SPATIAL_SPRING}
                aria-hidden="true"
                className={cn(
                  "absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-4 w-4 rounded-full bg-[var(--bg-surface)] border-2 shadow-xs z-20",
                  confidence < 0.16
                    ? "border-[var(--teal)]"
                    : dimension === "single"
                      ? "border-[var(--accent)]"
                      : "border-[var(--indigo)]",
                )}
              />
            </div>

            <div className="flex items-center justify-between text-[10px] font-mono-num text-[var(--fg-muted)] select-none">
              <span>0% Baseline</span>
              <span>25%</span>
              <span>50%</span>
              <span>75%</span>
              <span>{cappedAt85 ? "85% Cap" : "100%"}</span>
            </div>
          </div>

          {/* Primary Contributing Family Hint */}
          {strongest ? (
            <div className="text-xs text-[var(--fg-secondary)] flex items-center justify-between gap-2 pt-0.5">
              <span className="truncate">
                Top driver:{" "}
                <strong className="font-semibold text-[var(--fg-primary)]">
                  {FAMILY_LABELS[strongest.family].name}
                </strong>
              </span>
              <span
                className={cn(
                  "font-mono-num font-semibold shrink-0",
                  strongest.contribution > 0 ? "text-[var(--accent)]" : "text-[var(--teal)]",
                )}
              >
                {formatSignedContribution(strongest.contribution)} log-odds
              </span>
            </div>
          ) : (
            <div className="text-xs text-[var(--fg-muted)]">
              Zero manipulation or copy signals fired across checked coverage.
            </div>
          )}
        </div>
      )}

      {/* Footer Action: Progressive Disclosure Trigger */}
      <div className="pt-3 border-t border-[var(--border-subtle)] flex items-center justify-between gap-2 text-xs">
        <span className="text-[var(--fg-muted)] font-mono-num">
          {evidenceCount} {evidenceCount === 1 ? "evidence item" : "evidence items"}
        </span>

        <button
          type="button"
          onClick={() => onInspectCalculation(dimension)}
          className="inline-flex items-center gap-1 font-semibold text-[var(--accent)] hover:underline cursor-pointer"
        >
          <span>How this was computed</span>
          <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}
