import { useMemo, useState } from "react";
import { ExternalLink, Globe, ShieldAlert, ShieldCheck } from "lucide-react";
import type {
  Claim,
  ContextItem,
  Evidence,
  Language,
  SourceProfile,
} from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { formatDateTime, formatDomainAge, formatPct } from "../lib/format";
import {
  ADAPTER_LABELS,
  OUTLET_TYPE_LABELS,
  languageName,
  networkLabel,
  signalLabel,
} from "../lib/labels";
import { cn } from "../lib/utils";

export interface CoverageViewProps {
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly evidence: readonly Evidence[];
  readonly claims: readonly Claim[];
  readonly documentLanguage: Language | null | undefined;
  readonly documentOutlet: string | null | undefined;
  readonly documentPublishedAt: string | null | undefined;
  readonly activeEvidenceId: string | null;
  readonly onSelectAnnotation: (id: string) => void;
}

type CoverageTab = "peers" | "fact_checks" | "domains" | "excluded";

/**
 * Custom SVG 1D Peer Tone Strip + Publication Timeline / Similarity Scatter Plot.
 */
function PeerComparisonPlots({
  storyItems,
  toneZ,
  documentPublishedAt,
  documentOutlet,
  sourceMap,
}: Readonly<{
  storyItems: readonly ContextItem[];
  toneZ: number | null;
  documentPublishedAt: string | null | undefined;
  documentOutlet: string | null | undefined;
  sourceMap: ReadonlyMap<string, SourceProfile>;
}>) {
  // Dated items for Timeline × Similarity scatter
  const datedPoints = useMemo(() => {
    const pts: {
      readonly id: string;
      readonly domain: string;
      readonly ms: number;
      readonly similarity: number;
      readonly isNetwork: boolean;
      readonly sharedTracker: boolean;
    }[] = [];

    const trackerCounts = new Map<string, number>();
    for (const item of storyItems) {
      for (const tid of item.tracking_ids) {
        trackerCounts.set(tid, (trackerCounts.get(tid) ?? 0) + 1);
      }
    }

    for (const item of storyItems) {
      if (!item.published_at) continue;
      const ms = new Date(item.published_at).getTime();
      if (Number.isNaN(ms)) continue;
      const dom = cleanDomain(item.outlet ?? item.url) || "source";
      const prof = sourceMap.get(dom);
      pts.push({
        id: item.id,
        domain: dom,
        ms,
        similarity: item.similarity ?? 0.85,
        isNetwork: Boolean(prof?.known_network),
        sharedTracker: item.tracking_ids.some((t) => (trackerCounts.get(t) ?? 0) > 1),
      });
    }
    return pts.sort((a, b) => a.ms - b.ms);
  }, [storyItems, sourceMap]);

  const docMs = useMemo(() => {
    if (!documentPublishedAt) return null;
    const t = new Date(documentPublishedAt).getTime();
    return Number.isNaN(t) ? null : t;
  }, [documentPublishedAt]);

  if (toneZ === null && datedPoints.length < 2) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Plot 1: Emotional Intensity Relative to Story Peers (z-score) */}
      {toneZ !== null && (
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-4 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-bold text-[var(--fg-primary)]">
              Emotional tone vs. story peers
            </div>
            <span className="font-mono-num text-xs font-semibold text-[var(--accent)]">
              z = {toneZ >= 0 ? `+${toneZ.toFixed(2)}` : toneZ.toFixed(2)}σ
            </span>
          </div>

          <svg
            viewBox="0 0 380 86"
            className="w-full h-auto select-none"
            role="img"
            aria-label="Article emotional intensity z-score relative to peer outlets covering the same story"
          >
            {/* Normal Peer Band [-1σ, +1σ] */}
            <rect
              x={190 - 48}
              y={22}
              width={96}
              height={24}
              rx={6}
              fill="var(--teal-soft)"
              stroke="var(--teal-border)"
            />
            <line
              x1={30}
              y1={34}
              x2={350}
              y2={34}
              stroke="var(--border-strong)"
              strokeWidth="2"
              strokeLinecap="round"
            />
            {/* Center Peer Mean Tick */}
            <line x1={190} y1={16} x2={190} y2={52} stroke="var(--teal)" strokeDasharray="3 2" />

            {/* Peer Dots Clustered near Mean */}
            {storyItems.slice(0, 7).map((item, i) => {
              const offset = ((i % 2 === 0 ? 1 : -1) * ((i + 1) * 13)) % 44;
              return (
                <circle
                  key={item.id}
                  cx={190 + offset}
                  cy={34}
                  r={4}
                  fill="var(--fg-muted)"
                  opacity="0.55"
                />
              );
            })}

            {/* Analysed Document Marker */}
            {(() => {
              const clampedZ = Math.max(-3.2, Math.min(3.2, toneZ));
              const docX = 190 + (clampedZ / 3.2) * 145;
              return (
                <g>
                  <circle
                    cx={docX}
                    cy={34}
                    r={7}
                    fill={toneZ > 1.0 ? "var(--accent)" : "var(--teal)"}
                    stroke="var(--bg-surface)"
                    strokeWidth="2"
                  />
                  <text
                    x={Math.max(48, Math.min(332, docX))}
                    y={13}
                    textAnchor="middle"
                    fontSize="10"
                    fontWeight="700"
                    fill="var(--fg-primary)"
                  >
                    {documentOutlet ? cleanDomain(documentOutlet) : "This item"}
                  </text>
                </g>
              );
            })()}

            <text x={30} y={72} fontSize="10" fill="var(--fg-muted)">
              −3σ Calmer
            </text>
            <text x={190} y={72} textAnchor="middle" fontSize="10" fill="var(--teal)">
              Peer average (±1σ)
            </text>
            <text x={350} y={72} textAnchor="end" fontSize="10" fill="var(--fg-muted)">
              More charged +3σ
            </text>
          </svg>
        </div>
      )}

      {/* Plot 2: Coverage Propagation Timeline × Semantic Similarity */}
      {datedPoints.length >= 2 && (
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-4 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-bold text-[var(--fg-primary)]">
              Coverage timeline &amp; similarity
            </div>
            <span className="font-mono-num text-[11px] text-[var(--fg-muted)]">
              {datedPoints.length} dated reports
            </span>
          </div>

          {(() => {
            const allMs = docMs !== null ? [...datedPoints.map((p) => p.ms), docMs] : datedPoints.map((p) => p.ms);
            const minMs = Math.min(...allMs);
            const maxMs = Math.max(...allMs);
            const spanMs = Math.max(3_600_000, maxMs - minMs);
            const xOfMs = (ms: number) => 36 + ((ms - minMs) / spanMs) * 314;

            return (
              <svg
                viewBox="0 0 380 86"
                className="w-full h-auto select-none"
                role="img"
                aria-label="Publication timeline versus semantic similarity across outlets"
              >
                {/* Axes */}
                <line x1={36} y1={64} x2={354} y2={64} stroke="var(--border-strong)" />
                <line x1={36} y1={16} x2={36} y2={64} stroke="var(--border-strong)" />

                {/* 6-hour burst window around document publication */}
                {docMs !== null && (
                  <rect
                    x={Math.max(36, xOfMs(docMs - 6 * 3_600_000))}
                    y={16}
                    width={Math.max(
                      6,
                      Math.min(354, xOfMs(docMs + 6 * 3_600_000)) -
                        Math.max(36, xOfMs(docMs - 6 * 3_600_000)),
                    )}
                    height={48}
                    fill="var(--accent-soft)"
                    opacity="0.7"
                  />
                )}

                {datedPoints.map((pt) => {
                  const cx = xOfMs(pt.ms);
                  const cy =
                    62 - Math.max(0, Math.min(1, (pt.similarity - 0.7) / 0.3)) * 42;
                  return (
                    <g key={pt.id}>
                      <title>{`${pt.domain} (${Math.round(pt.similarity * 100)}% match)`}</title>
                      <circle
                        cx={cx}
                        cy={cy}
                        r={5}
                        fill={
                          pt.isNetwork || pt.sharedTracker
                            ? "var(--caution)"
                            : "var(--accent)"
                        }
                        opacity="0.85"
                      />
                    </g>
                  );
                })}

                {docMs !== null && (
                  <line
                    x1={xOfMs(docMs)}
                    y1={14}
                    x2={xOfMs(docMs)}
                    y2={64}
                    stroke="var(--fg-primary)"
                    strokeWidth="1.5"
                    strokeDasharray="3 2"
                  />
                )}

                <text x={36} y={78} fontSize="10" fontFamily="var(--font-mono)" fill="var(--fg-muted)">
                  Earliest
                </text>
                {docMs !== null && (
                  <text x={195} y={78} textAnchor="middle" fontSize="10" fill="var(--accent)">
                    Shaded = ±6h copy window
                  </text>
                )}
                <text x={354} y={78} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--fg-muted)">
                  Latest
                </text>
              </svg>
            );
          })()}
        </div>
      )}
    </div>
  );
}

export function CoverageView({
  context,
  sources,
  evidence,
  claims,
  documentLanguage,
  documentOutlet,
  documentPublishedAt,
  activeEvidenceId,
  onSelectAnnotation,
}: Readonly<CoverageViewProps>) {
  const [tab, setTab] = useState<CoverageTab>("peers");

  const sourceMap = useMemo(() => {
    const map = new Map<string, SourceProfile>();
    for (const s of sources) {
      map.set(cleanDomain(s.domain), s);
    }
    return map;
  }, [sources]);

  const quotesByContextId = useMemo(() => {
    const map = new Map<string, { readonly evidenceId: string; readonly quote: string | null }[]>();
    for (const ev of evidence) {
      for (const ref of ev.source_refs) {
        if (ref.kind === "context") {
          const list = map.get(ref.id) ?? [];
          list.push({ evidenceId: ev.id, quote: ref.quote ?? null });
          map.set(ref.id, list);
        }
      }
    }
    return map;
  }, [evidence]);

  const storyPeers = useMemo(
    () => context.filter((c) => c.in_story !== false && !c.fact_check),
    [context],
  );
  const factChecks = useMemo(() => context.filter((c) => Boolean(c.fact_check)), [context]);
  const excludedItems = useMemo(
    () => context.filter((c) => c.in_story === false && !c.fact_check),
    [context],
  );

  const toneEvidence = useMemo(
    () => evidence.find((e) => e.family === "tone" && e.signal === "tone_vs_peers") ?? null,
    [evidence],
  );

  const claimVerificationRows = useMemo(() => {
    return claims.map((cl) => {
      const matching = evidence.filter(
        (ev) =>
          (ev.family === "claim_support" || ev.family === "fact_checks") &&
          ev.source_refs.some(
            (r) =>
              r.kind === "document" &&
              r.span.paragraph === cl.span.paragraph &&
              r.span.start <= cl.span.end &&
              r.span.end >= cl.span.start,
          ),
      );
      return { claim: cl, matching };
    });
  }, [claims, evidence]);

  const docLang = documentLanguage?.code?.toLowerCase() ?? null;

  const effectiveTab: CoverageTab =
    tab === "peers" && storyPeers.length === 0 && factChecks.length > 0
      ? "fact_checks"
      : tab === "peers" && storyPeers.length === 0 && sources.length > 0
        ? "domains"
        : tab;

  return (
    <div className="space-y-5">
      {/* Top Visual Plots + Claim Matrix */}
      <div className="editorial-card rounded-3xl p-5 sm:p-6 space-y-5">
        <div className="space-y-1">
          <h3 className="text-base font-bold text-[var(--fg-primary)] m-0">
            Cross-outlet comparison &amp; visited sources
          </h3>
          <p className="text-xs text-[var(--fg-secondary)] m-0">
            How independent outlets and fact-checkers covered the same event across languages.
          </p>
        </div>

        <PeerComparisonPlots
          storyItems={storyPeers}
          toneZ={toneEvidence?.value ?? null}
          documentPublishedAt={documentPublishedAt}
          documentOutlet={documentOutlet}
          sourceMap={sourceMap}
        />

        {/* Claim Verification Matrix */}
        {claimVerificationRows.length > 0 && (
          <div className="space-y-2.5 pt-1">
            <div className="text-xs font-bold text-[var(--fg-primary)]">
              Extracted claims vs. external coverage ({claimVerificationRows.length})
            </div>
            <div className="space-y-2">
              {claimVerificationRows.map(({ claim, matching }) => (
                <div
                  key={claim.id}
                  className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <p className="text-xs text-[var(--fg-primary)] leading-relaxed m-0 flex-1">
                    “{claim.text}”
                  </p>

                  <div className="flex flex-wrap items-center gap-1.5 shrink-0">
                    {matching.length === 0 ? (
                      <span className="px-2.5 py-0.5 rounded-full bg-[var(--bg-subtle)] text-[11px] text-[var(--fg-muted)]">
                        No direct contradiction or fact-check
                      </span>
                    ) : (
                      matching.map((ev) => {
                        const isFalseOrContra =
                          ev.signal === "rated_false" ||
                          ev.signal === "rated_misleading" ||
                          (ev.signal === "contradicted" && ev.value > 0.5);
                        return (
                          <button
                            key={ev.id}
                            type="button"
                            onClick={() => onSelectAnnotation(ev.id)}
                            className={cn(
                              "px-2.5 py-1 rounded-full text-[11px] font-semibold border cursor-pointer",
                              isFalseOrContra
                                ? "bg-[var(--caution-soft)] text-[var(--caution)] border-[var(--caution-border)]"
                                : "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)]",
                            )}
                          >
                            {signalLabel(ev.signal)}
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Visited Websites & Domain Profiles Browser */}
      <div className="editorial-card rounded-3xl p-5 sm:p-6 space-y-4">
        <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--border-subtle)] pb-3">
          {(
            [
              { id: "peers", label: `Same-event peers (${storyPeers.length})` },
              { id: "fact_checks", label: `Fact-checks (${factChecks.length})` },
              { id: "domains", label: `Outlet profiles (${sources.length})` },
              ...(excludedItems.length > 0
                ? [{ id: "excluded" as const, label: `Filtered out (${excludedItems.length})` }]
                : []),
            ] as const
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "px-3 py-1.5 rounded-full text-xs font-semibold transition-colors cursor-pointer",
                effectiveTab === t.id
                  ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)]/70",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {effectiveTab === "domains" ? (
          sources.length === 0 ? (
            <p className="text-xs text-[var(--fg-muted)] m-0">No domain records collected.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {sources.map((src) => {
                const typeMeta = src.outlet_type ? OUTLET_TYPE_LABELS[src.outlet_type] : null;
                const age = formatDomainAge(src.registered_at, src.first_cert_at, documentPublishedAt);
                return (
                  <div
                    key={src.domain}
                    className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-3.5 space-y-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--fg-primary)] truncate">
                        <Globe className="h-3.5 w-3.5 text-[var(--fg-muted)] shrink-0" aria-hidden="true" />
                        <span className="truncate">{src.domain}</span>
                      </span>
                      {src.country && (
                        <span className="font-mono-num text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] text-[var(--fg-muted)]">
                          {src.country}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                      {typeMeta && (
                        <span
                          className={cn(
                            "px-2 py-0.5 rounded-full font-medium border",
                            typeMeta.tone === "teal"
                              ? "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)]"
                              : typeMeta.tone === "caution"
                                ? "bg-[var(--caution-soft)] text-[var(--caution)] border-[var(--caution-border)]"
                                : "bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-[var(--border-subtle)]",
                          )}
                        >
                          {typeMeta.label}
                        </span>
                      )}

                      {age && (
                        <span className="px-2 py-0.5 rounded-full bg-[var(--bg-subtle)] font-mono-num text-[var(--fg-secondary)]">
                          {age}
                        </span>
                      )}

                      {src.known_network && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--caution-soft)] border border-[var(--caution-border)] font-semibold text-[var(--caution)]">
                          <ShieldAlert className="h-3 w-3" aria-hidden="true" />
                          <span>{networkLabel(src.known_network)}</span>
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )
        ) : (
          (() => {
            const list =
              effectiveTab === "peers"
                ? storyPeers
                : effectiveTab === "fact_checks"
                  ? factChecks
                  : excludedItems;

            if (list.length === 0) {
              return (
                <p className="text-xs text-[var(--fg-muted)] m-0 py-2">
                  No items in this category for the current analysis.
                </p>
              );
            }

            return (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {list.map((item) => {
                  const dom = cleanDomain(item.outlet ?? item.url) || "External source";
                  const profile = sourceMap.get(dom);
                  const typeMeta = profile?.outlet_type ? OUTLET_TYPE_LABELS[profile.outlet_type] : null;
                  const linkedQuotes = quotesByContextId.get(item.id) ?? [];
                  const isHighlighted =
                    activeEvidenceId !== null &&
                    linkedQuotes.some((q) => q.evidenceId === activeEvidenceId);

                  return (
                    <article
                      key={item.id}
                      className={cn(
                        "rounded-2xl border p-4 space-y-2.5 flex flex-col justify-between transition-colors",
                        isHighlighted
                          ? "border-[var(--accent)] bg-[var(--accent-soft)]/40"
                          : "border-[var(--border-subtle)] bg-[var(--bg-canvas)]",
                      )}
                    >
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-1.5 text-xs">
                          <div className="flex flex-wrap items-center gap-1.5 min-w-0">
                            <span className="font-bold text-[var(--fg-primary)] truncate">
                              {dom}
                            </span>

                            {item.language && (
                              <span
                                title={languageName(item.language)}
                                className={cn(
                                  "px-1.5 py-0.5 rounded font-mono-num text-[10px] uppercase border",
                                  docLang && item.language.toLowerCase() !== docLang
                                    ? "bg-[var(--accent-soft)] text-[var(--accent)] border-[var(--accent-border)]"
                                    : "bg-[var(--bg-subtle)] text-[var(--fg-muted)] border-[var(--border-subtle)]",
                                )}
                              >
                                {item.language}
                              </span>
                            )}

                            {typeMeta && (
                              <span className="px-2 py-0.5 rounded-full bg-[var(--bg-subtle)] text-[10px] font-medium text-[var(--fg-secondary)]">
                                {typeMeta.label}
                              </span>
                            )}
                          </div>

                          <span className="text-[10px] text-[var(--fg-muted)]">
                            {ADAPTER_LABELS[item.retrieved_by] ?? item.retrieved_by}
                          </span>
                        </div>

                        {item.fact_check && (
                          <div className="rounded-xl bg-[var(--caution-soft)]/70 border border-[var(--caution-border)] px-3 py-2 space-y-0.5">
                            <div className="inline-flex items-center gap-1 text-xs font-bold text-[var(--caution)]">
                              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                              <span>
                                {item.fact_check.publisher ?? dom}: {item.fact_check.rating}
                              </span>
                            </div>
                            <p className="text-[11px] text-[var(--fg-secondary)] m-0 line-clamp-2">
                              Reviewed claim: “{item.fact_check.claim}”
                            </p>
                          </div>
                        )}

                        <h4 className="text-xs sm:text-sm font-semibold text-[var(--fg-primary)] leading-snug m-0">
                          {item.title || dom}
                        </h4>

                        {linkedQuotes[0]?.quote ? (
                          <blockquote className="m-0 pl-2.5 border-l-2 border-[var(--accent)] text-xs italic text-[var(--fg-secondary)] line-clamp-3">
                            “{linkedQuotes[0].quote}”
                          </blockquote>
                        ) : item.text ? (
                          <p className="text-xs text-[var(--fg-secondary)] line-clamp-2 leading-relaxed m-0">
                            {item.text}
                          </p>
                        ) : null}

                        {item.story_reason && item.in_story === false && (
                          <p className="text-[11px] text-[var(--fg-muted)] m-0">
                            Filtered out: {item.story_reason}
                          </p>
                        )}
                      </div>

                      <div className="pt-2 border-t border-[var(--border-subtle)]/70 flex items-center justify-between gap-2 text-[11px] text-[var(--fg-muted)]">
                        <span className="font-mono-num">
                          {formatDateTime(item.published_at) ??
                            (item.similarity != null
                              ? `${formatPct(item.similarity, 0)} topic match`
                              : "Live web extract")}
                        </span>

                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 font-semibold text-[var(--accent)] hover:underline"
                        >
                          <span>Visit site</span>
                          <ExternalLink className="h-3 w-3" aria-hidden="true" />
                        </a>
                      </div>
                    </article>
                  );
                })}
              </div>
            );
          })()
        )}
      </div>
    </div>
  );
}
