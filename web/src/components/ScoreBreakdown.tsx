import { useState } from "react";
import { Filter } from "lucide-react";
import type {
  ContextItem,
  DimensionKey,
  DocumentData,
  Evidence,
  Family,
  Scores,
  SourceProfile,
} from "../lib/contracts";
import { computeWaterfallSteps } from "../lib/evidence";
import { formatPct, formatSignedContribution } from "../lib/format";
import { DIMENSION_META, FAMILY_LABELS, signalLabel } from "../lib/labels";
import { cn } from "../lib/utils";
import { CitationChip } from "./CitationChip";

export interface ScoreBreakdownProps {
  readonly scores: Scores | null | undefined;
  readonly evidence: readonly Evidence[];
  readonly document: DocumentData | null | undefined;
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly cappedAt85: boolean;
  readonly activeDimension: DimensionKey;
  readonly onChangeDimension: (dim: DimensionKey) => void;
  readonly activeEvidenceId: string | null;
  readonly onInspectEvidence: (id: string) => void;
}

const SINGLE_FAMILY_LOOKUP: Partial<Record<Family, true>> = {
  techniques: true,
  tone: true,
  claim_support: true,
  fact_checks: true,
  source_profile: true,
};

/**
 * Custom SVG SHAP-style Sigmoid Waterfall Plot:
 * Maps additive log-odds `b + Σ w_f·v_f` onto probability space `[0%, 100%]`
 * so readers see how each family moves confidence from the prior baseline to the final score.
 */
function SigmoidWaterfallSvg({
  dimension,
  scores,
  cappedAt85,
  selectedFamily,
  onSelectFamily,
}: Readonly<{
  dimension: DimensionKey;
  scores: Scores;
  cappedAt85: boolean;
  selectedFamily: Family | null;
  onSelectFamily: (family: Family | null) => void;
}>) {
  const score = scores[dimension];
  const wf = computeWaterfallSteps(dimension, score, cappedAt85);

  const leftPad = 176;
  const rightPad = 112;
  const trackW = 412;
  const width = leftPad + trackW + rightPad;
  const rowH = 34;
  const topPad = 32;
  const totalRows = wf.steps.length + 2; // Baseline + N families + Final
  const height = topPad + totalRows * rowH + 28;

  const xOf = (p: number) => leftPad + Math.max(0, Math.min(1, p)) * trackW;

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full min-w-[560px] h-auto select-none"
        role="img"
        aria-label={`Confidence calculation waterfall chart for ${DIMENSION_META[dimension].shortTitle}`}
      >
        {/* Probability Grid Ticks (0%, 25%, 50%, 75%, 100%) */}
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const x = xOf(tick);
          return (
            <g key={tick}>
              <line
                x1={x}
                y1={topPad - 6}
                x2={x}
                y2={topPad + totalRows * rowH}
                stroke="var(--border-subtle)"
                strokeDasharray={tick === 0 || tick === 1 ? undefined : "3 3"}
                strokeWidth="1"
              />
              <text
                x={x}
                y={topPad - 12}
                textAnchor="middle"
                fontSize="10"
                fontFamily="var(--font-mono)"
                fill="var(--fg-muted)"
              >
                {Math.round(tick * 100)}%
              </text>
            </g>
          );
        })}

        {/* Row 0: Baseline Prior σ(b) */}
        {(() => {
          const y = topPad + 6;
          const baseX = xOf(wf.baselineProb);
          return (
            <g>
              <text
                x={leftPad - 12}
                y={y + 13}
                textAnchor="end"
                fontSize="12"
                fontWeight="600"
                fill="var(--fg-secondary)"
              >
                Prior baseline σ(b)
              </text>
              <rect
                x={xOf(0)}
                y={y + 3}
                width={Math.max(3, baseX - xOf(0))}
                height={14}
                rx={4}
                fill="var(--border-strong)"
                opacity="0.65"
              />
              <line
                x1={baseX}
                y1={y + 17}
                x2={baseX}
                y2={y + rowH + 3}
                stroke="var(--border-strong)"
                strokeDasharray="2 2"
              />
              <text
                x={leftPad + trackW + 10}
                y={y + 14}
                fontSize="11"
                fontFamily="var(--font-mono)"
                fill="var(--fg-muted)"
              >
                {formatPct(wf.baselineProb, 0)} (b={wf.intercept.toFixed(1)})
              </text>
            </g>
          );
        })()}

        {/* Family Step Rows */}
        {wf.steps.map((step, idx) => {
          const y = topPad + (idx + 1) * rowH + 6;
          const xStart = xOf(step.probBefore);
          const xEnd = xOf(step.probAfter);
          const barX = Math.min(xStart, xEnd);
          const barW = Math.max(3, Math.abs(xEnd - xStart));
          const isPositive = step.logOddsDelta > 0.005;
          const isNegative = step.logOddsDelta < -0.005;
          const isSelected = selectedFamily !== null && selectedFamily === step.family;

          const fill = isPositive
            ? dimension === "single"
              ? "var(--accent)"
              : "var(--indigo)"
            : isNegative
              ? "var(--teal)"
              : "var(--border-strong)";

          return (
            <g
              key={step.key}
              onClick={() =>
                step.family &&
                onSelectFamily(selectedFamily === step.family ? null : step.family)
              }
              style={{ cursor: step.family ? "pointer" : "default" }}
            >
              {/* Subtle Interactive Row Hover/Selection Highlight */}
              <rect
                x={4}
                y={y - 4}
                width={width - 8}
                height={rowH - 4}
                rx={8}
                fill={isSelected ? "var(--accent-soft)" : "transparent"}
              />

              <text
                x={leftPad - 12}
                y={y + 13}
                textAnchor="end"
                fontSize="12"
                fontWeight={isSelected || Math.abs(step.logOddsDelta) > 0.01 ? "600" : "400"}
                fill={
                  isSelected
                    ? "var(--accent)"
                    : Math.abs(step.logOddsDelta) > 0.01
                      ? "var(--fg-primary)"
                      : "var(--fg-muted)"
                }
              >
                {step.label}
              </text>

              <rect
                x={barX}
                y={y + 3}
                width={barW}
                height={14}
                rx={4}
                fill={fill}
                opacity={Math.abs(step.logOddsDelta) < 0.005 ? 0.35 : 0.92}
              />

              {/* Connector to next row */}
              <line
                x1={xEnd}
                y1={y + 17}
                x2={xEnd}
                y2={y + rowH + 3}
                stroke="var(--border-strong)"
                strokeDasharray="2 2"
              />

              {/* Signed Log-Odds Label */}
              <text
                x={leftPad + trackW + 10}
                y={y + 14}
                fontSize="11"
                fontWeight={Math.abs(step.logOddsDelta) > 0.01 ? "600" : "400"}
                fontFamily="var(--font-mono)"
                fill={
                  isPositive
                    ? "var(--accent)"
                    : isNegative
                      ? "var(--teal)"
                      : "var(--fg-muted)"
                }
              >
                {formatSignedContribution(step.logOddsDelta)} → {formatPct(step.probAfter, 0)}
              </text>
            </g>
          );
        })}

        {/* Final Combined Confidence Row */}
        {(() => {
          const y = topPad + (wf.steps.length + 1) * rowH + 8;
          const finalX = xOf(wf.finalProb);
          return (
            <g>
              <line
                x1={8}
                y1={y - 6}
                x2={width - 8}
                y2={y - 6}
                stroke="var(--border-subtle)"
              />
              <text
                x={leftPad - 12}
                y={y + 13}
                textAnchor="end"
                fontSize="12"
                fontWeight="700"
                fill="var(--fg-primary)"
              >
                {score.abstained ? "Combined (abstained)" : "Final confidence"}
              </text>
              <rect
                x={xOf(0)}
                y={y + 3}
                width={Math.max(4, finalX - xOf(0))}
                height={14}
                rx={4}
                fill={score.abstained ? "var(--fg-muted)" : "var(--accent)"}
                opacity={score.abstained ? 0.45 : 1}
              />
              <circle
                cx={finalX}
                cy={y + 10}
                r={5}
                fill="var(--bg-surface)"
                stroke={score.abstained ? "var(--fg-muted)" : "var(--accent)"}
                strokeWidth="2.5"
              />
              <text
                x={leftPad + trackW + 10}
                y={y + 14}
                fontSize="12"
                fontWeight="700"
                fontFamily="var(--font-mono)"
                fill="var(--fg-primary)"
              >
                {score.abstained ? "Abstained" : formatPct(wf.finalProb, 1)}
              </text>
            </g>
          );
        })()}
      </svg>
    </div>
  );
}

export function ScoreBreakdown({
  scores,
  evidence,
  document,
  context,
  sources,
  cappedAt85,
  activeDimension,
  onChangeDimension,
  activeEvidenceId,
  onInspectEvidence,
}: Readonly<ScoreBreakdownProps>) {
  const [selectedFamily, setSelectedFamily] = useState<Family | null>(null);

  if (!scores) {
    return (
      <div className="editorial-card rounded-3xl p-6 text-xs text-[var(--fg-muted)]">
        Score breakdown is not available for this run.
      </div>
    );
  }

  const dimEvidence = evidence.filter((ev) => {
    const inDim =
      activeDimension === "single"
        ? Boolean(SINGLE_FAMILY_LOOKUP[ev.family])
        : !SINGLE_FAMILY_LOOKUP[ev.family];
    if (!inDim) return false;
    if (selectedFamily && ev.family !== selectedFamily) return false;
    return true;
  });

  const activeScore = scores[activeDimension];

  return (
    <div className="space-y-5">
      {/* Dimension Switcher + Waterfall Card */}
      <div className="editorial-card rounded-3xl p-5 sm:p-6 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <h3 className="text-base font-bold text-[var(--fg-primary)] m-0">
              Logistic Combiner Waterfall
            </h3>
            <p className="text-xs text-[var(--fg-secondary)] m-0 max-w-[68ch]">
              Only the <strong>strongest signal inside each family</strong> counts so correlated cues are never double-counted. Click any family row to filter its underlying evidence below.
            </p>
          </div>

          {/* Dimension Pill Toggle */}
          <div className="inline-flex items-center p-1 rounded-2xl bg-[var(--bg-subtle)] border border-[var(--border-subtle)]">
            {(["single", "coordinated"] as const).map((dim) => {
              const selected = activeDimension === dim;
              return (
                <button
                  key={dim}
                  type="button"
                  onClick={() => {
                    onChangeDimension(dim);
                    setSelectedFamily(null);
                  }}
                  className={cn(
                    "px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer",
                    selected
                      ? "bg-[var(--bg-surface)] text-[var(--fg-primary)] shadow-xs"
                      : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]",
                  )}
                >
                  {DIMENSION_META[dim].shortTitle}
                </button>
              );
            })}
          </div>
        </div>

        {activeScore.abstained && (
          <div className="rounded-2xl bg-[var(--bg-subtle)]/80 border border-[var(--border-subtle)] px-4 py-3 text-xs text-[var(--fg-secondary)]">
            <strong className="text-[var(--fg-primary)]">Abstained on this dimension: </strong>
            {activeScore.reason ?? "Insufficient context items."} Raw family contributions collected before abstention are still plotted below for transparency.
          </div>
        )}

        <SigmoidWaterfallSvg
          dimension={activeDimension}
          scores={scores}
          cappedAt85={cappedAt85}
          selectedFamily={selectedFamily}
          onSelectFamily={setSelectedFamily}
        />

        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-[var(--border-subtle)] text-[11px] text-[var(--fg-muted)]">
          <span>
            Formula: <code className="font-mono-num">confidence = σ(b + Σ w_f · v_f)</code>
          </span>
          <div className="flex items-center gap-4">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-xs bg-[var(--accent)]" />
              <span>Increases signal score (+w·v)</span>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-xs bg-[var(--teal)]" />
              <span>Corroborated / established agency (−w·v)</span>
            </span>
          </div>
        </div>
      </div>

      {/* Contributing Evidence Cards */}
      <div className="editorial-card rounded-3xl p-5 sm:p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-[var(--fg-primary)] m-0">
            Contributing evidence ({dimEvidence.length})
          </h3>

          {selectedFamily && (
            <button
              type="button"
              onClick={() => setSelectedFamily(null)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--accent-soft)] text-xs font-semibold text-[var(--accent)] cursor-pointer"
            >
              <Filter className="h-3 w-3" aria-hidden="true" />
              <span>Filtered: {FAMILY_LABELS[selectedFamily].name} ×</span>
            </button>
          )}
        </div>

        {dimEvidence.length === 0 ? (
          <p className="text-xs text-[var(--fg-muted)] m-0 py-2">
            No signals fired for {selectedFamily ? FAMILY_LABELS[selectedFamily].name : DIMENSION_META[activeDimension].shortTitle.toLowerCase()} in the retrieved coverage.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {dimEvidence.map((ev) => {
              const isSelected = activeEvidenceId === ev.id;
              return (
                <div
                  key={ev.id}
                  id={`evidence-${ev.id}`}
                  className={cn(
                    "rounded-2xl border p-4 space-y-2.5 transition-colors",
                    isSelected
                      ? "border-[var(--accent)] bg-[var(--accent-soft)]/35"
                      : "border-[var(--border-subtle)] bg-[var(--bg-canvas)]",
                  )}
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-semibold text-[var(--fg-primary)]">
                      {signalLabel(ev.signal)}
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-[var(--bg-subtle)] text-[10px] font-medium text-[var(--fg-muted)]">
                      {FAMILY_LABELS[ev.family].name}
                    </span>
                  </div>

                  <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
                    {ev.detail}
                  </p>

                  <div className="pt-1 flex flex-wrap items-center justify-between gap-2">
                    <CitationChip
                      evidence={ev}
                      document={document}
                      context={context}
                      sources={sources}
                      active={isSelected}
                      onInspect={onInspectEvidence}
                    />

                    <span className="font-mono-num text-[11px] text-[var(--fg-muted)]">
                      raw={ev.value.toFixed(2)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
