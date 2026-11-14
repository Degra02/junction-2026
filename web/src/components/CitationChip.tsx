import { useState } from "react";
import * as HoverCard from "@radix-ui/react-hover-card";
import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import type { ContextItem, DocumentData, Evidence, SourceProfile } from "../lib/contracts";
import { resolveCitationChip } from "../lib/evidence";
import { buttonClass, tagClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { Favicon } from "./ui/Favicon";

export interface CitationChipProps {
  readonly evidence: Evidence;
  readonly document: DocumentData | null | undefined;
  readonly context: readonly ContextItem[];
  readonly sources: readonly SourceProfile[];
  readonly active?: boolean;
  readonly onInspect?: (evidenceId: string) => void;
}

/** Inline source chip; hovering shows the signal and its sources one at a time. */
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
  const lead = meta.sources[0] ?? null;
  const leadDomain = lead && lead.kind !== "document" ? lead.domain : null;

  return (
    <HoverCard.Root openDelay={120} closeDelay={140}>
      <HoverCard.Trigger asChild>
        <button
          type="button"
          onClick={() => onInspect?.(evidence.id)}
          className={cn(
            "inline-flex items-center gap-1.5 h-6 px-2 rounded-md border text-xs transition-colors cursor-pointer align-middle",
            active
              ? "bg-[var(--accent-soft)] border-[var(--accent-border)] text-[var(--accent)]"
              : "bg-[var(--bg-surface)] border-[var(--border-subtle)] text-[var(--fg-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--fg-primary)]",
          )}
        >
          {leadDomain && <Favicon domain={leadDomain} size={12} />}
          <span className="truncate max-w-[160px]">{meta.primaryLabel}</span>
          {meta.extraCount > 0 && (
            <span className="font-mono-num text-[11px] text-[var(--fg-muted)]">+{meta.extraCount}</span>
          )}
        </button>
      </HoverCard.Trigger>

      <HoverCard.Portal>
        <HoverCard.Content
          side="top"
          align="center"
          sideOffset={8}
          collisionPadding={16}
          className="z-50 glass-popover rounded-xl p-3 w-80 space-y-2.5 text-left outline-none"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-[var(--fg-primary)] truncate">{meta.signalLabel}</div>
              <div className="text-xs text-[var(--fg-muted)] truncate">{meta.familyLabel}</div>
            </div>

            {total > 1 && (
              <div className="inline-flex items-center shrink-0">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPage((p) => (p - 1 + total) % total);
                  }}
                  aria-label="Previous source"
                  className={buttonClass("ghost", "sm", "h-6 w-6 px-0")}
                >
                  <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
                <span className="font-mono-num text-[11px] text-[var(--fg-muted)]">
                  {safeIndex + 1}/{total}
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPage((p) => (p + 1) % total);
                  }}
                  aria-label="Next source"
                  className={buttonClass("ghost", "sm", "h-6 w-6 px-0")}
                >
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>
            )}
          </div>

          {meta.detail && <p className="text-xs leading-relaxed text-[var(--fg-secondary)]">{meta.detail}</p>}

          {current && (
            <div className="pt-2.5 border-t border-[var(--border-subtle)] space-y-2">
              <div className="flex items-center gap-1.5 min-w-0">
                {current.kind !== "document" && <Favicon domain={current.domain} size={14} />}
                <span className="font-mono-num text-xs text-[var(--fg-primary)] truncate">
                  {current.kind === "document" ? "This article" : current.domain}
                </span>
                {current.domainAge && (
                  <span className="font-mono-num text-[11px] text-[var(--fg-muted)] shrink-0">{current.domainAge}</span>
                )}
                {current.url && (
                  <a
                    href={current.url}
                    target="_blank"
                    rel="noreferrer"
                    aria-label="Open source"
                    className="ml-auto shrink-0 text-[var(--fg-muted)] hover:text-[var(--accent)]"
                  >
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                )}
              </div>

              {current.title && (
                <div className="text-[13px] text-[var(--fg-primary)] line-clamp-2">{current.title}</div>
              )}

              {(current.outletTypeLabel || current.knownNetworkLabel || current.factCheckRating) && (
                <div className="flex flex-wrap items-center gap-1">
                  {current.outletTypeLabel && (
                    <span className={tagClass(current.outletTypeTone ?? "neutral")}>{current.outletTypeLabel}</span>
                  )}
                  {current.knownNetworkLabel && (
                    <span className={tagClass("caution")}>{current.knownNetworkLabel}</span>
                  )}
                  {current.factCheckRating && (
                    <span className={tagClass("caution")}>
                      {current.factCheckPublisher ? `${current.factCheckPublisher}: ` : ""}
                      {current.factCheckRating}
                    </span>
                  )}
                </div>
              )}

              {current.quote && (
                <blockquote className="font-serif text-[13px] leading-relaxed text-[var(--fg-primary)] line-clamp-4">
                  <mark className="bg-[var(--mark)] text-inherit rounded-[2px] px-0.5 box-decoration-clone">
                    {current.quote}
                  </mark>
                </blockquote>
              )}

              {onInspect && (
                <button
                  type="button"
                  onClick={() => onInspect(evidence.id)}
                  className={buttonClass("ghost", "sm", "-ml-2.5")}
                >
                  {current.kind === "document" ? "Show in text →" : "Inspect →"}
                </button>
              )}
            </div>
          )}
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
}
