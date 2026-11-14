import { useState } from "react";
import * as HoverCard from "@radix-ui/react-hover-card";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Globe,
  ShieldAlert,
} from "lucide-react";
import type {
  ContextItem,
  DocumentData,
  Evidence,
  SourceProfile,
} from "../lib/contracts";
import { resolveCitationChip } from "../lib/evidence";
import { cn } from "../lib/utils";

export interface CitationChipProps {
  readonly evidence: Evidence;
  readonly document: DocumentData | null | undefined;
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly active?: boolean;
  readonly onInspect?: (evidenceId: string) => void;
}

/**
 * Perplexity-style publisher/signal inline chip with a Liquid Glass HoverCard
 * supporting 1/N multi-source pagination, outlet badges, domain age, and verbatim quotes.
 */
export function CitationChip({
  evidence,
  document,
  context,
  sources,
  active = false,
  onInspect,
}: Readonly<CitationChipProps>) {
  const [page, setPage] = useState<number>(0);
  const meta = resolveCitationChip(evidence, document, context, sources);
  const total = meta.sources.length;
  const safeIndex = total > 0 ? Math.min(page, total - 1) : 0;
  const current = meta.sources[safeIndex] ?? null;

  return (
    <HoverCard.Root openDelay={120} closeDelay={140}>
      <HoverCard.Trigger asChild>
        <button
          type="button"
          onClick={() => onInspect?.(evidence.id)}
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border transition-all cursor-pointer align-baseline",
            active
              ? "bg-[var(--accent)] text-white border-[var(--accent)] shadow-xs"
              : meta.tone === "teal"
                ? "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)] hover:opacity-90"
                : meta.tone === "caution"
                  ? "bg-[var(--caution-soft)] text-[var(--caution)] border-[var(--caution-border)] hover:opacity-90"
                  : "bg-[var(--accent-soft)] text-[var(--accent)] border-[var(--accent-border)] hover:opacity-90",
          )}
        >
          <span className="truncate max-w-[150px]">{meta.primaryLabel}</span>
          {meta.extraCount > 0 && (
            <span className="font-mono-num text-[10px] opacity-80">+{meta.extraCount}</span>
          )}
        </button>
      </HoverCard.Trigger>

      <HoverCard.Portal>
        <HoverCard.Content
          side="top"
          align="center"
          sideOffset={8}
          collisionPadding={16}
          className="z-50 glass-popover rounded-2xl p-3.5 w-80 sm:w-96 space-y-2.5 text-left outline-none"
        >
          {/* Header: Signal Family + 1/N Pagination */}
          <div className="flex items-center justify-between gap-2 pb-2 border-b border-[var(--border-subtle)]/80">
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
                {meta.familyLabel}
              </div>
              <div className="text-xs font-bold text-[var(--fg-primary)] truncate">
                {meta.signalLabel}
              </div>
            </div>

            {total > 1 && (
              <div className="inline-flex items-center gap-1 shrink-0 bg-[var(--bg-subtle)]/80 rounded-full px-1.5 py-0.5">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPage((p) => (p - 1 + total) % total);
                  }}
                  aria-label="Previous source"
                  className="p-0.5 text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] cursor-pointer"
                >
                  <ChevronLeft className="h-3 w-3" aria-hidden="true" />
                </button>
                <span className="font-mono-num text-[10px] text-[var(--fg-secondary)] px-0.5">
                  {safeIndex + 1}/{total}
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPage((p) => (p + 1) % total);
                  }}
                  aria-label="Next source"
                  className="p-0.5 text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] cursor-pointer"
                >
                  <ChevronRight className="h-3 w-3" aria-hidden="true" />
                </button>
              </div>
            )}
          </div>

          {/* Evidence Plain-Language Detail */}
          <p className="text-xs text-[var(--fg-secondary)] leading-relaxed m-0">
            {meta.detail}
          </p>

          {/* Current Source Card */}
          {current && (
            <div className="rounded-xl bg-[var(--bg-subtle)]/75 border border-[var(--border-subtle)] p-2.5 space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-1.5">
                <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--fg-primary)] min-w-0">
                  {current.kind === "document" ? (
                    <FileText className="h-3.5 w-3.5 text-[var(--accent)] shrink-0" aria-hidden="true" />
                  ) : (
                    <Globe className="h-3.5 w-3.5 text-[var(--accent)] shrink-0" aria-hidden="true" />
                  )}
                  <span className="truncate">{current.domain}</span>
                </div>

                <div className="flex flex-wrap items-center gap-1">
                  {current.outletTypeLabel && (
                    <span
                      className={cn(
                        "px-1.5 py-0.5 rounded-md text-[10px] font-medium border",
                        current.outletTypeTone === "teal"
                          ? "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)]"
                          : current.outletTypeTone === "caution"
                            ? "bg-[var(--caution-soft)] text-[var(--caution)] border-[var(--caution-border)]"
                            : "bg-[var(--bg-surface)] text-[var(--fg-secondary)] border-[var(--border-subtle)]",
                      )}
                    >
                      {current.outletTypeLabel}
                    </span>
                  )}

                  {current.domainAge && (
                    <span className="px-1.5 py-0.5 rounded-md bg-[var(--bg-surface)] border border-[var(--border-subtle)] font-mono-num text-[10px] text-[var(--fg-muted)]">
                      {current.domainAge}
                    </span>
                  )}
                </div>
              </div>

              {current.knownNetworkLabel && (
                <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[var(--caution-soft)] border border-[var(--caution-border)] text-[10px] font-semibold text-[var(--caution)]">
                  <ShieldAlert className="h-3 w-3" aria-hidden="true" />
                  <span>{current.knownNetworkLabel}</span>
                </div>
              )}

              {current.factCheckRating && (
                <div className="text-[11px] font-semibold text-[var(--caution)]">
                  {current.factCheckPublisher ? `${current.factCheckPublisher} rating: ` : "Fact-check rating: "}
                  <span className="underline decoration-dotted">{current.factCheckRating}</span>
                </div>
              )}

              <div className="text-[11px] font-medium text-[var(--fg-primary)] line-clamp-1">
                {current.title}
              </div>

              {current.quote && (
                <blockquote className="m-0 pl-2.5 border-l-2 border-[var(--accent)] text-[11px] italic text-[var(--fg-secondary)] line-clamp-3 leading-relaxed">
                  “{current.quote}”
                </blockquote>
              )}

              <div className="pt-1 flex items-center justify-between gap-2">
                {onInspect && (
                  <button
                    type="button"
                    onClick={() => onInspect(evidence.id)}
                    className="text-[11px] font-semibold text-[var(--accent)] hover:underline cursor-pointer"
                  >
                    {current.kind === "document" ? "Highlight in text →" : "Open in evidence inspector →"}
                  </button>
                )}

                {current.url && (
                  <a
                    href={current.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--fg-secondary)] hover:text-[var(--accent)] ml-auto"
                  >
                    <span>Open source</span>
                    <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  </a>
                )}
              </div>
            </div>
          )}
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
}
