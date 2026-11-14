import { HelpCircle } from "lucide-react";
import type { DimensionKey, Evidence, Score } from "../lib/contracts";
import { formatPct, formatSignedContribution } from "../lib/format";
import { DIMENSION_META, FAMILY_LABELS } from "../lib/labels";

export interface DimensionScoreCardProps {
  readonly dimension: DimensionKey;
  readonly score: Score | null | undefined;
  readonly evidence: readonly Evidence[];
  readonly isPreliminaryEstimate: boolean;
  readonly isPending: boolean;
  readonly onOpenBreakdown: () => void;
}

export function DimensionScoreCard({
  dimension,
  score,
  evidence,
  isPreliminaryEstimate,
  isPending,
  onOpenBreakdown,
}: Readonly<DimensionScoreCardProps>) {
  const meta = DIMENSION_META[dimension];
  const familySet = new Set(meta.families);
  const dimEvidence = evidence.filter((e) => familySet.has(e.family));
  const evidenceCount = dimEvidence.length;

  const strongest =
    score?.breakdown
      .filter((b) => Math.abs(b.contribution) >= 0.01)
      .slice()
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))[0] ?? null;

  return (
    <section
      aria-labelledby={`dim-${dimension}-heading`}
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 flex flex-col justify-between gap-4"
    >
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-[var(--fg-muted)]">{meta.shortTitle}</span>
          <span className="font-mono-num text-xs text-[var(--fg-secondary)] bg-[var(--bg-subtle)] px-2 py-0.5 rounded-md shrink-0 whitespace-nowrap">
            {evidenceCount} {evidenceCount === 1 ? "piece" : "pieces"} of evidence
          </span>
        </div>
        <h2
          id={`dim-${dimension}-heading`}
          className="text-base font-bold tracking-tight text-[var(--fg-primary)] m-0"
        >
          {meta.title}
        </h2>
      </div>

      {isPending && !score ? (
        <div className="space-y-2.5 py-2" aria-busy="true">
          <div className="h-7 w-40 rounded bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-2.5 w-full rounded-full bg-[var(--bg-subtle)] animate-pulse" />
          <p className="text-xs text-[var(--fg-muted)] m-0">Waiting for signal and scoring stages…</p>
        </div>
      ) : !score || score.abstained || score.confidence == null ? (
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/70 p-3.5 space-y-1.5">
          <div className="flex items-center gap-2 text-sm font-bold text-[var(--fg-primary)]">
            <HelpCircle className="h-4 w-4 text-[var(--fg-muted)] shrink-0" aria-hidden="true" />
            <span>Not enough evidence</span>
          </div>
          <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
            {score?.reason ??
              "The pipeline abstained rather than guessing because insufficient independent context was available."}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-baseline gap-2.5 flex-wrap">
            <span className="font-mono-num text-3xl font-bold tracking-tight text-[var(--fg-primary)]">
              {formatPct(score.confidence, 0)}
            </span>
            <span className="text-xs font-medium text-[var(--fg-secondary)]">
              {isPreliminaryEstimate ? "confidence (uncalibrated prior estimate)" : "confidence"}
            </span>
          </div>

          <div
            role="meter"
            aria-label={`${meta.title} confidence`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(score.confidence * 100)}
            className="h-2.5 w-full rounded-full bg-[var(--bg-subtle)] overflow-hidden border border-[var(--border-subtle)]"
          >
            <div
              className="h-full rounded-full bg-[var(--accent)] transition-all duration-300"
              style={{ width: `${Math.max(2, Math.min(100, score.confidence * 100))}%` }}
            />
          </div>

          {strongest ? (
            <p className="text-xs text-[var(--fg-secondary)] m-0 flex items-center justify-between gap-2">
              <span>
                Largest factor:{" "}
                <strong className="font-semibold text-[var(--fg-primary)]">
                  {FAMILY_LABELS[strongest.family].name}
                </strong>
              </span>
              <span className="font-mono-num text-xs text-[var(--fg-muted)]">
                {formatSignedContribution(strongest.contribution)} log-odds
              </span>
            </p>
          ) : (
            <p className="text-xs text-[var(--fg-muted)] m-0">
              Baseline intercept only — no signal families fired on this dimension.
            </p>
          )}
        </div>
      )}

      <div className="pt-2 border-t border-[var(--border-subtle)] flex items-center justify-between gap-2 text-xs">
        <span className="text-[var(--fg-muted)] line-clamp-1">{meta.subtitle}</span>
        <button
          type="button"
          onClick={onOpenBreakdown}
          className="text-[var(--accent)] font-semibold hover:underline shrink-0 cursor-pointer"
        >
          Weights &amp; math
        </button>
      </div>
    </section>
  );
}
