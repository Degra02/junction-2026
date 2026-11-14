import { Fragment, useEffect, useMemo, useRef } from "react";
import * as Popover from "@radix-ui/react-popover";
import { ChevronRight, ExternalLink } from "lucide-react";
import type {
  Claim,
  ContextItem,
  DocumentData,
  Evidence,
  SourceProfile,
  Topic,
} from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { formatShortDate } from "../lib/format";
import { FAMILY_LABELS, TECHNIQUE_GUIDE, signalLabel } from "../lib/labels";
import { collectDocumentAnnotations, segmentParagraph } from "../lib/spans";
import { tagClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { CitationChip } from "./CitationChip";
import { Favicon } from "./ui/Favicon";

export interface DocumentReaderProps {
  readonly document: DocumentData | null | undefined;
  readonly topic: Topic | null | undefined;
  readonly claims: readonly Claim[];
  readonly evidence: readonly Evidence[];
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly activeAnnotationId: string | null;
  readonly onSelectAnnotation: (id: string) => void;
  /** The paragraph at the reading line: its flagged passages are filled in. */
  readonly focusParagraph?: number | null;
  /** Called as the reader scrolls, with the paragraph crossing the reading line (null above the text). */
  readonly onFocusParagraph?: (paragraph: number | null) => void;
}

/**
 * The reading line: a band between 38% and 48% of the viewport height. The topmost paragraph
 * inside it is the one being read.
 */
const READING_BAND = "-38% 0px -52% 0px";
const READING_LINE = 0.48;

export function DocumentReader({
  document,
  topic,
  claims,
  evidence,
  context,
  sources,
  activeAnnotationId,
  onSelectAnnotation,
  focusParagraph = null,
  onFocusParagraph,
}: Readonly<DocumentReaderProps>) {
  const containerRef = useRef<HTMLElement | null>(null);

  const annotations = useMemo(
    () => collectDocumentAnnotations(claims, evidence),
    [claims, evidence],
  );

  const claimMap = useMemo(() => new Map(claims.map((c) => [c.id, c])), [claims]);
  const evidenceMap = useMemo(() => new Map(evidence.map((e) => [e.id, e])), [evidence]);

  // Scrolling to a passage is the page's job (it knows which paragraph was asked for); the
  // reader only flashes the marks of the selected item.
  useEffect(() => {
    if (!activeAnnotationId || !containerRef.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const targets = containerRef.current.querySelectorAll<HTMLElement>(
      `[data-annotation-ids~="${CSS.escape(activeAnnotationId)}"]`,
    );
    for (const target of targets) {
      target.animate(
        [{ boxShadow: "0 0 0 4px var(--mark-strong)" }, { boxShadow: "0 0 0 0 transparent" }],
        { duration: 900, easing: "ease-out" },
      );
    }
  }, [activeAnnotationId]);

  const paragraphCount = document?.paragraphs.length ?? 0;
  useEffect(() => {
    const root = containerRef.current;
    if (!root || !onFocusParagraph || paragraphCount === 0) return;
    const paragraphs = Array.from(root.querySelectorAll<HTMLElement>("[data-paragraph]"));
    const inBand = new Set<number>();

    const band = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const index = Number((entry.target as HTMLElement).dataset.paragraph);
          if (entry.isIntersecting) inBand.add(index);
          else inBand.delete(index);
        }
        if (inBand.size > 0) {
          onFocusParagraph(Math.min(...inBand));
          return;
        }
        // Between two paragraphs the last one stays; above the first one nothing is being read.
        const first = paragraphs[0]?.getBoundingClientRect().top ?? 0;
        if (first > window.innerHeight * READING_LINE) onFocusParagraph(null);
      },
      { rootMargin: READING_BAND },
    );
    for (const p of paragraphs) band.observe(p);

    const whole = new IntersectionObserver(([entry]) => {
      if (entry && !entry.isIntersecting) onFocusParagraph(null);
    });
    whole.observe(root);

    return () => {
      band.disconnect();
      whole.disconnect();
      onFocusParagraph(null);
    };
  }, [paragraphCount, onFocusParagraph]);

  if (!document || document.paragraphs.length === 0) {
    return (
      <div className="editorial-card rounded-xl p-4 sm:p-5 text-[13px] text-[var(--fg-muted)]">
        No text extracted.
      </div>
    );
  }

  const pubDate = formatShortDate(document.published_at);
  const outlet = document.outlet ? cleanDomain(document.outlet) || document.outlet : null;
  const topicMeta = [topic?.place, topic?.date].filter(Boolean).join(" · ");

  return (
    <section
      ref={containerRef}
      aria-labelledby="reader-heading"
      className="editorial-card rounded-xl p-4 sm:p-8 min-w-0"
    >
      <header className="max-w-[calc(68ch+2.75rem)] sm:pl-11 space-y-2">
        {/* The page title above is the document's title: the reader does not repeat it. */}
        <h2 id="reader-heading" className="text-sm font-medium text-[var(--fg-primary)]">
          {outlet ? "Article" : "Text"}
        </h2>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--fg-secondary)]">
          {outlet && (
            <span className="inline-flex items-center gap-1.5">
              <Favicon domain={outlet} size={14} />
              <span className="font-mono-num">{outlet}</span>
            </span>
          )}
          {document.author && <span>{document.author}</span>}
          {pubDate && <span className="font-mono-num text-[var(--fg-muted)]">{pubDate}</span>}
          {document.url && (
            <a
              href={document.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline"
            >
              Original
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          )}
          <span className="ml-auto inline-flex items-center gap-3 text-[var(--fg-muted)]">
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden="true" className="h-2.5 w-3.5 rounded-[2px] bg-[var(--mark-strong)]" />
              Evidence
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="w-3.5 border-b-[1.5px] border-dotted border-[var(--accent)]"
              />
              Claim
            </span>
          </span>
        </div>
      </header>

      {topic && (
        <details className="group mt-4 max-w-[calc(68ch+2.75rem)] sm:ml-11 border-y border-[var(--border-subtle)] py-2 text-xs">
          <summary className="flex items-center gap-2 cursor-pointer list-none [&::-webkit-details-marker]:hidden text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]">
            <ChevronRight
              className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)] transition-transform group-open:rotate-90"
              aria-hidden="true"
            />
            <span className="font-medium text-[var(--fg-primary)]">Event</span>
            {topicMeta && <span className="font-mono-num text-[var(--fg-muted)] shrink-0">{topicMeta}</span>}
            <span className="truncate text-[var(--fg-muted)] group-open:hidden">{topic.summary}</span>
          </summary>
          <div className="pl-5.5 pt-2 pb-1 space-y-2">
            <p className="text-[13px] leading-relaxed text-[var(--fg-secondary)]">{topic.summary}</p>
            {topic.entities.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {topic.entities.map((entity) => (
                  <span key={entity} className={tagClass("neutral")}>
                    {entity}
                  </span>
                ))}
              </div>
            )}
          </div>
        </details>
      )}

      <div className="mt-6 grid grid-cols-[1.75rem_minmax(0,68ch)] sm:grid-cols-[2rem_minmax(0,68ch)] gap-x-2 sm:gap-x-3 gap-y-5">
        {document.paragraphs.map((para, pIdx) => {
          const segments = segmentParagraph(para, pIdx, annotations);
          const isFocus = pIdx === focusParagraph;

          return (
            <Fragment key={pIdx}>
              <span
                aria-hidden="true"
                className={cn(
                  "font-mono-num text-[11px] leading-[1.7] pt-[0.3em] text-right select-none transition-colors",
                  isFocus ? "text-[var(--fg-primary)]" : "text-[var(--fg-muted)]",
                )}
              >
                {pIdx + 1}
              </span>
              <p data-paragraph={pIdx} className="font-serif text-[17px] leading-[1.7] text-[var(--fg-primary)]">
                {segments.map((seg) => {
                  if (seg.annotations.length === 0) {
                    return <span key={`${seg.start}-${seg.end}`}>{seg.text}</span>;
                  }

                  const uniqueIds = Array.from(new Set(seg.annotations.map((a) => a.id)));
                  const isActive =
                    activeAnnotationId !== null && uniqueIds.includes(activeAnnotationId);
                  const hasEvidence = seg.annotations.some((a) => a.kind === "evidence");
                  const hasClaim = seg.annotations.some((a) => a.kind === "claim");

                  const matchedClaims = uniqueIds
                    .map((id) => claimMap.get(id))
                    .filter((c): c is Claim => c !== undefined);
                  const matchedEvidence = uniqueIds
                    .map((id) => evidenceMap.get(id))
                    .filter((e): e is Evidence => e !== undefined);

                  return (
                    <Popover.Root key={`${seg.start}-${seg.end}`}>
                      <Popover.Trigger asChild>
                        <mark
                          data-annotation-ids={uniqueIds.join(" ")}
                          data-focus={hasEvidence && isFocus && !isActive ? "true" : undefined}
                          onClick={() => {
                            if (uniqueIds[0]) onSelectAnnotation(uniqueIds[0]);
                          }}
                          className={cn(
                            "text-inherit rounded-[2px] box-decoration-clone cursor-pointer transition-colors underline-offset-[5px]",
                            hasEvidence && "mark-sweep",
                            hasEvidence
                              ? isActive
                                ? "bg-[var(--mark-strong)]"
                                : "bg-[var(--mark)] hover:bg-[var(--mark-strong)]"
                              : "bg-transparent hover:bg-[var(--bg-hover)]",
                            isActive
                              ? "underline decoration-2 decoration-[color:var(--caution)]"
                              : hasClaim && "underline decoration-dotted decoration-[1.5px] decoration-[color:var(--accent)]",
                          )}
                        >
                          {seg.text}
                        </mark>
                      </Popover.Trigger>

                      <Popover.Portal>
                        <Popover.Content
                          side="top"
                          align="center"
                          sideOffset={8}
                          collisionPadding={16}
                          className="z-50 glass-popover rounded-xl w-80 sm:w-96 outline-none divide-y divide-[var(--border-subtle)]"
                        >
                          <div className="px-3 py-2 font-mono-num text-[11px] text-[var(--fg-muted)]">
                            ¶ {pIdx + 1}
                          </div>

                          {matchedClaims.map((cl) => (
                            <div key={cl.id} className="px-3 py-2.5 space-y-1">
                              <div className="text-xs font-medium text-[var(--accent)]">Claim</div>
                              <p className="text-[13px] text-[var(--fg-primary)] leading-snug">
                                “{cl.text}”
                              </p>
                            </div>
                          ))}

                          {matchedEvidence.map((ev) => (
                            <div key={ev.id} className="px-3 py-2.5 space-y-1.5">
                              <div className="flex items-baseline justify-between gap-2">
                                <span className="text-[13px] font-medium text-[var(--fg-primary)]">
                                  {signalLabel(ev.signal)}
                                </span>
                                <span className="text-xs text-[var(--fg-muted)]">
                                  {FAMILY_LABELS[ev.family].name}
                                </span>
                              </div>
                              <p className="text-xs text-[var(--fg-secondary)] leading-relaxed">
                                {ev.detail}
                              </p>
                              {ev.family === "techniques" && TECHNIQUE_GUIDE[ev.signal] && (
                                <p className="text-xs text-[var(--fg-secondary)] leading-relaxed">
                                  <span className="font-medium text-[var(--fg-primary)]">Spot it: </span>
                                  {TECHNIQUE_GUIDE[ev.signal]?.spot}
                                </p>
                              )}
                              <CitationChip
                                evidence={ev}
                                document={document}
                                context={context}
                                sources={sources}
                              />
                            </div>
                          ))}
                        </Popover.Content>
                      </Popover.Portal>
                    </Popover.Root>
                  );
                })}
              </p>
            </Fragment>
          );
        })}
      </div>

      {document.tracking_ids.length > 0 && (
        <div className="mt-6 pt-4 sm:ml-11 border-t border-[var(--border-subtle)] flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-[var(--fg-muted)] mr-1">Trackers</span>
          {document.tracking_ids.map((tid) => (
            <code key={tid} className={tagClass("neutral", { mono: true })}>
              {tid}
            </code>
          ))}
        </div>
      )}
    </section>
  );
}
