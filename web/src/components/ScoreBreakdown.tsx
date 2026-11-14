import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Calculator,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileSearch,
  RotateCcw,
} from "lucide-react";
import { rerunAnalysis } from "../lib/api";
import type {
  ContextItem,
  Contribution,
  DimensionKey,
  DocumentData,
  Evidence,
  Scores,
  SourceProfile,
  StageName,
} from "../lib/contracts";
import { formatPct, formatShortDate, formatSignedContribution } from "../lib/format";
import {
  ALL_STAGES,
  DIMENSION_META,
  FAMILY_LABELS,
  OUTLET_TYPE_LABELS,
  STAGE_LABELS,
  networkLabel,
  signalLabel,
} from "../lib/labels";
import { sliceCodePoints } from "../lib/spans";
import { cn } from "../lib/utils";

export interface ScoreBreakdownProps {
  readonly analysisId: string;
  readonly isFinished: boolean;
  readonly scores: Scores | null | undefined;
  readonly evidence: readonly Evidence[];
  readonly document: DocumentData | null | undefined;
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly open: boolean;
  readonly onToggle: () => void;
  readonly activeEvidenceId: string | null;
  readonly onSelectEvidence: (id: string) => void;
}

function ContributionRows({
  dimension,
  breakdown,
  confidence,
  abstained,
  activeEvidenceId,
  onSelectEvidence,
}: Readonly<{
  dimension: DimensionKey;
  breakdown: readonly Contribution[];
  confidence: number | null | undefined;
  abstained: boolean;
  activeEvidenceId: string | null;
  onSelectEvidence: (id: string) => void;
}>) {
  const maxAbs = Math.max(
    2.5,
    ...breakdown.map((b) => Math.abs(b.contribution)),
  );

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-2 pb-2 border-b border-[var(--border-subtle)]">
        <h3 className="text-sm font-bold text-[var(--fg-primary)] m-0">
          {DIMENSION_META[dimension].shortTitle}
        </h3>
        <span className="font-mono-num text-xs text-[var(--fg-secondary)]">
          {abstained || confidence == null
            ? "Abstained (contributions still shown)"
            : `σ(b + Σ w·v) = ${formatPct(confidence, 1)}`}
        </span>
      </div>

      <div className="space-y-2.5">
        {breakdown.map((row) => {
          const fam = FAMILY_LABELS[row.family];
          const val = row.contribution;
          const pctHalf = Math.min(50, (Math.abs(val) / maxAbs) * 50);

          return (
            <div key={row.family} className="space-y-1">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-medium text-[var(--fg-primary)]" title={fam.hint}>
                  {fam.name}
                </span>
                <div className="flex items-center gap-2">
                  {row.evidence_ids.map((eid) => (
                    <button
                      key={eid}
                      type="button"
                      onClick={() => onSelectEvidence(eid)}
                      className={cn(
                        "px-1.5 py-0.5 rounded font-mono-num text-[11px] border cursor-pointer",
                        activeEvidenceId === eid
                          ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                          : "bg-[var(--accent-soft)] text-[var(--accent)] border-[var(--accent-border)]",
                      )}
                    >
                      [{eid}]
                    </button>
                  ))}
                  <span
                    className={cn(
                      "font-mono-num font-semibold w-14 text-right",
                      val > 0.005
                        ? "text-[var(--accent)]"
                        : val < -0.005
                          ? "text-[var(--teal)]"
                          : "text-[var(--fg-muted)]",
                    )}
                  >
                    {formatSignedContribution(val)}
                  </span>
                </div>
              </div>

              <div className="relative h-2 rounded-full bg-[var(--bg-subtle)] overflow-hidden">
                <div className="absolute top-0 bottom-0 left-1/2 w-px bg-[var(--border-strong)]" />
                {Math.abs(val) >= 0.005 && (
                  <div
                    className={cn(
                      "absolute top-0 bottom-0 rounded-full",
                      val > 0 ? "bg-[var(--accent)]" : "bg-[var(--teal)]",
                    )}
                    style={
                      val > 0
                        ? { left: "50%", width: `${pctHalf}%` }
                        : { right: "50%", width: `${pctHalf}%` }
                    }
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex justify-between gap-3 text-[10px] font-mono-num text-[var(--fg-muted)] pt-1">
        <span className="flex-1">← Points away (agency / corroborated)</span>
        <span className="shrink-0">0.00</span>
        <span className="flex-1 text-right">Points toward signs →</span>
      </div>
    </div>
  );
}

export function ScoreBreakdown({
  analysisId,
  isFinished,
  scores,
  evidence,
  document,
  context,
  sources,
  open,
  onToggle,
  activeEvidenceId,
  onSelectEvidence,
}: Readonly<ScoreBreakdownProps>) {
  const navigate = useNavigate();
  const [rerunStage, setRerunStage] = useState<StageName>("signals_single");
  const [rerunning, setRerunning] = useState<boolean>(false);
  const [rerunError, setRerunError] = useState<string | null>(null);

  const contextMap = new Map(context.map((c) => [c.id, c]));

  async function handleRerun() {
    setRerunError(null);
    setRerunning(true);
    try {
      const created = await rerunAnalysis(analysisId, rerunStage);
      navigate(`/analyses/${created.id}`);
    } catch (err: unknown) {
      setRerunError(err instanceof Error ? err.message : "Could not re-run from selected stage.");
    } finally {
      setRerunning(false);
    }
  }

  return (
    <section
      aria-labelledby="breakdown-toggle"
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] overflow-hidden"
    >
      <button
        id="breakdown-toggle"
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="w-full px-5 py-4 flex items-center justify-between gap-3 text-left hover:bg-[var(--bg-subtle)]/50 transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-2.5">
          <Calculator className="h-4 w-4 text-[var(--accent)] shrink-0" aria-hidden="true" />
          <div>
            <span className="text-sm font-bold text-[var(--fg-primary)]">
              Show how we calculated this
            </span>
            <span className="hidden sm:inline text-xs text-[var(--fg-muted)] ml-2.5">
              Per-family log-odds contributions, all {evidence.length} evidence items, and domain records
            </span>
          </div>
        </div>
        {open ? (
          <ChevronDown className="h-4 w-4 text-[var(--fg-muted)] shrink-0" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-4 w-4 text-[var(--fg-muted)] shrink-0" aria-hidden="true" />
        )}
      </button>

      {open && (
        <div className="px-5 pb-5 pt-2 border-t border-[var(--border-subtle)] space-y-6">
          <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0 max-w-[80ch]">
            Each signal family produces at most one value{" "}
            <code className="font-mono-num">v_f ∈ [−1, 1]</code> from its{" "}
            <strong>strongest signal only</strong> so correlated findings are never double-counted.
            A logistic regression combines those family values:{" "}
            <code className="font-mono-num">confidence = σ(intercept + Σ w_f · v_f)</code>.
            The language model writes the plain-English summary from the evidence below; it never alters the score.
          </p>

          {scores && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <ContributionRows
                dimension="single"
                breakdown={scores.single.breakdown}
                confidence={scores.single.confidence}
                abstained={scores.single.abstained}
                activeEvidenceId={activeEvidenceId}
                onSelectEvidence={onSelectEvidence}
              />
              <ContributionRows
                dimension="coordinated"
                breakdown={scores.coordinated.breakdown}
                confidence={scores.coordinated.confidence}
                abstained={scores.coordinated.abstained}
                activeEvidenceId={activeEvidenceId}
                onSelectEvidence={onSelectEvidence}
              />
            </div>
          )}

          {/* Full Evidence Ledger */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <FileSearch className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
              <h3 className="text-sm font-bold text-[var(--fg-primary)] m-0">
                Complete evidence ledger ({evidence.length})
              </h3>
            </div>

            {evidence.length === 0 ? (
              <p className="text-xs text-[var(--fg-muted)] m-0">
                No signal evidence items were emitted for this content.
              </p>
            ) : (
              <div className="space-y-2.5">
                {evidence.map((item) => {
                  const fam = FAMILY_LABELS[item.family];
                  const isActive = activeEvidenceId === item.id;
                  return (
                    <div
                      key={item.id}
                      id={`evidence-${item.id}`}
                      className={cn(
                        "rounded-lg border p-3.5 space-y-2 transition-colors",
                        isActive
                          ? "border-[var(--accent)] bg-[var(--accent-soft)]/50"
                          : "border-[var(--border-subtle)] bg-[var(--bg-canvas)]",
                      )}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => onSelectEvidence(item.id)}
                            className="font-mono-num font-bold text-[var(--accent)] hover:underline cursor-pointer"
                          >
                            [{item.id}]
                          </button>
                          <span className="px-2 py-0.5 rounded bg-[var(--bg-subtle)] font-medium text-[var(--fg-secondary)]">
                            {fam.name}
                          </span>
                          <span className="text-[var(--fg-muted)]">·</span>
                          <span className="font-medium text-[var(--fg-primary)]">
                            {signalLabel(item.signal)}
                          </span>
                        </div>

                        <span className="font-mono-num text-xs text-[var(--fg-muted)]">
                          raw value: {Number.isInteger(item.value) ? item.value : item.value.toFixed(2)}
                        </span>
                      </div>

                      <p className="text-xs sm:text-sm text-[var(--fg-primary)] m-0 leading-relaxed">
                        {item.detail}
                      </p>

                      <div className="flex flex-wrap gap-2 pt-0.5">
                        {item.source_refs.map((ref, idx) => {
                          if (ref.kind === "document") {
                            const para = document?.paragraphs[ref.span.paragraph] ?? "";
                            const snippet = para
                              ? sliceCodePoints(para, ref.span.start, ref.span.end)
                              : "";
                            return (
                              <button
                                key={`doc-${idx}`}
                                type="button"
                                onClick={() => onSelectEvidence(item.id)}
                                className="inline-flex items-center gap-1.5 max-w-full px-2.5 py-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-xs text-[var(--fg-secondary)] hover:border-[var(--accent)] hover:text-[var(--fg-primary)] cursor-pointer text-left"
                              >
                                <span className="font-mono-num text-[11px] text-[var(--accent)] shrink-0">
                                  ¶{ref.span.paragraph + 1}
                                </span>
                                <span className="truncate max-w-[36ch]">
                                  {snippet ? `“${snippet}”` : `Span [${ref.span.start}..${ref.span.end}]`}
                                </span>
                              </button>
                            );
                          }

                          if (ref.kind === "context") {
                            const ctx = contextMap.get(ref.id);
                            return (
                              <a
                                key={`ctx-${idx}`}
                                href={ctx?.url ?? "#"}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1.5 max-w-full px-2.5 py-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-xs text-[var(--fg-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                              >
                                <span className="font-semibold shrink-0">
                                  {ctx?.outlet ?? ref.id}
                                </span>
                                {ref.quote && (
                                  <span className="truncate max-w-[34ch] text-[var(--fg-muted)]">
                                    “{ref.quote}”
                                  </span>
                                )}
                                <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                              </a>
                            );
                          }

                          return (
                            <a
                              key={`url-${idx}`}
                              href={ref.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-xs text-[var(--accent)] hover:underline font-mono-num"
                            >
                              <span className="truncate max-w-[40ch]">{ref.url}</span>
                              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                            </a>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Outlet Domain Profiles */}
          {sources.length > 0 && (
            <div className="space-y-2.5">
              <h3 className="text-sm font-bold text-[var(--fg-primary)] m-0">
                Outlet &amp; domain profiles ({sources.length})
              </h3>
              <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-b border-[var(--border-subtle)]">
                      <th className="py-2 px-3 font-semibold">Domain</th>
                      <th className="py-2 px-3 font-semibold">Type</th>
                      <th className="py-2 px-3 font-semibold">Country</th>
                      <th className="py-2 px-3 font-semibold">Registered (RDAP)</th>
                      <th className="py-2 px-3 font-semibold">First TLS Cert</th>
                      <th className="py-2 px-3 font-semibold">Documented Network</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-subtle)]">
                    {sources.map((src) => {
                      const typeMeta = src.outlet_type ? OUTLET_TYPE_LABELS[src.outlet_type] : null;
                      return (
                        <tr key={src.domain} className="bg-[var(--bg-surface)]">
                          <td className="py-2 px-3 font-mono-num font-medium text-[var(--fg-primary)]">
                            {src.domain}
                          </td>
                          <td className="py-2 px-3 text-[var(--fg-secondary)]">
                            {typeMeta ? typeMeta.label : "Untyped"}
                          </td>
                          <td className="py-2 px-3 font-mono-num text-[var(--fg-muted)]">
                            {src.country ?? "—"}
                          </td>
                          <td className="py-2 px-3 font-mono-num text-[var(--fg-muted)]">
                            {formatShortDate(src.registered_at) ?? "—"}
                          </td>
                          <td className="py-2 px-3 font-mono-num text-[var(--fg-muted)]">
                            {formatShortDate(src.first_cert_at) ?? "—"}
                          </td>
                          <td className="py-2 px-3">
                            {src.known_network ? (
                              <span className="px-2 py-0.5 rounded bg-[var(--caution-soft)] border border-[var(--caution-border)] text-[var(--caution)] font-semibold">
                                {networkLabel(src.known_network)}
                              </span>
                            ) : (
                              <span className="text-[var(--fg-muted)]">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Stage re-run utility */}
          {isFinished && (
            <div className="pt-3 border-t border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-[var(--fg-muted)]">
                Re-run downstream stages on the stored upstream context:
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="sr-only" htmlFor="rerun-stage-select">
                  Stage to re-run from
                </label>
                <select
                  id="rerun-stage-select"
                  value={rerunStage}
                  onChange={(e) => setRerunStage(e.target.value as StageName)}
                  className="h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-canvas)] px-2.5 text-xs text-[var(--fg-primary)]"
                >
                  {ALL_STAGES.map((st) => (
                    <option key={st} value={st}>
                      from {st} ({STAGE_LABELS[st].label})
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={rerunning}
                  onClick={handleRerun}
                  className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] text-xs font-medium text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-50 cursor-pointer"
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{rerunning ? "Queueing…" : "Re-run from stage"}</span>
                </button>
              </div>
              {rerunError && (
                <p role="alert" className="w-full text-xs text-[var(--danger)] m-0">
                  {rerunError}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
