import { motion } from "motion/react";
import { CheckCircle2, Network } from "lucide-react";
import type { DimensionKey, Evidence, Family, Scores } from "../lib/contracts";
import { DIMENSION_META, FAMILY_LABELS, TECHNIQUE_GUIDE, signalLabel } from "../lib/labels";
import { SPATIAL_SPRING } from "../lib/motion";
import { buttonClass, tagClass } from "../lib/ui";
import { AnimatedNumber } from "./ui/AnimatedNumber";
import { Hint, InfoHint } from "./ui/Hint";

export interface DimensionScoreCardProps {
  readonly scores: Scores | null | undefined;
  readonly evidence: readonly Evidence[];
  readonly isPreliminaryEstimate: boolean;
  readonly cappedAt85: boolean;
  readonly onInspectCalculation: (dimension: DimensionKey) => void;
  readonly onInspectEvidence: (evidenceId: string) => void;
}

const SINGLE_FAMILY_MAP: Partial<Record<Family, true>> = {
  techniques: true,
  rhetoric: true,
  tone: true,
  claim_support: true,
  fact_checks: true,
  source_profile: true,
};

const REASSURING_SIGNALS = new Set([
  "rated_true",
  "outlet_wire_service",
  "outlet_national",
  "outlet_local",
  "outlet_fact_checker",
  "outlet_satire",
]);

const formatWholePct = (value: number): string => `${Math.round(value)}%`;

function isCautionEvidence(ev: Evidence): boolean {
  if (REASSURING_SIGNALS.has(ev.signal)) return false;
  if (ev.family === "source_profile" && ev.signal === "domain_age_days") {
    return ev.value < 365;
  }
  if (ev.family === "tone") {
    return ev.value > 0;
  }
  return true;
}

function chipLabel(ev: Evidence): string {
  const guide = TECHNIQUE_GUIDE[ev.signal];
  if (guide) return guide.name;
  if (ev.family === "source_profile" && ev.signal === "domain_age_days") {
    const days = Math.max(0, Math.round(ev.value));
    if (days < 365) return `Domain registered ${days}d before`;
    const years = Math.floor(days / 365);
    return `Domain registered ${years}y+`;
  }
  return signalLabel(ev.signal);
}

/** Deduplicate overlapping XLM-R (`techniques`) and LLM (`rhetoric`) detections of the same category. */
function dedupeSignals(items: readonly Evidence[]): Evidence[] {
  const bySignal = new Map<string, Evidence>();
  for (const ev of items) {
    const prev = bySignal.get(ev.signal);
    if (!prev || (ev.family === "rhetoric" && prev.family === "techniques") || ev.value > prev.value) {
      bySignal.set(ev.signal, ev);
    }
  }
  return Array.from(bySignal.values());
}

export function DimensionScoreCard({
  scores,
  evidence,
  isPreliminaryEstimate,
  cappedAt85,
  onInspectCalculation,
  onInspectEvidence,
}: Readonly<DimensionScoreCardProps>) {
  const single = scores?.single;
  const coord = scores?.coordinated;

  const singleEvidence = evidence.filter((e) => Boolean(SINGLE_FAMILY_MAP[e.family]));
  const coordEvidence = evidence.filter((e) => !SINGLE_FAMILY_MAP[e.family]);
  const hasCoordSignals = coordEvidence.length > 0;

  const singleScored = Boolean(single && !single.abstained && single.confidence != null);
  const coordScored = Boolean(coord && !coord.abstained && coord.confidence != null);

  // Noisy-OR across non-abstained dimensions, EXCEPT when `single` abstained and `coordinated`
  // found 0 signals (avoid showing a misleading ~5% from an empty coordination baseline).
  const showCombinedPct = singleScored || (coordScored && hasCoordSignals);
  const pSingle = singleScored ? (single?.confidence ?? 0) : 0;
  const pCoord = coordScored && (hasCoordSignals || singleScored) ? (coord?.confidence ?? 0) : 0;
  const rawCombined = 1 - (1 - pSingle) * (1 - pCoord);
  const combined = cappedAt85 ? Math.min(rawCombined, 0.85) : rawCombined;
  const pct = Math.max(0, Math.min(100, combined * 100));

  const activeBreakdowns = [
    ...(singleScored ? (single?.breakdown ?? []) : []),
    ...(coordScored && (hasCoordSignals || singleScored) ? (coord?.breakdown ?? []) : []),
  ];
  const strongest =
    activeBreakdowns
      .filter((b) => Math.abs(b.contribution) >= 0.01)
      .slice()
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))[0] ?? null;

  const cautionSingle = dedupeSignals(singleEvidence.filter(isCautionEvidence));
  const reassuringSingle = dedupeSignals(singleEvidence.filter((e) => !isCautionEvidence(e)));
  const isSatireAbstain =
    !singleScored &&
    (/satire|humour|humor/i.test(single?.reason ?? "") ||
      singleEvidence.some((e) => e.signal === "outlet_satire"));

  const primaryInspectDim: DimensionKey =
    !singleScored && hasCoordSignals ? "coordinated" : "single";
  const meterDrivenByCoord = !singleScored && hasCoordSignals;

  return (
    <section
      aria-labelledby="combined-signal-heading"
      data-spotlight
      className="editorial-card rounded-xl p-5 sm:p-6 flex flex-col gap-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h2
            id="combined-signal-heading"
            className="text-sm font-medium text-[var(--fg-primary)] leading-snug"
          >
            {showCombinedPct
              ? "Combined propaganda-signal confidence"
              : "Detected content & source signals"}
          </h2>
          <InfoHint
            label="How content and coordination signals are combined"
            content={
              <>
                Combines calibrated content-level ({DIMENSION_META.single.shortTitle.toLowerCase()})
                {" "}and {DIMENSION_META.coordinated.shortTitle.toLowerCase()} probabilities via
                noisy-OR: 1 − (1 − p<sub>content</sub>)(1 − p<sub>network</sub>). When cross-outlet
                coverage is too sparse for a percentage and no network traces exist, detected
                persuasion and source signals are shown directly. Never a binary verdict.
              </>
            }
          />
        </div>
        {isPreliminaryEstimate && showCombinedPct && (
          <Hint content="The weights behind this number are not yet fitted on labelled data.">
            <span tabIndex={0} className={tagClass("caution", undefined, "cursor-help")}>
              Preliminary
            </span>
          </Hint>
        )}
      </div>

      {showCombinedPct ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <AnimatedNumber
              value={pct}
              format={formatWholePct}
              className="block text-[46px] leading-none font-semibold tracking-tight tabular text-[var(--fg-primary)]"
            />
            <span className="font-mono-num text-xs text-[var(--fg-muted)]">
              {singleScored && coordScored
                ? `Content ${formatWholePct(pSingle * 100)} · Network ${formatWholePct(pCoord * 100)}`
                : singleScored
                  ? `Content ${formatWholePct(pSingle * 100)} · Network unrated`
                  : `Network ${formatWholePct(pCoord * 100)} · Content unrated`}
            </span>
          </div>

          <div
            role="meter"
            aria-label="Combined propaganda-signal confidence"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(pct)}
            className="relative h-2 rounded-full bg-[var(--bg-subtle)]"
          >
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={SPATIAL_SPRING}
              className="h-full rounded-full"
              style={{ background: meterDrivenByCoord ? "var(--indigo)" : "var(--accent)" }}
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
            <p className="text-[13px] text-[var(--fg-secondary)]">
              {strongest.contribution > 0 ? "Raised most by " : "Lowered most by "}
              <span className="font-medium text-[var(--fg-primary)]">
                {FAMILY_LABELS[strongest.family].name.toLowerCase()}
              </span>
            </p>
          ) : (
            <p className="text-[13px] text-[var(--fg-muted)]">
              No manipulation signals found in the checked coverage
            </p>
          )}
        </div>
      ) : isSatireAbstain ? (
        <div className="space-y-2">
          <p className="display text-2xl sm:text-[28px] leading-snug text-[var(--fg-primary)]">
            Satire or humour — not scored as factual news
          </p>
          <p className="text-[13px] text-[var(--fg-secondary)]">
            {single?.reason ?? "This item appears to be satire or parody rather than factual reporting."}
          </p>
        </div>
      ) : cautionSingle.length > 0 ? (
        <div className="space-y-3">
          <p className="display text-2xl sm:text-[28px] leading-snug text-[var(--fg-primary)]">
            {cautionSingle.every((e) => e.family === "techniques" || e.family === "rhetoric")
              ? `${cautionSingle.length} persuasion ${cautionSingle.length === 1 ? "technique" : "techniques"} detected in the content`
              : `${cautionSingle.length} content & source ${cautionSingle.length === 1 ? "signal" : "signals"} detected`}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            {cautionSingle.map((ev) => (
              <button
                key={ev.id}
                type="button"
                onClick={() => onInspectEvidence(ev.id)}
                className={tagClass("caution", undefined, "cursor-pointer hover:opacity-85 transition-opacity")}
              >
                {chipLabel(ev)} →
              </button>
            ))}
            {reassuringSingle.map((ev) => (
              <button
                key={ev.id}
                type="button"
                onClick={() => onInspectEvidence(ev.id)}
                className={tagClass("neutral", undefined, "cursor-pointer hover:opacity-85 transition-opacity")}
              >
                {chipLabel(ev)}
              </button>
            ))}
          </div>
          <p className="text-xs text-[var(--fg-muted)]">
            No calibrated percentage shown:{" "}
            {single?.reason ?? "fewer than 3 independent reports on the same event were found to compare against."}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          <p className="display text-2xl sm:text-[28px] leading-snug text-[var(--fg-primary)]">
            No persuasion techniques detected in the content
          </p>
          {reassuringSingle.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {reassuringSingle.map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => onInspectEvidence(ev.id)}
                  className={tagClass("teal", undefined, "cursor-pointer hover:opacity-85 transition-opacity")}
                >
                  {chipLabel(ev)}
                </button>
              ))}
            </div>
          )}
          <p className="text-xs text-[var(--fg-muted)]">
            Cross-outlet claim score abstained:{" "}
            {single?.reason ?? "too few independent reports on the same event were found to compare."}
          </p>
        </div>
      )}

      {hasCoordSignals ? (
        <div className="pt-3.5 border-t border-[var(--border-subtle)] grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => onInspectCalculation("single")}
            className="text-left rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/45 hover:bg-[var(--bg-hover)] transition-colors px-3.5 py-2.5 space-y-1 cursor-pointer"
          >
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="font-medium text-[var(--fg-primary)]">
                {DIMENSION_META.single.shortTitle}
              </span>
              <span className="font-mono-num text-[var(--fg-secondary)]">
                {singleScored
                  ? formatWholePct(pSingle * 100)
                  : `${singleEvidence.length} ${singleEvidence.length === 1 ? "signal" : "signals"}`}
              </span>
            </div>
            <p className="text-[11px] text-[var(--fg-muted)] truncate">
              {singleScored
                ? `${singleEvidence.length} content/source ${singleEvidence.length === 1 ? "signal" : "signals"}`
                : (single?.reason ?? "Too few related reports to cross-check")}
            </p>
          </button>

          <button
            type="button"
            onClick={() => onInspectCalculation("coordinated")}
            className="text-left rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/45 hover:bg-[var(--bg-hover)] transition-colors px-3.5 py-2.5 space-y-1 cursor-pointer"
          >
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="inline-flex items-center gap-1.5 font-medium text-[var(--fg-primary)]">
                <Network className="h-3.5 w-3.5 text-[var(--indigo)]" aria-hidden="true" />
                {DIMENSION_META.coordinated.shortTitle}
              </span>
              <span className="font-mono-num font-medium text-[var(--indigo)]">
                {coordScored
                  ? formatWholePct((coord?.confidence ?? 0) * 100)
                  : `${coordEvidence.length} ${coordEvidence.length === 1 ? "signal" : "signals"}`}
              </span>
            </div>
            <p className="text-[11px] text-[var(--fg-secondary)] truncate">
              {coordEvidence.map((e) => chipLabel(e)).join(" · ")}
            </p>
          </button>
        </div>
      ) : (
        <div className="pt-3 border-t border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs text-[var(--fg-muted)]">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-[var(--teal)]" aria-hidden="true" />
            <span>No cross-site copy or tracker network detected</span>
            {singleEvidence.length > 0 && (
              <span className="font-mono-num">
                · {singleEvidence.length} content {singleEvidence.length === 1 ? "signal" : "signals"}
              </span>
            )}
          </span>
          <button
            type="button"
            onClick={() => onInspectCalculation(primaryInspectDim)}
            className={buttonClass("ghost", "sm", "-mr-2.5")}
          >
            How it was scored →
          </button>
        </div>
      )}
    </section>
  );
}
