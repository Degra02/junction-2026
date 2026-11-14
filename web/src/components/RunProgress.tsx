import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { Check, ExternalLink, Minus, Search, X } from "lucide-react";
import type { ActivityLog } from "../hooks/useAnalysisStream";
import { rerunAnalysis } from "../lib/api";
import type { Analysis, ContextItem, Family, StageName, Step } from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { formatDurationMs, formatPct, formatShortDate } from "../lib/format";
import {
  ADAPTER_LABELS,
  ALL_STAGES,
  FAMILY_LABELS,
  LANGUAGE_SUPPORT_LABELS,
  OUTLET_TYPE_LABELS,
  STAGE_LABELS,
  languageName,
  networkLabel,
} from "../lib/labels";
import { GENTLE_SPRING } from "../lib/motion";
import { SECTION_LABEL, buttonClass, tagClass } from "../lib/ui";
import { cn } from "../lib/utils";
import { Favicon, FaviconStack } from "./ui/Favicon";

type Mode = "live" | "replay" | "log";

const SINGLE_FAMILIES: Partial<Record<Family, true>> = {
  techniques: true,
  tone: true,
  claim_support: true,
  fact_checks: true,
  source_profile: true,
};

/** Domain-like tokens in a progress note ("Reading 3 of 9 (lemonde.fr, ansa.it)"). */
const DOMAIN_RE = /\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b/gi;
/** A trailing "(site.a, site.b and 3 more)" list: shown as chips, not as text. */
const DOMAIN_LIST_RE = /\s*\([^()]*\b[a-z0-9-]+\.[a-z]{2,}\b[^()]*\)\s*$/i;

function stepOf(analysis: Analysis, name: StageName): Step {
  return (
    analysis.steps.find((s) => s.name === name) ?? {
      name,
      state: "pending",
      duration_ms: null,
      detail: null,
      error: null,
    }
  );
}

function formatElapsed(ms: number): string {
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function outletOf(item: ContextItem): string {
  return cleanDomain(item.outlet ?? item.url) || "web";
}

/** Ticks on its own so only this text re-renders while a stage runs. */
function Elapsed({ since }: Readonly<{ since: number }>) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(timer);
  }, []);
  return <>{formatElapsed(Math.max(0, now - since))}</>;
}

function StepIcon({ state }: Readonly<{ state: Step["state"] }>) {
  const base = "relative z-10 h-5 w-5 rounded-full inline-flex items-center justify-center shrink-0";
  if (state === "running") {
    return (
      <span className={cn(base, "bg-[var(--bg-surface)]")}>
        <svg viewBox="0 0 20 20" className="h-5 w-5 animate-spin" aria-hidden="true">
          <circle cx="10" cy="10" r="8" fill="none" stroke="var(--border-subtle)" strokeWidth="2" />
          <path d="M10 2a8 8 0 0 1 8 8" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </span>
    );
  }
  if (state === "done") {
    return (
      <span className={cn(base, "bg-[var(--fg-primary)] text-[var(--bg-surface)]")}>
        <Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
      </span>
    );
  }
  if (state === "failed") {
    return (
      <span className={cn(base, "bg-[var(--danger)] text-white")}>
        <X className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
      </span>
    );
  }
  if (state === "skipped") {
    return (
      <span className={cn(base, "bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[var(--fg-muted)]")}>
        <Minus className="h-3 w-3" aria-hidden="true" />
      </span>
    );
  }
  return <span className={cn(base, "bg-[var(--bg-surface)] border-[1.5px] border-[var(--border-strong)]")} />;
}

/** What a stage found, in one or two short lines. */
function StageDetail({ analysis, step, notes }: Readonly<{ analysis: Analysis; step: Step; notes: readonly string[] }>) {
  const running = step.state === "running";
  const done = step.state === "done";

  switch (step.name) {
    case "extract": {
      if (!done || !analysis.document) return null;
      const doc = analysis.document;
      const outlet = cleanDomain(doc.outlet ?? doc.url);
      const lang = analysis.language;
      return (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-[var(--fg-secondary)]">
          {outlet ? (
            <span className="inline-flex items-center gap-1.5 font-mono-num text-xs text-[var(--fg-primary)]">
              <Favicon domain={outlet} size={14} />
              {outlet}
            </span>
          ) : (
            <span>Pasted text</span>
          )}
          {lang && (
            <span>
              · {languageName(lang.code)}{" "}
              <span className="text-[var(--fg-muted)]">({LANGUAGE_SUPPORT_LABELS[lang.support].badge.toLowerCase()})</span>
            </span>
          )}
          <span className="font-mono-num text-xs text-[var(--fg-muted)]">· {doc.paragraphs.length} ¶</span>
        </div>
      );
    }
    case "understand": {
      if (!done) return null;
      return (
        <div className="space-y-2">
          {analysis.topic?.summary && (
            <p className="text-[13px] leading-snug text-[var(--fg-secondary)] line-clamp-2">
              {analysis.topic.summary}
            </p>
          )}
          {analysis.queries.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {analysis.queries.map((q, i) => (
                <span
                  key={`${q.language}-${i}`}
                  className="inline-flex items-center gap-1.5 h-6 max-w-full px-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-xs text-[var(--fg-primary)]"
                >
                  <Search className="h-3 w-3 text-[var(--fg-muted)] shrink-0" aria-hidden="true" />
                  <span className="truncate">{q.text}</span>
                  <span className="font-mono-num text-[10px] uppercase text-[var(--fg-muted)]">{q.language}</span>
                </span>
              ))}
            </div>
          )}
          <p className="text-xs text-[var(--fg-muted)]">
            {analysis.claims.length === 0
              ? "No checkable claims"
              : `${analysis.claims.length} ${analysis.claims.length === 1 ? "claim" : "claims"} to check`}
          </p>
        </div>
      );
    }
    case "retrieve": {
      if (running) {
        const domains = Array.from(new Set(notes.flatMap((n) => n.match(DOMAIN_RE) ?? []).map((d) => d.toLowerCase())));
        if (domains.length === 0) return null;
        return (
          <div className="flex flex-wrap gap-1.5">
            {domains.slice(0, 12).map((d) => (
              <span
                key={d}
                className="inline-flex items-center gap-1.5 h-6 px-1.5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] font-mono-num text-[11px] text-[var(--fg-secondary)]"
              >
                <Favicon domain={d} size={12} />
                {d}
              </span>
            ))}
          </div>
        );
      }
      if (!done) return null;
      const outlets = Array.from(new Set(analysis.context.map(outletOf)));
      return (
        <div className="flex flex-wrap items-center gap-2">
          {outlets.length > 0 && <FaviconStack domains={outlets} max={8} />}
          {step.detail && <span className="text-[13px] text-[var(--fg-secondary)]">{step.detail}</span>}
        </div>
      );
    }
    case "story": {
      if (!done) return null;
      const total = analysis.context.filter((c) => !c.fact_check).length;
      const same = analysis.context.filter((c) => c.in_story === true);
      return (
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-[var(--fg-secondary)]">
          {same.length > 0 && <FaviconStack domains={Array.from(new Set(same.map(outletOf)))} />}
          <span>
            {total === 0
              ? "No other reports to compare"
              : same.length === 0
                ? `None of ${total} reports covers the same event`
                : `${same.length} of ${total} reports cover the same event`}
          </span>
        </div>
      );
    }
    case "signals_single":
    case "signals_coordinated": {
      if (running && step.name === "signals_single" && analysis.claims.length > 0 && notes.length === 0) {
        return (
          <p className="text-[13px] text-[var(--fg-secondary)]">
            {analysis.claims.length} claims, persuasion techniques, tone
          </p>
        );
      }
      if (!done) return null;
      const single = step.name === "signals_single";
      const found = analysis.evidence.filter((e) => Boolean(SINGLE_FAMILIES[e.family]) === single);
      const families = Array.from(new Set(found.map((e) => e.family)));
      if (found.length === 0) {
        return <p className="text-[13px] text-[var(--fg-muted)]">No signals</p>;
      }
      return (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[13px] text-[var(--fg-secondary)] mr-0.5">
            {found.length} {found.length === 1 ? "signal" : "signals"}:
          </span>
          {families.map((f) => (
            <span key={f} className={tagClass(single ? "accent" : "indigo")}>
              {FAMILY_LABELS[f].name}
            </span>
          ))}
        </div>
      );
    }
    case "score": {
      if (!done || !analysis.scores) return null;
      const show = (label: string, s: (typeof analysis.scores)["single"]) => (
        <span>
          {label}{" "}
          <span className="font-mono-num text-[var(--fg-primary)]">
            {s.abstained || s.confidence == null ? "not enough evidence" : formatPct(s.confidence)}
          </span>
        </span>
      );
      return (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-[var(--fg-secondary)]">
          {show("Single actor", analysis.scores.single)}
          {show("Coordinated", analysis.scores.coordinated)}
        </div>
      );
    }
    default:
      return null;
  }
}

function LedgerRow({
  analysis,
  step,
  notes,
  startedAt,
  mode,
  last,
  maxMs,
}: Readonly<{
  analysis: Analysis;
  step: Step;
  notes: readonly string[];
  startedAt: number | null;
  mode: Mode;
  last: boolean;
  maxMs: number;
}>) {
  const meta = STAGE_LABELS[step.name];
  const running = step.state === "running";
  const pending = step.state === "pending";
  const done = step.state === "done";
  const label = running
    ? meta.active
    : step.name === "extract" && analysis.input.kind === "text"
      ? "Read the text"
      : meta.label;
  // The latest note is the headline while running; earlier ones stay as a short trail.
  const current = running ? notes[notes.length - 1] : undefined;
  const trail = running ? notes.slice(-4, -1) : [];

  return (
    <li className="relative flex gap-3.5 pb-5 last:pb-0">
      {!last && (
        <span
          aria-hidden="true"
          className={cn(
            "absolute left-[9.5px] top-6 bottom-0.5 w-px",
            done ? "bg-[var(--fg-muted)]/50" : "bg-[var(--border-subtle)]",
          )}
        />
      )}
      <StepIcon state={step.state} />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex items-baseline justify-between gap-3 min-h-5">
          <span
            className={cn(
              "text-sm",
              running && "shimmer font-medium text-[var(--fg-primary)]",
              done && "text-[var(--fg-primary)]",
              pending && "text-[var(--fg-muted)]",
              step.state === "failed" && "text-[var(--danger)] font-medium",
              step.state === "skipped" && "text-[var(--fg-muted)] line-through decoration-[var(--border-strong)]",
            )}
          >
            {label}
          </span>
          <span className="flex items-center gap-2 shrink-0 font-mono-num text-xs text-[var(--fg-muted)]">
            {mode === "log" && step.duration_ms != null && (
              <span className="hidden sm:block w-16 h-1 rounded-full bg-[var(--bg-subtle)] overflow-hidden">
                <span
                  className="block h-full rounded-full bg-[var(--fg-muted)]"
                  style={{ width: `${Math.max(3, (step.duration_ms / maxMs) * 100)}%` }}
                />
              </span>
            )}
            {running && mode === "live" && startedAt !== null ? (
              <Elapsed since={startedAt} />
            ) : step.duration_ms != null && !running ? (
              formatDurationMs(step.duration_ms)
            ) : null}
          </span>
        </div>

        {running && (current || trail.length > 0) && (
          <div className="space-y-1">
            {trail.map((note) => (
              <p key={note} className="flex items-center gap-1.5 text-xs text-[var(--fg-muted)]">
                <Check className="h-3 w-3 shrink-0" aria-hidden="true" />
                <span className="truncate">{note.replace(DOMAIN_LIST_RE, "")}</span>
              </p>
            ))}
            {current && (
              <motion.p
                key={current.replace(/\d+/g, "#")}
                initial={{ opacity: 0, y: 3 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
                className="text-[13px] text-[var(--fg-secondary)] tabular"
              >
                {current.replace(DOMAIN_LIST_RE, "")}
              </motion.p>
            )}
          </div>
        )}

        <AnimatePresence initial={false}>
          {(running || done) && (
            <motion.div
              key={`${step.name}-${step.state}`}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={GENTLE_SPRING}
            >
              <StageDetail analysis={analysis} step={step} notes={notes} />
            </motion.div>
          )}
        </AnimatePresence>

        {done && step.detail && step.name !== "retrieve" && step.name !== "story" && (
          <p className="text-xs text-[var(--fg-muted)]">{step.detail}</p>
        )}
        {(step.state === "failed" || step.state === "skipped") && step.error && (
          <p className={cn("text-xs", step.state === "failed" ? "text-[var(--danger)]" : "text-[var(--fg-muted)]")}>
            {step.error}
          </p>
        )}
      </div>
    </li>
  );
}

/** The stage-by-stage ledger: live while running, the run log once finished. */
export function RunLedger({
  analysis,
  activity,
  mode,
}: Readonly<{ analysis: Analysis; activity: ActivityLog; mode: Mode }>) {
  const steps = ALL_STAGES.map((name) => stepOf(analysis, name));
  const maxMs = Math.max(1, ...steps.map((s) => s.duration_ms ?? 0));
  return (
    <ol aria-label="Analysis steps">
      {steps.map((step, i) => (
        <LedgerRow
          key={step.name}
          analysis={analysis}
          step={step}
          notes={activity[step.name]?.notes ?? []}
          startedAt={activity[step.name]?.startedAt ?? null}
          mode={mode}
          last={i === steps.length - 1}
          maxMs={maxMs}
        />
      ))}
    </ol>
  );
}

function SourceRow({ item, analysis, index }: Readonly<{ item: ContextItem; analysis: Analysis; index: number }>) {
  const domain = outletOf(item);
  const profile = analysis.sources.find((s) => cleanDomain(s.domain) === domain);
  const type = profile?.outlet_type ? OUTLET_TYPE_LABELS[profile.outlet_type] : null;
  const date = formatShortDate(item.published_at);
  const dimmed = item.in_story === false && !item.fact_check;

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...GENTLE_SPRING, delay: Math.min(index, 12) * 0.05 }}
      className="py-3 first:pt-0 border-b border-[var(--border-subtle)] last:border-b-0"
    >
      <a
        href={item.url}
        target="_blank"
        rel="noreferrer noopener"
        className={cn("group block space-y-1 transition-opacity", dimmed && "opacity-60 hover:opacity-100")}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          <Favicon domain={domain} size={14} />
          <span className="font-mono-num text-xs text-[var(--fg-secondary)] truncate">{domain}</span>
          <ExternalLink
            className="h-3 w-3 text-[var(--fg-muted)] opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
            aria-hidden="true"
          />
        </div>
        <p className="text-[13px] leading-snug text-[var(--fg-primary)] line-clamp-2 group-hover:underline decoration-[var(--border-strong)] underline-offset-2">
          {item.fact_check?.claim && !item.title ? item.fact_check.claim : item.title || domain}
        </p>
        <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
          {item.fact_check && (
            <span className={tagClass("caution")}>
              {item.fact_check.publisher ? `${item.fact_check.publisher}: ` : "Rated "}
              {item.fact_check.rating}
            </span>
          )}
          {item.in_story === true && <span className={tagClass("accent")}>Same event</span>}
          {type && <span className={tagClass(type.tone === "neutral" ? "neutral" : type.tone)}>{type.label}</span>}
          {profile?.known_network && <span className={tagClass("caution")}>{networkLabel(profile.known_network)}</span>}
          <span className="text-[11px] text-[var(--fg-muted)]">
            {ADAPTER_LABELS[item.retrieved_by] ?? item.retrieved_by}
            {date ? ` · ${date}` : ""}
          </span>
        </div>
      </a>
    </motion.li>
  );
}

/** Right rail while running: what is being searched, then every source as it arrives. */
function SourcesPanel({ analysis }: Readonly<{ analysis: Analysis }>) {
  const retrieve = stepOf(analysis, "retrieve");
  const searching = retrieve.state === "running";
  const items = analysis.context
    .slice()
    .sort(
      (a, b) =>
        Number(Boolean(b.fact_check)) - Number(Boolean(a.fact_check)) ||
        Number(b.in_story === true) - Number(a.in_story === true),
    );

  return (
    <section aria-label="Sources" className="editorial-card rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium">Sources</h2>
        {items.length > 0 && <span className="font-mono-num text-xs text-[var(--fg-muted)]">{items.length}</span>}
      </div>

      {items.length === 0 && (
        <div className="space-y-3">
          {analysis.queries.length > 0 ? (
            <ul className="space-y-1.5">
              {analysis.queries.map((q, i) => (
                <li key={`${q.language}-${i}`} className="flex items-center gap-2 text-[13px] text-[var(--fg-secondary)]">
                  <Search
                    className={cn("h-3.5 w-3.5 shrink-0", searching ? "text-[var(--accent)]" : "text-[var(--fg-muted)]")}
                    aria-hidden="true"
                  />
                  <span className={cn("truncate", searching && "shimmer")}>{q.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-[var(--fg-muted)]">Search terms come from the article.</p>
          )}
          <div className="space-y-2.5 pt-1" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="space-y-1.5">
                <div className="h-2.5 w-24 rounded bg-[var(--bg-subtle)]" />
                <div className={cn("h-2.5 rounded bg-[var(--bg-subtle)]", i === 1 ? "w-3/5" : "w-4/5")} />
              </div>
            ))}
          </div>
        </div>
      )}

      {items.length > 0 && (
        <ul className="max-h-[60vh] overflow-y-auto -mr-2 pr-2">
          {items.map((item, i) => (
            <SourceRow key={item.id} item={item} analysis={analysis} index={i} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** The live view of a running (or replayed) analysis. */
export function RunProgress({
  analysis,
  activity,
  replay,
}: Readonly<{ analysis: Analysis; activity: ActivityLog; replay: boolean }>) {
  const [mountedAt] = useState(() => Date.now());
  const steps = ALL_STAGES.map((name) => stepOf(analysis, name));
  const finished = steps.filter((s) => s.state !== "pending" && s.state !== "running").length;
  const queued = analysis.status === "queued";

  const created = Date.parse(analysis.created_at);
  const runStart = !replay && Number.isFinite(created) && Date.now() - created < 3_600_000 && Date.now() >= created
    ? created
    : mountedAt;

  const doc = analysis.document;
  const inputDomain = analysis.input.kind === "url" ? cleanDomain(analysis.input.value) : "";
  const title =
    doc?.title ||
    (analysis.input.kind === "url"
      ? analysis.input.value.replace(/^https?:\/\/(www\.)?/, "")
      : `${Array.from(analysis.input.value).slice(0, 140).join("")}${analysis.input.value.length > 140 ? "…" : ""}`);

  return (
    <motion.section
      aria-label="Analysis in progress"
      aria-busy="true"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={GENTLE_SPRING}
      className="space-y-8"
    >
      <header className="space-y-4">
        <div className="flex items-center justify-between gap-3 text-xs">
          <span className="inline-flex items-center gap-2 font-medium text-[var(--fg-secondary)]">
            <span className="live-dot" aria-hidden="true" />
            {queued
              ? `Queued · ${analysis.queue_position ?? 1} ahead`
              : replay
                ? "Replaying a stored run"
                : "Analyzing"}
          </span>
          <span className="font-mono-num text-[var(--fg-muted)]" aria-live="off">
            {finished}/{steps.length}
            {!replay && (
              <>
                {" · "}
                <Elapsed since={runStart} />
              </>
            )}
          </span>
        </div>

        <div className="flex items-start gap-3">
          {(cleanDomain(doc?.outlet ?? doc?.url) || inputDomain) && (
            <Favicon domain={cleanDomain(doc?.outlet ?? doc?.url) || inputDomain} size={22} className="mt-1.5" />
          )}
          <h1
            className={cn(
              "min-w-0 break-words",
              doc?.title || analysis.input.kind === "text"
                ? "display text-[26px] sm:text-[30px] leading-tight"
                : "font-mono-num text-base sm:text-lg text-[var(--fg-secondary)] leading-snug",
            )}
          >
            {title}
          </h1>
        </div>

        <div
          className="relative h-0.5 w-full rounded-full bg-[var(--border-subtle)] overflow-hidden"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={finished}
          aria-label="Steps finished"
        >
          <div className="absolute inset-0 progress-indeterminate opacity-60" />
          <motion.div
            className="relative h-full rounded-full bg-[var(--accent)]"
            initial={false}
            animate={{ width: `${Math.max(3, (finished / steps.length) * 100)}%` }}
            transition={GENTLE_SPRING}
          />
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px] gap-8 lg:gap-10 items-start">
        <div aria-live="polite">
          <RunLedger analysis={analysis} activity={activity} mode={replay ? "replay" : "live"} />
        </div>
        <div className="lg:sticky lg:top-20">
          <SourcesPanel analysis={analysis} />
        </div>
      </div>
    </motion.section>
  );
}

/** Start a new analysis that reuses this one's stored stage outputs up to `from`. */
export function RerunControl({ analysisId }: Readonly<{ analysisId: string }>) {
  const navigate = useNavigate();
  const [stage, setStage] = useState<StageName>("signals_single");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function rerun() {
    setError(null);
    setBusy(true);
    try {
      const created = await rerunAnalysis(analysisId, stage);
      navigate(`/analyses/${created.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start the re-run.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className={SECTION_LABEL}>Re-run from</span>
        <select
          value={stage}
          onChange={(e) => setStage(e.target.value as StageName)}
          className="h-8 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] px-2 text-[13px] text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
        >
          {ALL_STAGES.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABELS[s].label} ({s})
            </option>
          ))}
        </select>
        <button type="button" disabled={busy} onClick={() => void rerun()} className={buttonClass("secondary", "md")}>
          {busy ? "Starting…" : "Re-run"}
        </button>
      </div>
      {error && <p className="text-xs text-[var(--danger)]">{error}</p>}
    </div>
  );
}
