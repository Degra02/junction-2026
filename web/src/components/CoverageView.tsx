import { useMemo, useState } from "react";
import { ExternalLink, Layers, Scale, ShieldAlert, CheckCircle2 } from "lucide-react";
import type {
  Claim,
  ContextItem,
  Evidence,
  Language,
  SourceProfile,
} from "../lib/contracts";
import { formatDateTime, formatDomainAge, formatPct } from "../lib/format";
import {
  ADAPTER_LABELS,
  OUTLET_TYPE_LABELS,
  languageName,
  networkLabel,
} from "../lib/labels";
import { cn } from "../lib/utils";

export interface CoverageViewProps {
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly evidence: readonly Evidence[];
  readonly claims: readonly Claim[];
  readonly documentLanguage: Language | null | undefined;
  readonly documentPublishedAt: string | null | undefined;
  readonly activeEvidenceId: string | null;
  readonly onSelectAnnotation: (id: string) => void;
  readonly isPending: boolean;
}

type TabKey = "story" | "fact_checks" | "excluded";

function normalizeDomain(domain: string | null | undefined): string {
  if (!domain) return "";
  return domain.trim().toLowerCase().replace(/^www\./, "");
}

function sortByPublishedAsc(items: readonly ContextItem[]): ContextItem[] {
  return items.slice().sort((a, b) => {
    if (!a.published_at && !b.published_at) return (b.similarity ?? 0) - (a.similarity ?? 0);
    if (!a.published_at) return 1;
    if (!b.published_at) return -1;
    return new Date(a.published_at).getTime() - new Date(b.published_at).getTime();
  });
}

export function CoverageView({
  context,
  sources,
  evidence,
  claims,
  documentLanguage,
  documentPublishedAt,
  activeEvidenceId,
  onSelectAnnotation,
  isPending,
}: Readonly<CoverageViewProps>) {
  const [tab, setTab] = useState<TabKey>("story");

  const sourceMap = useMemo(() => {
    const map = new Map<string, SourceProfile>();
    for (const src of sources) {
      map.set(normalizeDomain(src.domain), src);
    }
    return map;
  }, [sources]);

  const quotesByContextId = useMemo(() => {
    const map = new Map<string, { readonly evidenceId: string; readonly quote: string | null }[]>();
    for (const ev of evidence) {
      for (const ref of ev.source_refs) {
        if (ref.kind === "context") {
          const existing = map.get(ref.id) ?? [];
          existing.push({ evidenceId: ev.id, quote: ref.quote ?? null });
          map.set(ref.id, existing);
        }
      }
    }
    return map;
  }, [evidence]);

  const storyItems = useMemo(
    () => sortByPublishedAsc(context.filter((c) => c.in_story !== false && !c.fact_check)),
    [context],
  );
  const factChecks = useMemo(
    () => sortByPublishedAsc(context.filter((c) => Boolean(c.fact_check))),
    [context],
  );
  const excludedItems = useMemo(
    () => context.filter((c) => c.in_story === false && !c.fact_check),
    [context],
  );

  const docLang = documentLanguage?.code?.toLowerCase() ?? null;
  const sameLangPeers = useMemo(
    () =>
      docLang
        ? storyItems.filter((c) => !c.language || c.language.toLowerCase() === docLang)
        : storyItems,
    [storyItems, docLang],
  );
  const crossLangPeers = useMemo(
    () =>
      docLang
        ? storyItems.filter((c) => Boolean(c.language && c.language.toLowerCase() !== docLang))
        : [],
    [storyItems, docLang],
  );

  const toneEvidence = useMemo(
    () => evidence.find((e) => e.family === "tone" && e.signal === "tone_vs_peers") ?? null,
    [evidence],
  );

  const claimEvidenceMap = useMemo(() => {
    const map = new Map<string, Evidence[]>();
    for (const cl of claims) {
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
      map.set(cl.id, matching);
    }
    return map;
  }, [claims, evidence]);

  const effectiveTab: TabKey =
    tab === "story" && storyItems.length === 0 && factChecks.length > 0
      ? "fact_checks"
      : tab === "story" && storyItems.length === 0 && excludedItems.length > 0
        ? "excluded"
        : tab;

  function renderContextItem(item: ContextItem) {
    const profile = sourceMap.get(normalizeDomain(item.outlet));
    const outletTypeMeta = profile?.outlet_type ? OUTLET_TYPE_LABELS[profile.outlet_type] : null;
    const domainAge = formatDomainAge(
      profile?.registered_at,
      profile?.first_cert_at,
      documentPublishedAt ?? item.published_at,
    );
    const linkedRefs = quotesByContextId.get(item.id) ?? [];
    const isHighlighted =
      activeEvidenceId !== null && linkedRefs.some((r) => r.evidenceId === activeEvidenceId);

    return (
      <article
        key={item.id}
        className={cn(
          "rounded-lg border p-3.5 space-y-2 transition-colors",
          isHighlighted
            ? "border-[var(--accent)] bg-[var(--accent-soft)]/50"
            : "border-[var(--border-subtle)] bg-[var(--bg-canvas)]",
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold text-[var(--fg-primary)]">
              {item.outlet || "External source"}
            </span>

            {profile?.country && (
              <span className="px-1.5 py-0.5 rounded border border-[var(--border-subtle)] font-mono-num text-[10px] text-[var(--fg-muted)]">
                {profile.country}
              </span>
            )}

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

            {outletTypeMeta && (
              <span
                className={cn(
                  "px-2 py-0.5 rounded-md text-[11px] font-medium border",
                  outletTypeMeta.tone === "teal"
                    ? "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)]"
                    : outletTypeMeta.tone === "caution"
                      ? "bg-[var(--caution-soft)] text-[var(--caution)] border-[var(--caution-border)]"
                      : "bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-[var(--border-subtle)]",
                )}
              >
                {outletTypeMeta.label}
              </span>
            )}

            {profile?.known_network && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[var(--caution-soft)] border border-[var(--caution-border)] text-[11px] font-semibold text-[var(--caution)]">
                <ShieldAlert className="h-3 w-3" aria-hidden="true" />
                {networkLabel(profile.known_network)}
              </span>
            )}

            {domainAge && (
              <span className="font-mono-num text-[11px] text-[var(--fg-muted)]">{domainAge}</span>
            )}
          </div>

          <div className="flex items-center gap-2 text-[11px] font-mono-num text-[var(--fg-muted)]">
            {item.published_at && <span>{formatDateTime(item.published_at)}</span>}
            {item.similarity != null && (
              <span title="Story embedding similarity">
                sim {formatPct(item.similarity, 0)}
              </span>
            )}
            <span className="px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] text-[10px]">
              {ADAPTER_LABELS[item.retrieved_by] ?? item.retrieved_by}
            </span>
          </div>
        </div>

        <div className="flex items-start justify-between gap-3">
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm font-semibold text-[var(--fg-primary)] hover:text-[var(--accent)] hover:underline leading-snug inline-flex items-start gap-1.5"
          >
            <span>{item.title || item.url}</span>
            <ExternalLink className="h-3.5 w-3.5 shrink-0 mt-0.5 text-[var(--fg-muted)]" aria-hidden="true" />
          </a>
        </div>

        {item.fact_check && (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2.5 text-xs space-y-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-[var(--fg-secondary)]">
                ClaimReview{item.fact_check.publisher ? ` · ${item.fact_check.publisher}` : ""}
              </span>
              <span className="px-2 py-0.5 rounded font-mono-num font-semibold bg-[var(--caution-soft)] border border-[var(--caution-border)] text-[var(--caution)]">
                Rating: {item.fact_check.rating}
              </span>
            </div>
            <p className="text-[var(--fg-primary)] m-0">Reviewed claim: “{item.fact_check.claim}”</p>
          </div>
        )}

        {item.in_story === false && item.story_reason && (
          <p className="text-xs text-[var(--fg-muted)] m-0">
            Excluded from story peer set: <span className="text-[var(--fg-secondary)]">{item.story_reason}</span>
          </p>
        )}

        {linkedRefs.length > 0 && (
          <div className="space-y-1.5 pt-1">
            {linkedRefs.map((ref, rIdx) => (
              <div
                key={`${ref.evidenceId}-${rIdx}`}
                className="flex items-start gap-2 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] px-2.5 py-1.5 text-xs"
              >
                <button
                  type="button"
                  onClick={() => onSelectAnnotation(ref.evidenceId)}
                  className="font-mono-num font-semibold text-[var(--accent)] hover:underline shrink-0 cursor-pointer"
                >
                  [{ref.evidenceId}]
                </button>
                <span className="text-[var(--fg-secondary)]">
                  {ref.quote ? `Verbatim match: “${ref.quote}”` : "Referenced by signal evidence"}
                </span>
              </div>
            ))}
          </div>
        )}

        {item.tracking_ids.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--fg-muted)]">
            <span>Analytics IDs:</span>
            {item.tracking_ids.map((tid) => (
              <code
                key={tid}
                className="px-1.5 py-0.5 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] font-mono-num"
              >
                {tid}
              </code>
            ))}
          </div>
        )}
      </article>
    );
  }

  return (
    <section
      aria-labelledby="coverage-heading"
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-[var(--accent)]" aria-hidden="true" />
          <h2
            id="coverage-heading"
            className="text-base font-bold tracking-tight text-[var(--fg-primary)] m-0"
          >
            Story coverage &amp; peer comparison
          </h2>
        </div>

        <span className="text-xs font-mono-num text-[var(--fg-muted)]">
          {storyItems.length} in story · {factChecks.length} fact-checks · {excludedItems.length} excluded
        </span>
      </div>

      {/* Peer-relative position strip: Tone & Claim stance */}
      {(toneEvidence || claims.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-3.5 space-y-2">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="font-semibold text-[var(--fg-primary)] inline-flex items-center gap-1.5">
                <Scale className="h-3.5 w-3.5 text-[var(--fg-muted)]" aria-hidden="true" />
                Tone vs. story peers
              </span>
              {toneEvidence && (
                <span className="font-mono-num text-xs text-[var(--fg-secondary)]">
                  z = {toneEvidence.value >= 0 ? `+${toneEvidence.value.toFixed(2)}` : toneEvidence.value.toFixed(2)}
                </span>
              )}
            </div>

            {toneEvidence ? (
              <>
                <div className="relative h-2 rounded-full bg-[var(--bg-subtle)] border border-[var(--border-subtle)]">
                  <div className="absolute top-0 bottom-0 left-1/2 w-px bg-[var(--border-strong)]" />
                  <div
                    className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-3.5 w-3.5 rounded-full bg-[var(--accent)] border-2 border-[var(--bg-surface)]"
                    style={{
                      left: `${Math.max(5, Math.min(95, ((toneEvidence.value + 3) / 6) * 100))}%`,
                    }}
                  />
                </div>
                <div className="flex justify-between text-[10px] font-mono-num text-[var(--fg-muted)]">
                  <span>−3σ calmer</span>
                  <span>peer average</span>
                  <span>+3σ more charged</span>
                </div>
                <p className="text-xs text-[var(--fg-secondary)] m-0">{toneEvidence.detail}</p>
              </>
            ) : (
              <p className="text-xs text-[var(--fg-muted)] m-0 leading-relaxed">
                Peer-relative tone requires at least 3 independent non-copy reports covering the same event ({storyItems.length} in story).
              </p>
            )}
          </div>

          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-3.5 space-y-2">
            <div className="text-xs font-semibold text-[var(--fg-primary)]">
              Claim corroboration across coverage
            </div>
            {claims.length === 0 ? (
              <p className="text-xs text-[var(--fg-muted)] m-0">
                No verifiable factual claims extracted from this text.
              </p>
            ) : (
              <ul className="space-y-1.5 list-none p-0 m-0">
                {claims.map((cl) => {
                  const relatedEv = claimEvidenceMap.get(cl.id) ?? [];
                  return (
                    <li key={cl.id} className="text-xs flex items-start justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => onSelectAnnotation(cl.id)}
                        className="text-left text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] line-clamp-1 cursor-pointer"
                      >
                        <span className="font-mono-num text-[var(--accent)] font-semibold mr-1">
                          [{cl.id}]
                        </span>
                        {cl.text}
                      </button>
                      {relatedEv.length > 0 ? (
                        <div className="flex items-center gap-1 shrink-0">
                          {relatedEv.map((ev) => (
                            <button
                              key={ev.id}
                              type="button"
                              onClick={() => onSelectAnnotation(ev.id)}
                              title={ev.detail}
                              className="px-1.5 py-0.5 rounded bg-[var(--accent-soft)] border border-[var(--accent-border)] font-mono-num text-[11px] font-medium text-[var(--accent)] cursor-pointer"
                            >
                              [{ev.id}]
                            </button>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[11px] text-[var(--fg-muted)] shrink-0 inline-flex items-center gap-1">
                          <CheckCircle2 className="h-3 w-3 text-[var(--fg-muted)]" aria-hidden="true" />
                          no conflict
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div
        role="tablist"
        aria-label="Coverage categories"
        className="flex flex-wrap items-center gap-1.5 border-b border-[var(--border-subtle)] pb-2.5"
      >
        {(
          [
            { key: "story", label: `Same-event coverage (${storyItems.length})` },
            { key: "fact_checks", label: `Fact-checks (${factChecks.length})` },
            { key: "excluded", label: `Dropped / other events (${excludedItems.length})` },
          ] as const
        ).map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={effectiveTab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer",
              effectiveTab === t.key
                ? "bg-[var(--accent-soft)] text-[var(--accent)] font-semibold"
                : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)]",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isPending && context.length === 0 ? (
        <div className="space-y-2.5 py-2" aria-busy="true">
          <div className="h-16 w-full rounded-lg bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-16 w-full rounded-lg bg-[var(--bg-subtle)] animate-pulse" />
        </div>
      ) : context.length === 0 ? (
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/50 p-4 text-xs text-[var(--fg-secondary)]">
          No external coverage or ClaimReview fact-checks were returned by the retrieval adapters for this item.
        </div>
      ) : effectiveTab === "story" ? (
        storyItems.length === 0 ? (
          <p className="text-xs text-[var(--fg-muted)] m-0 py-2">
            None of the {context.length} retrieved items met the same-event story similarity threshold. Inspect the “Dropped / other events” tab to see why each item was filtered out.
          </p>
        ) : (
          <div className="space-y-4">
            {sameLangPeers.length > 0 && (
              <div className="space-y-2.5">
                {crossLangPeers.length > 0 && (
                  <h3 className="text-xs font-semibold text-[var(--fg-secondary)] m-0">
                    Coverage in {languageName(docLang)} ({sameLangPeers.length}) — chronological order
                  </h3>
                )}
                {sameLangPeers.map(renderContextItem)}
              </div>
            )}

            {crossLangPeers.length > 0 && (
              <div className="space-y-2.5 pt-2 border-t border-[var(--border-subtle)]">
                <h3 className="text-xs font-semibold text-[var(--fg-secondary)] m-0">
                  Cross-language international coverage ({crossLangPeers.length}) — evaluated via multilingual NLI
                </h3>
                {crossLangPeers.map(renderContextItem)}
              </div>
            )}
          </div>
        )
      ) : effectiveTab === "fact_checks" ? (
        factChecks.length === 0 ? (
          <p className="text-xs text-[var(--fg-muted)] m-0 py-2">
            No matching ClaimReview fact-checks were found for the claims in this content.
          </p>
        ) : (
          <div className="space-y-2.5">{factChecks.map(renderContextItem)}</div>
        )
      ) : excludedItems.length === 0 ? (
        <p className="text-xs text-[var(--fg-muted)] m-0 py-2">
          Every retrieved non-fact-check article matched the same event.
        </p>
      ) : (
        <div className="space-y-2.5">{excludedItems.map(renderContextItem)}</div>
      )}
    </section>
  );
}
