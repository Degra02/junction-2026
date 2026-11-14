import { useState } from "react";
import { X } from "lucide-react";
import type {
  ContextItem,
  DimensionKey,
  DocumentData,
  Evidence,
  Family,
  Scores,
  SourceProfile,
} from "../lib/contracts";
import { computeWaterfallSteps, resolveEvidenceSources } from "../lib/evidence";
import { formatPct, formatSignedContribution } from "../lib/format";
import { DIMENSION_META, FAMILY_LABELS, signalLabel } from "../lib/labels";
import { SECTION_LABEL, buttonClass, tagClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { Favicon } from "./ui/Favicon";

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

const DIMENSIONS: readonly DimensionKey[] = ["single", "coordinated"];
const ZERO = 0.005;
/** Shared row grid: family | diverging bar | values. */
const ROW_GRID = "grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_7.5rem] items-center gap-x-4";

function DivergingBar({
  delta,
  maxAbs,
  positiveColor,
}: Readonly<{ delta: number; maxAbs: number; positiveColor: string }>) {
  const half = maxAbs > 0 ? (Math.min(Math.abs(delta), maxAbs) / maxAbs) * 50 : 0;
  const positive = delta > ZERO;
  const negative = delta < -ZERO;
  return (
    <span className="relative block h-4" aria-hidden="true">
      <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-[var(--border-subtle)]" />
      <span className="absolute left-1/2 inset-y-0 w-px bg-[var(--border-strong)]" />
      {(positive || negative) && (
        <span
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-sm"
          style={{
            width: `${Math.max(half, 1)}%`,
            left: positive ? "50%" : undefined,
            right: negative ? "50%" : undefined,
            background: positive ? positiveColor : "var(--teal)",
          }}
        />
      )}
    </span>
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
      <div className="editorial-card rounded-xl p-4 sm:p-5 text-[13px] text-[var(--fg-muted)]">
        No score for this run.
      </div>
    );
  }

  const score = scores[activeDimension];
  const wf = computeWaterfallSteps(activeDimension, score, cappedAt85);
  const positiveColor = activeDimension === "single" ? "var(--accent)" : "var(--indigo)";
  const maxAbs = Math.max(0.5, ...wf.steps.map((s) => Math.abs(s.logOddsDelta)));
  const isCapped =
    cappedAt85 && score.confidence != null && Math.abs(score.confidence - 0.85) < 1e-3;

  const ledger = evidence.filter(
    (ev) =>
      FAMILY_LABELS[ev.family].dimension === activeDimension &&
      (selectedFamily === null || ev.family === selectedFamily),
  );

  return (
    <section className="editorial-card rounded-xl p-4 sm:p-5 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-[var(--fg-primary)]">How the score was built</h3>
        <div
          role="tablist"
          aria-label="Dimension"
          className="inline-flex rounded-lg bg-[var(--bg-subtle)] p-0.5"
        >
          {DIMENSIONS.map((dim) => {
            const selected = activeDimension === dim;
            return (
              <button
                key={dim}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => {
                  onChangeDimension(dim);
                  setSelectedFamily(null);
                }}
                className={cn(
                  "h-7 px-3 rounded-md text-xs font-medium transition-colors cursor-pointer",
                  selected
                    ? "bg-[var(--bg-surface)] text-[var(--fg-primary)] shadow-[var(--shadow-editorial)]"
                    : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]",
                )}
              >
                {DIMENSION_META[dim].shortTitle}
              </button>
            );
          })}
        </div>
      </div>

      {score.abstained && (
        <p className="text-[13px] text-[var(--fg-secondary)]">
          <span className="font-medium text-[var(--fg-primary)]">Not enough evidence.</span>{" "}
          {score.reason ?? "Too few comparable reports."}
        </p>
      )}

      {/* Waterfall: log-odds contribution per family on a zero axis */}
      <div aria-label={`Score contributions, ${DIMENSION_META[activeDimension].shortTitle}`}>
        <div className={cn(ROW_GRID, "pb-2 text-[11px] text-[var(--fg-muted)]")}>
          <span>Family</span>
          <span className="flex justify-between font-mono-num">
            <span>lowers</span>
            <span>0</span>
            <span>raises</span>
          </span>
          <span className="text-right">log-odds → conf.</span>
        </div>

        <div className={cn(ROW_GRID, "py-2.5 border-t border-[var(--border-subtle)]")}>
          <div className="min-w-0">
            <div className="text-[13px] font-medium text-[var(--fg-secondary)]">Baseline</div>
            <div className="text-xs text-[var(--fg-muted)] truncate">Before any signal</div>
          </div>
          <DivergingBar delta={0} maxAbs={maxAbs} positiveColor={positiveColor} />
          <div className="text-right font-mono-num text-xs text-[var(--fg-muted)]">
            b={wf.intercept.toFixed(2)} → {formatPct(wf.baselineProb, 0)}
          </div>
        </div>

        {wf.steps.map((step) => {
          const positive = step.logOddsDelta > ZERO;
          const negative = step.logOddsDelta < -ZERO;
          const selected = selectedFamily === step.family;
          return (
            <button
              key={step.key}
              type="button"
              aria-pressed={selected}
              onClick={() => setSelectedFamily(selected ? null : step.family)}
              className={cn(
                ROW_GRID,
                "w-full text-left py-2.5 border-t border-[var(--border-subtle)] cursor-pointer transition-colors hover:bg-[var(--bg-hover)]",
                selected && "bg-[var(--accent-soft)] hover:bg-[var(--accent-soft)]",
              )}
            >
              <span className="block min-w-0">
                <span
                  className={cn(
                    "block text-[13px] truncate",
                    positive || negative
                      ? "font-medium text-[var(--fg-primary)]"
                      : "text-[var(--fg-muted)]",
                  )}
                >
                  {step.label}
                </span>
                <span className="block text-xs text-[var(--fg-muted)] truncate">{step.hint}</span>
              </span>
              <DivergingBar delta={step.logOddsDelta} maxAbs={maxAbs} positiveColor={positiveColor} />
              <span className="block text-right font-mono-num text-xs">
                <span
                  style={{
                    color: positive ? positiveColor : negative ? "var(--teal)" : "var(--fg-muted)",
                  }}
                >
                  {formatSignedContribution(step.logOddsDelta)}
                </span>
                <span className="text-[var(--fg-muted)]"> → {formatPct(step.probAfter, 0)}</span>
              </span>
            </button>
          );
        })}

        <div className={cn(ROW_GRID, "pt-3 mt-1 border-t border-[var(--border-strong)]")}>
          <div className="text-[13px] font-medium text-[var(--fg-primary)]">Confidence</div>
          <div className="font-mono-num text-[11px] text-[var(--fg-muted)]">
            σ(b + Σ w·v)
            {isCapped && <span className={tagClass("caution", { mono: true }, "ml-2")}>capped 85%</span>}
          </div>
          <div className="text-right">
            {score.abstained ? (
              <span className="text-xs text-[var(--fg-muted)]">Not enough evidence</span>
            ) : (
              <span className="text-base font-semibold tracking-tight tabular text-[var(--fg-primary)]">
                {formatPct(wf.finalProb, 1)}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Evidence ledger */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h4 className={SECTION_LABEL}>
            Evidence <span className="font-mono-num">{ledger.length}</span>
          </h4>
          {selectedFamily && (
            <button
              type="button"
              onClick={() => setSelectedFamily(null)}
              className={buttonClass("ghost", "sm")}
            >
              {FAMILY_LABELS[selectedFamily].name}
              <X className="h-3 w-3" aria-hidden="true" />
              <span className="sr-only">Clear filter</span>
            </button>
          )}
        </div>

        {ledger.length === 0 ? (
          <p className="text-[13px] text-[var(--fg-muted)] py-2 border-t border-[var(--border-subtle)]">
            No signals fired.
          </p>
        ) : (
          <ul className="p-0 list-none border-t border-[var(--border-subtle)] divide-y divide-[var(--border-subtle)]">
            {ledger.map((ev) => {
              const isActive = activeEvidenceId === ev.id;
              const refs = resolveEvidenceSources(ev, document, context, sources);
              const first = refs[0];
              return (
                <li key={ev.id} id={`evidence-${ev.id}`}>
                  <button
                    type="button"
                    onClick={() => onInspectEvidence(ev.id)}
                    aria-pressed={isActive}
                    className={cn(
                      "w-full text-left grid grid-cols-[3rem_minmax(0,1fr)] gap-x-3 py-2.5 px-1 cursor-pointer transition-colors hover:bg-[var(--bg-hover)]",
                      isActive && "bg-[var(--accent-soft)] hover:bg-[var(--accent-soft)]",
                    )}
                  >
                    <span className="font-mono-num text-xs text-[var(--fg-muted)] pt-0.5">{ev.id}</span>
                    <span className="min-w-0 space-y-0.5">
                      <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                        <span className="text-[13px] font-medium text-[var(--fg-primary)]">
                          {signalLabel(ev.signal)}
                        </span>
                        <span className="font-mono-num text-[11px] text-[var(--fg-muted)]">
                          v={ev.value.toFixed(2)}
                        </span>
                      </span>
                      <span className="block text-[13px] text-[var(--fg-secondary)]">{ev.detail}</span>
                      {first && (
                        <span className="flex items-center gap-1.5 pt-0.5 text-xs text-[var(--fg-muted)]">
                          <Favicon domain={first.domain} size={14} />
                          <span className="font-mono-num truncate">{first.domain}</span>
                          {refs.length > 1 && (
                            <span className="font-mono-num">+{refs.length - 1}</span>
                          )}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
