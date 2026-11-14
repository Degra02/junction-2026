import { useEffect, useMemo, useRef } from "react";
import * as Popover from "@radix-ui/react-popover";
import { ExternalLink, FileText, Tag } from "lucide-react";
import type {
  Claim,
  ContextItem,
  DocumentData,
  Evidence,
  SourceProfile,
  Topic,
} from "../lib/contracts";
import { formatShortDate } from "../lib/format";
import { FAMILY_LABELS, signalLabel } from "../lib/labels";
import { collectDocumentAnnotations, segmentParagraph } from "../lib/spans";
import { cn } from "../lib/utils";
import { CitationChip } from "./CitationChip";

export interface DocumentReaderProps {
  readonly document: DocumentData | null | undefined;
  readonly topic: Topic | null | undefined;
  readonly claims: readonly Claim[];
  readonly evidence: readonly Evidence[];
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly activeAnnotationId: string | null;
  readonly onSelectAnnotation: (id: string) => void;
}

export function DocumentReader({
  document,
  topic,
  claims,
  evidence,
  context,
  sources,
  activeAnnotationId,
  onSelectAnnotation,
}: Readonly<DocumentReaderProps>) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const annotations = useMemo(
    () => collectDocumentAnnotations(claims, evidence),
    [claims, evidence],
  );

  const claimMap = useMemo(() => new Map(claims.map((c) => [c.id, c])), [claims]);
  const evidenceMap = useMemo(() => new Map(evidence.map((e) => [e.id, e])), [evidence]);

  useEffect(() => {
    if (!activeAnnotationId || !containerRef.current) return;
    const target = containerRef.current.querySelector<HTMLElement>(
      `[data-annotation-ids~="${CSS.escape(activeAnnotationId)}"]`,
    );
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeAnnotationId]);

  if (!document || document.paragraphs.length === 0) {
    return (
      <div className="editorial-card rounded-3xl p-6 text-xs text-[var(--fg-muted)]">
        No extracted source paragraphs available for this item.
      </div>
    );
  }

  const pubDate = formatShortDate(document.published_at);

  return (
    <section
      ref={containerRef}
      aria-labelledby="reader-heading"
      className="editorial-card rounded-3xl p-5 sm:p-7 space-y-5"
    >
      {/* Header & Source Metadata */}
      <div className="flex flex-wrap items-start justify-between gap-3 pb-4 border-b border-[var(--border-subtle)]">
        <div className="space-y-1 min-w-0">
          <div className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
            <FileText className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
            <span>Annotated source text</span>
          </div>
          {document.title && (
            <h3
              id="reader-heading"
              className="text-base sm:text-lg font-bold text-[var(--fg-primary)] leading-snug m-0"
            >
              {document.title}
            </h3>
          )}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--fg-secondary)]">
            {document.outlet && <span className="font-semibold">{document.outlet}</span>}
            {document.author && <span>By {document.author}</span>}
            {pubDate && <span className="font-mono-num">{pubDate}</span>}
            {document.url && (
              <a
                href={document.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline"
              >
                <span>Original page</span>
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            )}
          </div>
        </div>

        <div className="text-xs text-[var(--fg-muted)] bg-[var(--bg-subtle)] px-3 py-1.5 rounded-full">
          Click any highlighted passage to inspect signals
        </div>
      </div>

      {/* Event Summary & Entities Pill Bar */}
      {topic && (
        <div className="rounded-2xl bg-[var(--bg-subtle)]/70 border border-[var(--border-subtle)] p-3.5 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--fg-primary)]">
            <Tag className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
            <span>Identified event</span>
            {topic.place ? ` · ${topic.place}` : ""}
            {topic.date ? ` (${topic.date})` : ""}
          </div>
          <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
            {topic.summary}
          </p>
        </div>
      )}

      {/* Clean Paragraph Stream with Floating Popover Annotations (Zero [cl1]/[s1] Bracket Soup) */}
      <div className="space-y-4 max-w-[70ch]">
        {document.paragraphs.map((para, pIdx) => {
          const segments = segmentParagraph(para, pIdx, annotations);

          return (
            <p
              key={pIdx}
              className="text-sm sm:text-[15px] leading-[1.75] text-[var(--fg-primary)] m-0"
            >
              {segments.map((seg) => {
                if (seg.annotations.length === 0) {
                  return <span key={`${seg.start}-${seg.end}`}>{seg.text}</span>;
                }

                const uniqueIds = Array.from(new Set(seg.annotations.map((a) => a.id)));
                const isActive =
                  activeAnnotationId !== null && uniqueIds.includes(activeAnnotationId);
                const hasEvidence = seg.annotations.some((a) => a.kind === "evidence");

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
                        onClick={() => {
                          if (uniqueIds[0]) onSelectAnnotation(uniqueIds[0]);
                        }}
                        className={cn(
                          "rounded-md px-1 py-0.5 transition-all cursor-pointer text-inherit border-b-2",
                          isActive
                            ? "bg-[var(--accent-soft)] border-[var(--accent)] ring-2 ring-[var(--accent-border)]"
                            : hasEvidence
                              ? "bg-[var(--accent-soft)]/70 border-[var(--accent)]/60 hover:bg-[var(--accent-soft)]"
                              : "bg-[var(--teal-soft)]/70 border-[var(--teal)]/60 hover:bg-[var(--teal-soft)]",
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
                        className="z-50 glass-popover rounded-2xl p-4 w-80 sm:w-96 space-y-3 outline-none"
                      >
                        <div className="text-[11px] font-mono-num text-[var(--fg-muted)]">
                          Paragraph {pIdx + 1} · Verbatim span
                        </div>

                        {matchedClaims.map((cl) => (
                          <div
                            key={cl.id}
                            className="rounded-xl bg-[var(--teal-soft)]/60 border border-[var(--teal-border)] p-2.5 space-y-1"
                          >
                            <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--teal)]">
                              Extracted assertion checked across outlets
                            </div>
                            <p className="text-xs text-[var(--fg-primary)] m-0 leading-snug">
                              “{cl.text}”
                            </p>
                          </div>
                        ))}

                        {matchedEvidence.map((ev) => (
                          <div
                            key={ev.id}
                            className="rounded-xl bg-[var(--bg-subtle)]/80 border border-[var(--border-subtle)] p-2.5 space-y-2"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-bold text-[var(--fg-primary)]">
                                {signalLabel(ev.signal)}
                              </span>
                              <span className="text-[10px] text-[var(--fg-muted)]">
                                {FAMILY_LABELS[ev.family].name}
                              </span>
                            </div>
                            <p className="text-xs text-[var(--fg-secondary)] m-0 leading-relaxed">
                              {ev.detail}
                            </p>
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
          );
        })}
      </div>

      {document.tracking_ids.length > 0 && (
        <div className="pt-4 border-t border-[var(--border-subtle)] flex flex-wrap items-center gap-2 text-xs">
          <span className="text-[var(--fg-muted)]">Embedded analytics / ad tags:</span>
          {document.tracking_ids.map((tid) => (
            <code
              key={tid}
              className="px-2 py-0.5 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-subtle)] font-mono-num text-[11px] text-[var(--fg-secondary)]"
            >
              {tid}
            </code>
          ))}
        </div>
      )}
    </section>
  );
}
