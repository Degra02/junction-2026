import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, FileText, Tag } from "lucide-react";
import type { Claim, DocumentData, Evidence, SearchQuery, Topic } from "../lib/contracts";
import { formatShortDate } from "../lib/format";
import { languageName } from "../lib/labels";
import { collectDocumentAnnotations, segmentParagraph } from "../lib/spans";
import { cn } from "../lib/utils";

export interface DocumentReaderProps {
  readonly document: DocumentData | null | undefined;
  readonly topic: Topic | null | undefined;
  readonly claims: readonly Claim[];
  readonly queries: readonly SearchQuery[];
  readonly evidence: readonly Evidence[];
  readonly activeAnnotationId: string | null;
  readonly onSelectAnnotation: (id: string) => void;
  readonly isPending: boolean;
}

export function DocumentReader({
  document,
  topic,
  claims,
  queries,
  evidence,
  activeAnnotationId,
  onSelectAnnotation,
  isPending,
}: Readonly<DocumentReaderProps>) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [showClaimsDrawer, setShowClaimsDrawer] = useState<boolean>(false);

  const annotations = useMemo(
    () => collectDocumentAnnotations(claims, evidence),
    [claims, evidence],
  );

  useEffect(() => {
    if (!activeAnnotationId || !containerRef.current) return;
    const target = containerRef.current.querySelector<HTMLElement>(
      `[data-annotation-ids~="${CSS.escape(activeAnnotationId)}"]`,
    );
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeAnnotationId]);

  const pubDate = formatShortDate(document?.published_at);

  return (
    <section
      ref={containerRef}
      aria-labelledby="reader-heading"
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 sm:p-5 space-y-4"
    >
      <div className="flex items-center justify-between gap-2 pb-3 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 text-[var(--fg-muted)] shrink-0" aria-hidden="true" />
          <h2
            id="reader-heading"
            className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-secondary)] m-0 truncate"
          >
            Analysed content
          </h2>
        </div>

        {annotations.length > 0 && (() => {
          const spanCount = annotations.filter((a) => a.kind === "evidence").length;
          return (
            <span className="text-[11px] font-mono-num text-[var(--fg-muted)] shrink-0">
              {claims.length} {claims.length === 1 ? "claim" : "claims"} · {spanCount}{" "}
              {spanCount === 1 ? "span ref" : "span refs"}
            </span>
          );
        })()}
      </div>

      {isPending && !document ? (
        <div className="space-y-2.5 py-2" aria-busy="true">
          <div className="h-5 w-3/4 rounded bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-3.5 w-full rounded bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-3.5 w-11/12 rounded bg-[var(--bg-subtle)] animate-pulse" />
          <div className="h-3.5 w-4/5 rounded bg-[var(--bg-subtle)] animate-pulse" />
        </div>
      ) : !document || document.paragraphs.length === 0 ? (
        <p className="text-xs text-[var(--fg-muted)] m-0">
          No extracted paragraphs available for this item.
        </p>
      ) : (
        <>
          {(document.title || document.outlet || document.author || pubDate) && (
            <div className="space-y-1.5 pb-3 border-b border-[var(--border-subtle)]">
              {document.title && (
                <h3 className="text-sm font-bold text-[var(--fg-primary)] leading-snug m-0">
                  {document.title}
                </h3>
              )}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--fg-muted)]">
                {document.outlet && <span className="font-medium text-[var(--fg-secondary)]">{document.outlet}</span>}
                {document.author && <span>By {document.author}</span>}
                {pubDate && <span className="font-mono-num">{pubDate}</span>}
                {document.url && (
                  <a
                    href={document.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline"
                  >
                    <span>Source URL</span>
                    <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  </a>
                )}
              </div>
              {document.tracking_ids.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-[11px] text-[var(--fg-muted)]">Tracking IDs:</span>
                  {document.tracking_ids.map((tid) => (
                    <code
                      key={tid}
                      className="px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[11px] font-mono-num text-[var(--fg-secondary)]"
                    >
                      {tid}
                    </code>
                  ))}
                </div>
              )}
            </div>
          )}

          {topic && (
            <div className="rounded-lg bg-[var(--bg-subtle)]/70 border border-[var(--border-subtle)] p-3 space-y-1.5">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--fg-secondary)]">
                <Tag className="h-3 w-3 text-[var(--fg-muted)]" aria-hidden="true" />
                <span>Event summary</span>
                {topic.place ? ` · ${topic.place}` : ""}
                {topic.date ? ` (${topic.date})` : ""}
              </div>
              <p className="text-xs text-[var(--fg-primary)] leading-relaxed m-0">{topic.summary}</p>
              {topic.entities.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-0.5">
                  {topic.entities.map((ent) => (
                    <span
                      key={ent}
                      className="px-1.5 py-0.5 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-[11px] text-[var(--fg-secondary)]"
                    >
                      {ent}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1">
            {document.paragraphs.map((para, pIdx) => {
              const segments = segmentParagraph(para, pIdx, annotations);
              const seenBadgeInPara = new Set<string>();

              return (
                <p
                  key={pIdx}
                  className="text-xs sm:text-[13px] leading-[1.7] text-[var(--fg-primary)] m-0 max-w-[68ch]"
                >
                  <span className="font-mono-num text-[10px] text-[var(--fg-muted)] select-none mr-2">
                    ¶{pIdx + 1}
                  </span>
                  {segments.map((seg) => {
                    if (seg.annotations.length === 0) {
                      return <span key={`${seg.start}-${seg.end}`}>{seg.text}</span>;
                    }

                    const ids = seg.annotations.map((a) => a.id);
                    const uniqueIds = Array.from(new Set(ids));
                    const isActive =
                      activeAnnotationId !== null && uniqueIds.includes(activeAnnotationId);
                    const hasEvidence = seg.annotations.some((a) => a.kind === "evidence");

                    const firstNewBadges = uniqueIds.filter((id) => {
                      if (seenBadgeInPara.has(id)) return false;
                      seenBadgeInPara.add(id);
                      return true;
                    });

                    return (
                      <mark
                        key={`${seg.start}-${seg.end}`}
                        data-annotation-ids={uniqueIds.join(" ")}
                        onClick={() => {
                          const targetId =
                            seg.annotations.find((a) => a.kind === "evidence")?.id ??
                            seg.annotations[0]?.id;
                          if (targetId) onSelectAnnotation(targetId);
                        }}
                        title={seg.annotations.map((a) => `[${a.id}] ${a.label}`).join("\n")}
                        className={cn(
                          "bg-transparent text-inherit rounded-xs px-0.5 transition-colors cursor-pointer",
                          isActive
                            ? "bg-[var(--accent-soft)] border-b-2 border-[var(--accent)]"
                            : hasEvidence
                              ? "bg-[var(--caution-soft)]/70 border-b border-dashed border-[var(--caution)]"
                              : "border-b border-dotted border-[var(--accent-border)] hover:bg-[var(--accent-soft)]/50",
                        )}
                      >
                        {seg.text}
                        {firstNewBadges.map((id) => (
                          <sup
                            key={id}
                            className="ml-0.5 font-mono-num text-[10px] font-semibold text-[var(--accent)] select-none"
                          >
                            [{id}]
                          </sup>
                        ))}
                      </mark>
                    );
                  })}
                </p>
              );
            })}
          </div>

          {(claims.length > 0 || queries.length > 0) && (
            <div className="pt-2 border-t border-[var(--border-subtle)]">
              <button
                type="button"
                aria-expanded={showClaimsDrawer}
                onClick={() => setShowClaimsDrawer((v) => !v)}
                className="flex w-full items-center justify-between text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] cursor-pointer py-1"
              >
                <span>
                  Extracted claims ({claims.length}) &amp; search queries ({queries.length})
                </span>
                {showClaimsDrawer ? (
                  <ChevronDown className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
                )}
              </button>

              {showClaimsDrawer && (
                <div className="mt-2.5 space-y-3">
                  {claims.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-semibold text-[var(--fg-muted)]">
                        Verbatim claims asserted by the author
                      </div>
                      <ul className="space-y-1.5 list-none p-0 m-0">
                        {claims.map((cl) => (
                          <li key={cl.id}>
                            <button
                              type="button"
                              onClick={() => onSelectAnnotation(cl.id)}
                              className={cn(
                                "w-full text-left rounded-lg border p-2 text-xs transition-colors cursor-pointer",
                                activeAnnotationId === cl.id
                                  ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                                  : "border-[var(--border-subtle)] bg-[var(--bg-canvas)] hover:border-[var(--border-strong)]",
                              )}
                            >
                              <span className="font-mono-num font-semibold text-[var(--accent)] mr-1.5">
                                [{cl.id}]
                              </span>
                              <span className="text-[var(--fg-primary)]">“{cl.text}”</span>
                              <span className="font-mono-num text-[10px] text-[var(--fg-muted)] ml-2">
                                ¶{cl.span.paragraph + 1} [{cl.span.start}..{cl.span.end}]
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {queries.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-semibold text-[var(--fg-muted)]">
                        Multilingual retrieval queries
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {queries.map((q, idx) => (
                          <span
                            key={`${q.language}-${idx}`}
                            className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[11px] text-[var(--fg-secondary)]"
                          >
                            <span
                              title={languageName(q.language)}
                              className="font-mono-num uppercase text-[10px] text-[var(--fg-muted)]"
                            >
                              {q.language}
                            </span>
                            <span>{q.text}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
