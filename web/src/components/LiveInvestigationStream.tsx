import { AnimatePresence, motion } from "motion/react";
import {
  CheckCircle2,
  FileText,
  Globe,
  Layers,
  Loader2,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { Analysis } from "../lib/contracts";
import { cleanDomain, describeLiveActivity } from "../lib/evidence";
import { formatDurationMs } from "../lib/format";
import {
  ADAPTER_LABELS,
  ALL_STAGES,
  LANGUAGE_SUPPORT_LABELS,
  STAGE_LABELS,
  languageName,
} from "../lib/labels";
import { GENTLE_SPRING, SPATIAL_SPRING } from "../lib/motion";
import { cn } from "../lib/utils";

export interface LiveInvestigationStreamProps {
  readonly analysis: Analysis;
}

export function LiveInvestigationStream({ analysis }: Readonly<LiveInvestigationStreamProps>) {
  const activity = describeLiveActivity(analysis);
  const stepMap = new Map(analysis.steps.map((s) => [s.name, s]));

  const inStoryCount = analysis.context.filter((c) => c.in_story === true).length;
  const storyEvaluated = analysis.context.some(
    (c) => c.in_story !== null && c.in_story !== undefined,
  );

  return (
    <motion.section
      aria-label="Live investigation progress"
      aria-live="polite"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={GENTLE_SPRING}
      className="max-w-[820px] mx-auto glass-panel rounded-3xl p-5 sm:p-7 space-y-6"
    >
      {/* Top Hero Live Sentence + Progress Bar */}
      <div className="space-y-3.5">
        <div className="flex items-start gap-3.5">
          <div className="mt-1 h-8 w-8 rounded-2xl bg-[var(--accent-soft)] border border-[var(--accent-border)] text-[var(--accent)] inline-flex items-center justify-center shrink-0">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          </div>

          <div className="space-y-1 min-w-0 flex-1">
            <AnimatePresence mode="wait">
              <motion.h2
                key={activity.headline}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18 }}
                className="text-base sm:text-lg font-bold tracking-tight text-[var(--fg-primary)] leading-snug m-0"
              >
                {activity.headline}
              </motion.h2>
            </AnimatePresence>
            <p className="text-xs sm:text-sm text-[var(--fg-secondary)] m-0">
              {activity.subline}
            </p>
          </div>

          <span className="font-mono-num text-xs font-semibold text-[var(--accent)] bg-[var(--accent-soft)] px-2.5 py-1 rounded-full shrink-0">
            {activity.completedCount}/{activity.totalCount}
          </span>
        </div>

        <div className="h-1.5 w-full rounded-full bg-[var(--bg-subtle)] overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-[var(--accent)]"
            initial={{ width: "6%" }}
            animate={{ width: `${Math.round(activity.progressFraction * 100)}%` }}
            transition={SPATIAL_SPRING}
          />
        </div>
      </div>

      {/* Streaming Stage Artifacts — appear dynamically as stages complete */}
      <div className="space-y-4">
        {/* 1. Extracted Document Preview */}
        <AnimatePresence>
          {analysis.document && (
            <motion.div
              key="stage-extract"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={SPATIAL_SPRING}
              className="editorial-card rounded-2xl p-4 space-y-2"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="inline-flex items-center gap-2 font-semibold text-[var(--fg-primary)]">
                  <FileText className="h-3.5 w-3.5 text-[var(--teal)]" aria-hidden="true" />
                  <span>
                    Read content
                    {analysis.document.outlet ? ` from ${analysis.document.outlet}` : ""}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {analysis.language && (
                    <span className="px-2 py-0.5 rounded-full bg-[var(--bg-subtle)] text-[11px] font-medium text-[var(--fg-secondary)]">
                      {languageName(analysis.language.code)} ·{" "}
                      {LANGUAGE_SUPPORT_LABELS[analysis.language.support].badge}
                    </span>
                  )}
                  <span className="font-mono-num text-[11px] text-[var(--fg-muted)]">
                    {analysis.document.paragraphs.length} ¶
                  </span>
                </div>
              </div>

              {analysis.document.title && (
                <div className="text-sm font-semibold text-[var(--fg-primary)] leading-snug">
                  {analysis.document.title}
                </div>
              )}

              {analysis.document.paragraphs[0] && (
                <p className="text-xs text-[var(--fg-secondary)] line-clamp-2 leading-relaxed m-0">
                  {analysis.document.paragraphs[0]}
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* 2. Search Queries & Verbatim Claims */}
        <AnimatePresence>
          {(analysis.queries.length > 0 || analysis.claims.length > 0) && (
            <motion.div
              key="stage-understand"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={SPATIAL_SPRING}
              className="editorial-card rounded-2xl p-4 space-y-3"
            >
              <div className="flex items-center justify-between gap-2 text-xs">
                <div className="inline-flex items-center gap-2 font-semibold text-[var(--fg-primary)]">
                  <Search className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
                  <span>
                    Search queries &amp; {analysis.claims.length}{" "}
                    {analysis.claims.length === 1 ? "assertion" : "assertions"}
                  </span>
                </div>
                {analysis.topic?.summary && (
                  <span className="text-[11px] text-[var(--fg-muted)] truncate max-w-[320px]">
                    {analysis.topic.summary}
                  </span>
                )}
              </div>

              {analysis.queries.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {analysis.queries.map((q, idx) => (
                    <span
                      key={`${q.language}-${idx}`}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-xs text-[var(--fg-primary)]"
                    >
                      <Search className="h-3 w-3 text-[var(--accent)]" aria-hidden="true" />
                      <span className="truncate max-w-[240px]">{q.text}</span>
                      <span className="font-mono-num text-[10px] uppercase text-[var(--fg-muted)]">
                        {q.language}
                      </span>
                    </span>
                  ))}
                </div>
              )}

              {analysis.claims.length > 0 && (
                <div className="space-y-1 pt-1 border-t border-[var(--border-subtle)]/70">
                  {analysis.claims.slice(0, 3).map((cl) => (
                    <div
                      key={cl.id}
                      className="text-xs text-[var(--fg-secondary)] flex items-start gap-2 leading-snug"
                    >
                      <span className="text-[var(--accent)] font-bold shrink-0">•</span>
                      <span className="line-clamp-1">“{cl.text}”</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* 3. Visited Websites, News Feeds & Fact-Checks */}
        <AnimatePresence>
          {analysis.context.length > 0 && (
            <motion.div
              key="stage-retrieve"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={SPATIAL_SPRING}
              className="editorial-card rounded-2xl p-4 space-y-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="inline-flex items-center gap-2 font-semibold text-[var(--fg-primary)]">
                  <Globe className="h-3.5 w-3.5 text-[var(--teal)]" aria-hidden="true" />
                  <span>
                    Retrieved {analysis.context.length}{" "}
                    {analysis.context.length === 1 ? "external source" : "external sources"}
                  </span>
                </div>

                {storyEvaluated && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--teal-soft)] border border-[var(--teal-border)] text-[11px] font-medium text-[var(--teal)]">
                    <Layers className="h-3 w-3" aria-hidden="true" />
                    <span>{inStoryCount} matched exact event</span>
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-[240px] overflow-y-auto pr-1">
                {analysis.context.slice(0, 8).map((item) => {
                  const dom = cleanDomain(item.outlet ?? item.url) || "web source";
                  const adapter = ADAPTER_LABELS[item.retrieved_by] ?? item.retrieved_by;
                  return (
                    <div
                      key={item.id}
                      className={cn(
                        "rounded-xl border p-2.5 space-y-1 transition-colors",
                        item.fact_check
                          ? "bg-[var(--caution-soft)]/50 border-[var(--caution-border)]"
                          : "bg-[var(--bg-canvas)] border-[var(--border-subtle)]",
                      )}
                    >
                      <div className="flex items-center justify-between gap-1.5 text-[11px]">
                        <span className="font-semibold text-[var(--fg-primary)] truncate">
                          {dom}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] text-[10px] text-[var(--fg-muted)] shrink-0">
                          {adapter}
                        </span>
                      </div>

                      {item.fact_check ? (
                        <div className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--caution)]">
                          <ShieldCheck className="h-3 w-3 shrink-0" aria-hidden="true" />
                          <span className="truncate">
                            Fact-check rated: {item.fact_check.rating}
                          </span>
                        </div>
                      ) : (
                        <div className="text-xs font-medium text-[var(--fg-primary)] line-clamp-1">
                          {item.title || dom}
                        </div>
                      )}

                      {item.text && (
                        <p className="text-[11px] text-[var(--fg-muted)] line-clamp-1 m-0">
                          {item.text}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Compact Stage Strip Footer */}
      <div className="pt-3 border-t border-[var(--border-subtle)]/80 flex flex-wrap items-center gap-1.5">
        {ALL_STAGES.map((stageName) => {
          const st = stepMap.get(stageName);
          const state = st?.state ?? "pending";
          const shortLabel = STAGE_LABELS[stageName].label.split(" ")[0] ?? stageName;

          return (
            <div
              key={stageName}
              title={STAGE_LABELS[stageName].label}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border transition-colors",
                state === "running"
                  ? "bg-[var(--accent-soft)] border-[var(--accent-border)] text-[var(--accent)] font-semibold"
                  : state === "done"
                    ? "bg-[var(--bg-surface)] border-[var(--border-subtle)] text-[var(--fg-secondary)]"
                    : "bg-transparent border-transparent text-[var(--fg-muted)]/70",
              )}
            >
              {state === "done" ? (
                <CheckCircle2 className="h-3 w-3 text-[var(--teal)]" aria-hidden="true" />
              ) : state === "running" ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-[var(--border-strong)]" />
              )}
              <span>{shortLabel}</span>
              {st?.duration_ms != null && state === "done" && (
                <span className="font-mono-num text-[10px] text-[var(--fg-muted)]">
                  {formatDurationMs(st.duration_ms)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </motion.section>
  );
}
