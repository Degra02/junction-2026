import { motion } from "motion/react";
import type { DimensionKey, Evidence, Family, Score } from "../lib/contracts";
import { formatSignedContribution } from "../lib/format";
import { DIMENSION_META, FAMILY_LABELS } from "../lib/labels";
import { SPATIAL_SPRING } from "../lib/motion";
import { buttonClass, tagClass } from "../lib/ui";
import { AnimatedNumber } from "./ui/AnimatedNumber";

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

const formatWholePct = (value: number): string => `${Math.round(value)}%`;

export function DimensionScoreCard({
  dimension,
  score,
  evidence,
  isPreliminaryEstimate,
  cappedAt85,
  onInspectCalculation,
}: Readonly<DimensionScoreCardProps>) {
  const meta = DIMENSION_META[dimension];
  const evidenceCount = evidence.filter((e) =>
    dimension === "single" ? Boolean(SINGLE_FAMILY_MAP[e.family]) : !SINGLE_FAMILY_MAP[e.family],
  ).length;

  const strongest =
    score?.breakdown
      .filter((b) => Math.abs(b.contribution) >= 0.01)
      .slice()
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))[0] ?? null;

  const isAbstained = !score || score.abstained || score.confidence == null;
  const confidence = score?.confidence ?? 0;
  const pct = Math.max(0, Math.min(100, confidence * 100));
  const headingId = `dim-${dimension}-heading`;

  return (
    <section
      aria-labelledby={headingId}
      data-spotlight
      className="editorial-card rounded-xl p-5 flex flex-col gap-4"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 id={headingId} className="text-sm font-medium text-[var(--fg-primary)] leading-snug">
          {meta.title}
        </h2>
        {isPreliminaryEstimate && !isAbstained && (
          <span title="Weights are hand-set priors, not yet calibrated" className={tagClass("caution")}>
            Prior estimate
          </span>
        )}
      </div>

      {isAbstained ? (
        <div className="space-y-1.5 my-auto">
          <p className="display text-2xl text-[var(--fg-primary)]">Not enough evidence</p>
          <p className="text-[13px] text-[var(--fg-secondary)]">
            {score?.reason ?? "Too few independent reports."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <AnimatedNumber
            value={pct}
            format={formatWholePct}
            className="block text-[44px] leading-none font-semibold tracking-tight tabular text-[var(--fg-primary)]"
          />

          <div
            role="meter"
            aria-label={`${meta.shortTitle} confidence`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(pct)}
            className="relative h-1.5 rounded-full bg-[var(--bg-subtle)]"
          >
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={SPATIAL_SPRING}
              className="h-full rounded-full"
              style={{ background: dimension === "single" ? "var(--accent)" : "var(--indigo)" }}
            />
            {cappedAt85 && (
              <span
                title="Capped at 85%: language not calibrated"
                style={{ left: "85%" }}
                className="absolute -top-1 -bottom-1 w-px bg-[var(--caution)]"
              />
            )}
          </div>

          {strongest ? (
            <p className="flex items-baseline justify-between gap-2 text-[13px] text-[var(--fg-secondary)]">
              <span className="truncate">{FAMILY_LABELS[strongest.family].name}</span>
              <span className="font-mono-num text-xs text-[var(--fg-primary)] shrink-0">
                {formatSignedContribution(strongest.contribution)}
              </span>
            </p>
          ) : (
            <p className="text-[13px] text-[var(--fg-muted)]">No signals found</p>
          )}
        </div>
      )}

      <div className="mt-auto pt-3 border-t border-[var(--border-subtle)] flex items-center justify-between gap-2">
        <span className="font-mono-num text-xs text-[var(--fg-muted)]">
          {evidenceCount} {evidenceCount === 1 ? "signal" : "signals"}
        </span>
        <button
          type="button"
          onClick={() => onInspectCalculation(dimension)}
          className={buttonClass("ghost", "sm", "-mr-2.5")}
        >
          How it was scored →
        </button>
      </div>
    </section>
  );
}
