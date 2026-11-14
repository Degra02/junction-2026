import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import * as Tabs from "@radix-ui/react-tabs";
import { motion } from "motion/react";
import { ArrowLeft, Check, ExternalLink, Link2, Play, RotateCw } from "lucide-react";
import { CoverageView } from "../components/CoverageView";
import { DimensionScoreCard } from "../components/DimensionScoreCard";
import { DocumentReader } from "../components/DocumentReader";
import { ExplanationPanel } from "../components/ExplanationPanel";
import { RerunControl, RunLedger, RunProgress } from "../components/RunProgress";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { Favicon } from "../components/ui/Favicon";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import { createAnalysis } from "../lib/api";
import type { DimensionKey, Family } from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { formatDomainAge, formatDurationMs, formatShortDate } from "../lib/format";
import { LANGUAGE_SUPPORT_LABELS, OUTLET_TYPE_LABELS, languageName, networkLabel } from "../lib/labels";
import { GENTLE_SPRING } from "../lib/motion";
import { buttonClass, tagClass } from "../lib/ui";

export type AnalysisPageProps = Record<string, never>;

type TabId = "coverage" | "text" | "score" | "run";

const SINGLE_FAMILIES: Partial<Record<Family, true>> = {
  techniques: true,
  tone: true,
  claim_support: true,
  fact_checks: true,
  source_profile: true,
};

/** The fixed "uncalibrated weights" sentence of `pipeline/explain`, one word per language. */
const PRELIMINARY_RE =
  /preliminary|preliminari|vorläufig|préliminaire|preliminar|wstępne|voorlopige|предварительные|попередні/i;

const TAB_TRIGGER =
  "relative h-10 px-1 shrink-0 rounded-sm text-[13px] font-medium text-[var(--fg-muted)] hover:text-[var(--fg-primary)] data-[state=active]:text-[var(--fg-primary)] transition-colors cursor-pointer after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-transparent data-[state=active]:after:bg-[var(--fg-primary)]";

export function AnalysisPage(_props: Readonly<AnalysisPageProps>) {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const replay = searchParams.get("replay") === "true" || searchParams.get("replay") === "1";
  const { analysis, activity, loading, isStreaming, error, notFound, reconnect } = useAnalysisStream(id, replay);

  const [tab, setTab] = useState<TabId>("coverage");
  const [mathDimension, setMathDimension] = useState<DimensionKey>("single");
  const [activeAnnotationId, setActiveAnnotationId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [forcingRun, setForcingRun] = useState(false);

  function openTab(next: TabId, scrollTarget?: string) {
    setTab(next);
    requestAnimationFrame(() => {
      const el = scrollTarget ? document.getElementById(scrollTarget) : null;
      (el ?? document.getElementById("details"))?.scrollIntoView({
        behavior: "smooth",
        block: el ? "center" : "start",
      });
    });
  }

  function handleInspectCalculation(dim: DimensionKey) {
    setMathDimension(dim);
    openTab("score");
  }

  function handleInspectEvidenceOrClaim(targetId: string) {
    setActiveAnnotationId(targetId);
    const ev = analysis?.evidence.find((e) => e.id === targetId);
    if (ev && !ev.source_refs.some((r) => r.kind === "document")) {
      setMathDimension(SINGLE_FAMILIES[ev.family] ? "single" : "coordinated");
      openTab("score", `evidence-${ev.id}`);
      return;
    }
    // Claims and evidence quoted from the article open the annotated text.
    openTab("text");
  }

  async function handleCopyLink() {
    if (!id) return;
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/analyses/${id}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard can be unavailable (insecure origin); nothing to do.
    }
  }

  function setReplay(on: boolean) {
    const next = new URLSearchParams(searchParams);
    if (on) next.set("replay", "true");
    else next.delete("replay");
    setSearchParams(next, { replace: true });
  }

  async function handleRunFresh() {
    if (!analysis) return;
    setForcingRun(true);
    try {
      const created = await createAnalysis(analysis.input, { force: true });
      navigate(`/analyses/${created.id}`);
    } catch {
      setForcingRun(false);
    }
  }

  if (notFound) {
    return (
      <div className="max-w-md mx-auto pt-16 text-center space-y-4">
        <h1 className="display text-3xl">Analysis not found</h1>
        <p className="text-sm text-[var(--fg-secondary)]">
          Nothing is stored under <code className="font-mono-num text-xs">{id}</code>.
        </p>
        <Link to="/" className={buttonClass("primary", "md")}>
          New analysis
        </Link>
      </div>
    );
  }

  if (loading && !analysis) {
    return (
      <div aria-busy="true" className="max-w-[760px] mx-auto pt-10 space-y-5">
        <div className="flex items-center gap-2 text-xs text-[var(--fg-muted)]">
          <span className="live-dot" aria-hidden="true" />
          <span className="shimmer">Connecting</span>
        </div>
        <div className="h-8 w-3/4 rounded-md bg-[var(--bg-subtle)]" />
        <div className="h-0.5 w-full rounded-full bg-[var(--border-subtle)] overflow-hidden">
          <div className="h-full w-full progress-indeterminate" />
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="max-w-md mx-auto pt-16 space-y-3">
        <h1 className="display text-2xl">Could not load this analysis</h1>
        <p className="text-sm text-[var(--danger)]">{error ?? "Connection error."}</p>
        <button type="button" onClick={reconnect} className={buttonClass("secondary", "md")}>
          Try again
        </button>
      </div>
    );
  }

  const isFinished = analysis.status === "done" || analysis.status === "failed";
  const isLive = !isFinished || isStreaming;

  const docOutlet = cleanDomain(analysis.document?.outlet ?? analysis.document?.url);
  const outletProfile = docOutlet
    ? (analysis.sources.find((s) => cleanDomain(s.domain) === docOutlet) ?? null)
    : null;
  const outletType = outletProfile?.outlet_type ? OUTLET_TYPE_LABELS[outletProfile.outlet_type] : null;
  const outletAge = formatDomainAge(
    outletProfile?.registered_at,
    outletProfile?.first_cert_at,
    analysis.document?.published_at,
  );
  const langSupport = analysis.language ? LANGUAGE_SUPPORT_LABELS[analysis.language.support] : null;
  const cappedAt85 = analysis.language?.support === "supported";
  const published = formatShortDate(analysis.document?.published_at);

  const headlineTitle =
    analysis.document?.title ||
    (analysis.input.kind === "url"
      ? analysis.input.value
      : `${Array.from(analysis.input.value).slice(0, 120).join("")}${analysis.input.value.length > 120 ? "…" : ""}`);

  const isPreliminaryEstimate = PRELIMINARY_RE.test(analysis.explanation?.summary ?? "");
  const totalMs = analysis.steps.reduce((acc, s) => acc + (s.duration_ms ?? 0), 0);

  return (
    <div className="max-w-[960px] mx-auto space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-2 -mt-2">
        <Link to="/" className={buttonClass("ghost", "sm", "-ml-2.5")}>
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          New analysis
        </Link>

        <div className="flex items-center gap-1">
          {isLive && replay && (
            <button type="button" onClick={() => setReplay(false)} className={buttonClass("secondary", "sm")}>
              Skip to result
            </button>
          )}
          {!isLive && (
            <>
              <button
                type="button"
                onClick={() => (replay ? reconnect() : setReplay(true))}
                className={buttonClass("ghost", "sm")}
              >
                <Play className="h-3 w-3 fill-current" aria-hidden="true" />
                Replay
              </button>
              <button
                type="button"
                disabled={forcingRun}
                onClick={() => void handleRunFresh()}
                title="Run again without the cache"
                className={buttonClass("ghost", "sm")}
              >
                <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                {forcingRun ? "Starting…" : "Run again"}
              </button>
            </>
          )}
          <button type="button" onClick={() => void handleCopyLink()} className={buttonClass("ghost", "sm")}>
            {copied ? (
              <Check className="h-3.5 w-3.5 text-[var(--teal)]" aria-hidden="true" />
            ) : (
              <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            {copied ? "Copied" : "Copy link"}
          </button>
        </div>
      </div>

      {(analysis.status === "failed" || error) && (
        <div
          role="alert"
          className="rounded-xl border border-[var(--danger-border)] bg-[var(--danger-soft)] px-4 py-3 flex items-start justify-between gap-3"
        >
          <div className="text-[13px] text-[var(--danger)] space-y-0.5">
            <p className="font-medium">
              {analysis.status === "failed" ? "The analysis stopped early" : "Live updates interrupted"}
            </p>
            <p>{analysis.error ?? error}</p>
          </div>
          {error && analysis.status !== "failed" && (
            <button type="button" onClick={reconnect} className={buttonClass("secondary", "sm")}>
              Reconnect
            </button>
          )}
        </div>
      )}

      {isLive ? (
        <RunProgress analysis={analysis} activity={activity} replay={replay} />
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={GENTLE_SPRING}
          className="space-y-8"
        >
          <header className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-xs text-[var(--fg-secondary)]">
              {docOutlet ? (
                <a
                  href={analysis.document?.url ?? undefined}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1.5 font-mono-num text-[var(--fg-primary)] hover:underline underline-offset-2"
                >
                  <Favicon domain={docOutlet} size={16} />
                  {docOutlet}
                  <ExternalLink className="h-3 w-3 text-[var(--fg-muted)]" aria-hidden="true" />
                </a>
              ) : (
                <span className="text-[var(--fg-primary)]">Pasted text</span>
              )}
              {published && <span className="font-mono-num text-[var(--fg-muted)]">{published}</span>}
              {outletType && (
                <span className={tagClass(outletType.tone === "neutral" ? "neutral" : outletType.tone)}>
                  {outletType.label}
                </span>
              )}
              {outletProfile?.known_network && (
                <span className={tagClass("caution")}>{networkLabel(outletProfile.known_network)}</span>
              )}
              {outletAge && <span className={tagClass("neutral", { mono: true })}>{outletAge}</span>}
              {analysis.language && langSupport && (
                <span
                  title={langSupport.detail}
                  className={tagClass(langSupport.tone === "neutral" ? "neutral" : langSupport.tone)}
                >
                  {languageName(analysis.language.code)} · {langSupport.badge.toLowerCase()}
                </span>
              )}
            </div>
            <h1 className="display text-[28px] sm:text-[36px] leading-[1.12] break-words">{headlineTitle}</h1>
          </header>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DimensionScoreCard
              dimension="single"
              score={analysis.scores?.single}
              evidence={analysis.evidence}
              isPreliminaryEstimate={isPreliminaryEstimate}
              cappedAt85={cappedAt85}
              onInspectCalculation={handleInspectCalculation}
            />
            <DimensionScoreCard
              dimension="coordinated"
              score={analysis.scores?.coordinated}
              evidence={analysis.evidence}
              isPreliminaryEstimate={isPreliminaryEstimate}
              cappedAt85={cappedAt85}
              onInspectCalculation={handleInspectCalculation}
            />
          </div>

          <ExplanationPanel
            explanation={analysis.explanation}
            evidence={analysis.evidence}
            document={analysis.document}
            context={analysis.context}
            sources={analysis.sources}
            input={analysis.input}
            detectedLanguage={analysis.language}
            activeEvidenceId={activeAnnotationId}
            onInspectEvidence={handleInspectEvidenceOrClaim}
          />

          <Tabs.Root
            id="details"
            value={tab}
            onValueChange={(v) => setTab(v as TabId)}
            className="scroll-mt-20 space-y-5"
          >
            <Tabs.List
              aria-label="Details"
              className="flex items-center gap-6 overflow-x-auto shadow-[inset_0_-1px_0_var(--border-subtle)]"
            >
              <Tabs.Trigger value="coverage" className={TAB_TRIGGER}>
                Coverage <span className="font-mono-num text-xs text-[var(--fg-muted)]">{analysis.context.length}</span>
              </Tabs.Trigger>
              <Tabs.Trigger value="text" className={TAB_TRIGGER}>
                Text{" "}
                <span className="font-mono-num text-xs text-[var(--fg-muted)]">
                  {analysis.document?.paragraphs.length ?? 0}¶
                </span>
              </Tabs.Trigger>
              <Tabs.Trigger value="score" className={TAB_TRIGGER}>
                Score
              </Tabs.Trigger>
              <Tabs.Trigger value="run" className={TAB_TRIGGER}>
                Run log{" "}
                <span className="font-mono-num text-xs text-[var(--fg-muted)]">{formatDurationMs(totalMs)}</span>
              </Tabs.Trigger>
            </Tabs.List>

            <Tabs.Content value="coverage" className="outline-none">
              <CoverageView
                context={analysis.context}
                sources={analysis.sources}
                evidence={analysis.evidence}
                claims={analysis.claims}
                documentLanguage={analysis.language}
                documentOutlet={analysis.document?.outlet}
                documentPublishedAt={analysis.document?.published_at}
                activeEvidenceId={activeAnnotationId}
                onSelectAnnotation={handleInspectEvidenceOrClaim}
              />
            </Tabs.Content>
            <Tabs.Content value="text" className="outline-none">
              <DocumentReader
                document={analysis.document}
                topic={analysis.topic}
                claims={analysis.claims}
                evidence={analysis.evidence}
                context={analysis.context}
                sources={analysis.sources}
                activeAnnotationId={activeAnnotationId}
                onSelectAnnotation={setActiveAnnotationId}
              />
            </Tabs.Content>
            <Tabs.Content value="score" className="outline-none">
              <ScoreBreakdown
                scores={analysis.scores}
                evidence={analysis.evidence}
                document={analysis.document}
                context={analysis.context}
                sources={analysis.sources}
                cappedAt85={cappedAt85}
                activeDimension={mathDimension}
                onChangeDimension={setMathDimension}
                activeEvidenceId={activeAnnotationId}
                onInspectEvidence={handleInspectEvidenceOrClaim}
              />
            </Tabs.Content>
            <Tabs.Content value="run" className="outline-none">
              <div className="editorial-card rounded-xl p-5 space-y-6">
                <RunLedger analysis={analysis} activity={activity} mode="log" />
                <div className="pt-4 border-t border-[var(--border-subtle)] flex flex-wrap items-center justify-between gap-3">
                  <RerunControl analysisId={analysis.id} />
                  <span className="font-mono-num text-xs text-[var(--fg-muted)]">{analysis.pipeline_version}</span>
                </div>
              </div>
            </Tabs.Content>
          </Tabs.Root>
        </motion.div>
      )}
    </div>
  );
}
