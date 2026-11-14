import { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import type {
  Claim,
  ContextItem,
  Evidence,
  Language,
  SourceProfile,
} from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { formatDateTime, formatDomainAge, formatPct, formatShortDate } from "../lib/format";
import {
  ADAPTER_LABELS,
  OUTLET_TYPE_LABELS,
  languageName,
  networkLabel,
  signalLabel,
} from "../lib/labels";
import { tagClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { Favicon } from "./ui/Favicon";

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

const SECTION = "px-4 sm:px-5 py-4 border-t border-[var(--border-subtle)]";
const PLOT_LABEL = { fontSize: 10, fontFamily: "var(--font-mono)", fill: "var(--fg-muted)" } as const;

/** Tone z-score strip and publication timeline × similarity scatter. */
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
  const datedPoints = useMemo(() => {
    const pts: {
      readonly id: string;
      readonly domain: string;
      readonly ms: number;
      readonly similarity: number;
      readonly flagged: boolean;
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
      pts.push({
        id: item.id,
        domain: dom,
        ms,
        similarity: item.similarity ?? 0.85,
        flagged:
          Boolean(sourceMap.get(dom)?.known_network) ||
          item.tracking_ids.some((t) => (trackerCounts.get(t) ?? 0) > 1),
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
    <div className={cn(SECTION, "grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-6")}>
      {toneZ !== null && (
        <figure className="space-y-2">
          <figcaption className="flex items-baseline justify-between gap-2 text-xs">
            <span className="font-medium text-[var(--fg-secondary)]">Tone vs peers</span>
            <span className="font-mono-num text-[var(--fg-primary)]">
              z {toneZ >= 0 ? `+${toneZ.toFixed(2)}` : toneZ.toFixed(2)}
            </span>
          </figcaption>

          <svg
            viewBox="0 0 380 80"
            className="w-full h-auto select-none"
            role="img"
            aria-label={`Emotional tone z-score ${toneZ.toFixed(2)} relative to same-event peers`}
          >
            <rect x={190 - 45} y={24} width={90} height={20} rx={3} fill="var(--bg-subtle)" />
            <line x1={30} y1={34} x2={350} y2={34} stroke="var(--border-subtle)" strokeWidth="1" />
            <line x1={190} y1={20} x2={190} y2={48} stroke="var(--fg-muted)" strokeDasharray="2 2" />

            {storyItems.slice(0, 7).map((item, i) => {
              const offset = ((i % 2 === 0 ? 1 : -1) * ((i + 1) * 13)) % 44;
              return (
                <circle key={item.id} cx={190 + offset} cy={34} r={3} fill="var(--fg-muted)" opacity="0.6" />
              );
            })}

            {(() => {
              const clampedZ = Math.max(-3.2, Math.min(3.2, toneZ));
              const docX = 190 + (clampedZ / 3.2) * 145;
              return (
                <g>
                  <circle cx={docX} cy={34} r={5} fill="var(--accent)" stroke="var(--bg-surface)" strokeWidth="2" />
                  <text
                    x={Math.max(48, Math.min(332, docX))}
                    y={14}
                    textAnchor="middle"
                    {...PLOT_LABEL}
                    fill="var(--fg-primary)"
                  >
                    {documentOutlet ? cleanDomain(documentOutlet) : "this item"}
                  </text>
                </g>
              );
            })()}

            <text x={30} y={68} {...PLOT_LABEL}>
              −3σ calmer
            </text>
            <text x={190} y={68} textAnchor="middle" {...PLOT_LABEL}>
              mean ±1σ
            </text>
            <text x={350} y={68} textAnchor="end" {...PLOT_LABEL}>
              charged +3σ
            </text>
          </svg>
        </figure>
      )}

      {datedPoints.length >= 2 && (
        <figure className="space-y-2">
          <figcaption className="flex items-baseline justify-between gap-2 text-xs">
            <span className="font-medium text-[var(--fg-secondary)]">Timeline</span>
            <span className="inline-flex items-center gap-3 text-[var(--fg-muted)]">
              <span className="inline-flex items-center gap-1">
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
                peer
              </span>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[var(--caution)]" />
                network / shared tag
              </span>
            </span>
          </figcaption>

          {(() => {
            const allMs = docMs !== null ? [...datedPoints.map((p) => p.ms), docMs] : datedPoints.map((p) => p.ms);
            const minMs = Math.min(...allMs);
            const maxMs = Math.max(...allMs);
            const spanMs = Math.max(3_600_000, maxMs - minMs);
            const xOfMs = (ms: number) => 40 + ((ms - minMs) / spanMs) * 310;
            const windowStart = docMs !== null ? Math.max(40, xOfMs(docMs - 6 * 3_600_000)) : 0;
            const windowEnd = docMs !== null ? Math.min(350, xOfMs(docMs + 6 * 3_600_000)) : 0;

            return (
              <svg
                viewBox="0 0 380 80"
                className="w-full h-auto select-none"
                role="img"
                aria-label="Publication time versus similarity across outlets"
              >
                {docMs !== null && (
                  <rect
                    x={windowStart}
                    y={12}
                    width={Math.max(6, windowEnd - windowStart)}
                    height={48}
                    fill="var(--bg-subtle)"
                  />
                )}
                <line x1={40} y1={60} x2={350} y2={60} stroke="var(--border-subtle)" />
                <line x1={40} y1={12} x2={40} y2={60} stroke="var(--border-subtle)" />
                <text x={35} y={18} textAnchor="end" {...PLOT_LABEL}>
                  100%
                </text>
                <text x={35} y={60} textAnchor="end" {...PLOT_LABEL}>
                  70%
                </text>

                {datedPoints.map((pt) => (
                  <circle
                    key={pt.id}
                    cx={xOfMs(pt.ms)}
                    cy={58 - Math.max(0, Math.min(1, (pt.similarity - 0.7) / 0.3)) * 42}
                    r={4}
                    fill={pt.flagged ? "var(--caution)" : "var(--accent)"}
                    opacity="0.85"
                  >
                    <title>{`${pt.domain} · ${Math.round(pt.similarity * 100)}%`}</title>
                  </circle>
                ))}

                {docMs !== null && (
                  <line
                    x1={xOfMs(docMs)}
                    y1={10}
                    x2={xOfMs(docMs)}
                    y2={60}
                    stroke="var(--fg-primary)"
                    strokeDasharray="2 2"
                  />
                )}

                <text x={40} y={74} {...PLOT_LABEL}>
                  {formatShortDate(new Date(minMs).toISOString()) ?? ""}
                </text>
                {docMs !== null && (
                  <text x={195} y={74} textAnchor="middle" {...PLOT_LABEL}>
                    ±6h window
                  </text>
                )}
                <text x={350} y={74} textAnchor="end" {...PLOT_LABEL}>
                  {formatShortDate(new Date(maxMs).toISOString()) ?? ""}
                </text>
              </svg>
            );
          })()}
        </figure>
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
  const crossLanguageCount = docLang
    ? storyPeers.filter((c) => c.language && c.language.toLowerCase() !== docLang).length
    : 0;

  const effectiveTab: CoverageTab =
    tab === "peers" && storyPeers.length === 0 && factChecks.length > 0
      ? "fact_checks"
      : tab === "peers" && storyPeers.length === 0 && sources.length > 0
        ? "domains"
        : tab;

  const tabs: readonly { readonly id: CoverageTab; readonly label: string; readonly count: number }[] = [
    { id: "peers", label: "Same event", count: storyPeers.length },
    { id: "fact_checks", label: "Fact-checks", count: factChecks.length },
    { id: "domains", label: "Outlets", count: sources.length },
    ...(excludedItems.length > 0
      ? [{ id: "excluded" as const, label: "Dropped", count: excludedItems.length }]
      : []),
  ];

  const list =
    effectiveTab === "peers" ? storyPeers : effectiveTab === "fact_checks" ? factChecks : excludedItems;

  return (
    <section aria-labelledby="coverage-heading" className="editorial-card rounded-xl overflow-hidden">
      <header className="px-4 sm:px-5 py-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex items-baseline gap-2 min-w-0">
          <h3 id="coverage-heading" className="text-sm font-medium text-[var(--fg-primary)]">
            Coverage
          </h3>
          <span className="font-mono-num text-xs text-[var(--fg-muted)]">
            {context.length} reports · {storyPeers.length} on the same event
            {crossLanguageCount > 0 && ` · ${crossLanguageCount} other-language`}
          </span>
        </div>

        <div role="tablist" className="inline-flex rounded-lg bg-[var(--bg-subtle)] p-0.5">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={effectiveTab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "h-6 px-2.5 rounded-md text-xs font-medium inline-flex items-center gap-1.5 transition-colors cursor-pointer",
                effectiveTab === t.id
                  ? "bg-[var(--bg-surface)] text-[var(--fg-primary)] shadow-[var(--shadow-editorial)]"
                  : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]",
              )}
            >
              {t.label}
              <span className="font-mono-num text-[11px] text-[var(--fg-muted)]">{t.count}</span>
            </button>
          ))}
        </div>
      </header>

      {effectiveTab === "domains" ? (
        sources.length === 0 ? (
          <p className={cn(SECTION, "text-[13px] text-[var(--fg-muted)]")}>No outlet records.</p>
        ) : (
          <ul className="p-0 list-none">
            {sources.map((src) => {
              const typeMeta = src.outlet_type ? OUTLET_TYPE_LABELS[src.outlet_type] : null;
              const age = formatDomainAge(src.registered_at, src.first_cert_at, documentPublishedAt);
              return (
                <li
                  key={src.domain}
                  className="px-4 sm:px-5 py-2.5 border-t border-[var(--border-subtle)] flex flex-wrap items-center gap-x-2 gap-y-1 hover:bg-[var(--bg-hover)] transition-colors"
                >
                  <Favicon domain={src.domain} size={14} />
                  <span className="font-mono-num text-xs text-[var(--fg-primary)] truncate">{src.domain}</span>
                  {src.country && <span className={tagClass("neutral", { mono: true })}>{src.country}</span>}
                  {typeMeta && <span className={tagClass(typeMeta.tone)}>{typeMeta.label}</span>}
                  {src.known_network && (
                    <span className={tagClass("caution")}>{networkLabel(src.known_network)}</span>
                  )}
                  {age && <span className="ml-auto font-mono-num text-xs text-[var(--fg-muted)]">{age}</span>}
                </li>
              );
            })}
          </ul>
        )
      ) : list.length === 0 ? (
        <p className={cn(SECTION, "text-[13px] text-[var(--fg-muted)]")}>None found.</p>
      ) : (
        <ul className="p-0 list-none">
          {list.map((item) => {
            const dom = cleanDomain(item.outlet ?? item.url) || "source";
            const profile = sourceMap.get(dom);
            const typeMeta = profile?.outlet_type ? OUTLET_TYPE_LABELS[profile.outlet_type] : null;
            const linkedQuotes = quotesByContextId.get(item.id) ?? [];
            const quoted = linkedQuotes.find((q) => q.quote);
            const isHighlighted =
              activeEvidenceId !== null && linkedQuotes.some((q) => q.evidenceId === activeEvidenceId);
            const otherLanguage = Boolean(docLang && item.language && item.language.toLowerCase() !== docLang);
            const date = formatDateTime(item.published_at);

            return (
              <li
                key={item.id}
                className={cn(
                  "group px-4 sm:px-5 py-3 border-t border-[var(--border-subtle)] space-y-1 transition-colors",
                  isHighlighted
                    ? "bg-[var(--bg-hover)] shadow-[inset_2px_0_0_var(--accent)]"
                    : "hover:bg-[var(--bg-hover)]",
                )}
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Favicon domain={dom} size={14} />
                  <span className="font-mono-num text-xs text-[var(--fg-secondary)] truncate">{dom}</span>
                  {typeMeta && <span className={tagClass(typeMeta.tone)}>{typeMeta.label}</span>}
                  {profile?.known_network && (
                    <span className={tagClass("caution")}>{networkLabel(profile.known_network)}</span>
                  )}
                  {item.fact_check && (
                    <span className={tagClass("caution")}>
                      {item.fact_check.rating}
                      {item.fact_check.publisher && ` · ${item.fact_check.publisher}`}
                    </span>
                  )}
                </div>

                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-baseline gap-1.5 text-sm font-medium leading-snug text-[var(--fg-primary)] hover:text-[var(--accent)]"
                >
                  <span>{item.title || dom}</span>
                  <ExternalLink
                    className="h-3 w-3 shrink-0 self-center text-[var(--fg-muted)] opacity-0 group-hover:opacity-100 transition-opacity"
                    aria-hidden="true"
                  />
                </a>

                <div className="flex flex-wrap items-center gap-x-1.5 text-xs text-[var(--fg-muted)]">
                  {[
                    date && <span key="date" className="font-mono-num">{date}</span>,
                    item.language && (
                      <span
                        key="lang"
                        title={languageName(item.language)}
                        className={cn("font-mono-num uppercase", otherLanguage && "text-[var(--accent)]")}
                      >
                        {item.language}
                      </span>
                    ),
                    <span key="adapter">{ADAPTER_LABELS[item.retrieved_by] ?? item.retrieved_by}</span>,
                    item.similarity != null && (
                      <span key="sim" className="font-mono-num">
                        {formatPct(item.similarity, 0)} match
                      </span>
                    ),
                  ]
                    .filter(Boolean)
                    .flatMap((node, i) =>
                      i === 0 ? [node] : [<span key={`sep${i}`} aria-hidden="true">·</span>, node],
                    )}
                </div>

                {item.fact_check && (
                  <p className="text-[13px] text-[var(--fg-secondary)] line-clamp-2">
                    “{item.fact_check.claim}”
                  </p>
                )}

                {quoted?.quote ? (
                  <button
                    type="button"
                    onClick={() => onSelectAnnotation(quoted.evidenceId)}
                    className="block text-left text-[13px] leading-relaxed text-[var(--fg-primary)] cursor-pointer"
                  >
                    <mark
                      className={cn(
                        "text-inherit rounded-[2px] box-decoration-clone line-clamp-3",
                        quoted.evidenceId === activeEvidenceId ? "bg-[var(--mark-strong)]" : "bg-[var(--mark)]",
                      )}
                    >
                      “{quoted.quote}”
                    </mark>
                  </button>
                ) : (
                  !item.fact_check &&
                  item.text && (
                    <p className="text-[13px] text-[var(--fg-secondary)] leading-relaxed line-clamp-2">
                      {item.text}
                    </p>
                  )
                )}

                {item.story_reason && item.in_story === false && (
                  <p className="text-xs text-[var(--fg-muted)]">Dropped: {item.story_reason}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <PeerComparisonPlots
        storyItems={storyPeers}
        toneZ={toneEvidence?.value ?? null}
        documentPublishedAt={documentPublishedAt}
        documentOutlet={documentOutlet}
        sourceMap={sourceMap}
      />

      {claimVerificationRows.length > 0 && (
        <div className="border-t border-[var(--border-subtle)]">
          <div className="px-4 sm:px-5 pt-4 pb-2 flex items-baseline gap-2">
            <h4 className="text-sm font-medium text-[var(--fg-primary)]">Claims</h4>
            <span className="font-mono-num text-xs text-[var(--fg-muted)]">{claimVerificationRows.length}</span>
          </div>
          <ul className="p-0 list-none">
            {claimVerificationRows.map(({ claim, matching }) => (
              <li
                key={claim.id}
                className="px-4 sm:px-5 py-2.5 border-t border-[var(--border-subtle)] flex flex-col sm:flex-row sm:items-center justify-between gap-2"
              >
                <p className="text-[13px] text-[var(--fg-primary)] leading-relaxed flex-1">“{claim.text}”</p>
                <div className="flex flex-wrap items-center gap-1 shrink-0">
                  {matching.length === 0 ? (
                    <span className="text-xs text-[var(--fg-muted)]">No match</span>
                  ) : (
                    matching.map((ev) => {
                      const disputed =
                        ev.signal === "rated_false" ||
                        ev.signal === "rated_misleading" ||
                        (ev.signal === "contradicted" && ev.value > 0.5);
                      return (
                        <button
                          key={ev.id}
                          type="button"
                          onClick={() => onSelectAnnotation(ev.id)}
                          className={tagClass(
                            disputed ? "caution" : "teal",
                            undefined,
                            cn(
                              "cursor-pointer hover:border-current",
                              ev.id === activeEvidenceId && "ring-1 ring-current",
                            ),
                          )}
                        >
                          {signalLabel(ev.signal)}
                        </button>
                      );
                    })
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
