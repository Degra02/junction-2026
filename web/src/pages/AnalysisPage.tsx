import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import {
  AlertTriangle,
  ArrowLeft,
  Calculator,
  Check,
  ChevronDown,
  FileText,
  Globe,
  Loader2,
  Play,
  RotateCw,
  Share2,
  ShieldAlert,
} from "lucide-react";
import { CoverageView } from "../components/CoverageView";
import { DimensionScoreCard } from "../components/DimensionScoreCard";
import { DocumentReader } from "../components/DocumentReader";
import { ExplanationPanel } from "../components/ExplanationPanel";
import { LiveInvestigationStream } from "../components/LiveInvestigationStream";
import { PipelineStepper } from "../components/PipelineStepper";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import { createAnalysis } from "../lib/api";
import type { DimensionKey, Family } from "../lib/contracts";
import { cleanDomain } from "../lib/evidence";
import { formatDomainAge } from "../lib/format";
import {
  LANGUAGE_SUPPORT_LABELS,
  OUTLET_TYPE_LABELS,
  languageName,
  networkLabel,
} from "../lib/labels";
import { GENTLE_SPRING, SPATIAL_SPRING } from "../lib/motion";
import { cn } from "../lib/utils";

export type AnalysisPageProps = Record<string, never>;

type DeepDiveSection = "math" | "coverage" | "reader";

const SINGLE_FAMILIES: Partial<Record<Family, true>> = {
  techniques: true,
  tone: true,
  claim_support: true,
  fact_checks: true,
  source_profile: true,
};

export function AnalysisPage(_props: Readonly<AnalysisPageProps>) {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const replay = searchParams.get("replay") === "true" || searchParams.get("replay") === "1";
  const { analysis, loading, isStreaming, error, notFound, reconnect } = useAnalysisStream(
    id,
    replay,
  );

  const [deepDive, setDeepDive] = useState<DeepDiveSection | null>(null);
  const [mathDimension, setMathDimension] = useState<DimensionKey>("single");
  const [activeAnnotationId, setActiveAnnotationId] = useState<string | null>(null);
  const [pipelineDrawerOpen, setPipelineDrawerOpen] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [forcingRun, setForcingRun] = useState<boolean>(false);

  function scrollToDeepDive() {
    requestAnimationFrame(() => {
      document
        .getElementById("deep-dive-anchor")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function handleInspectCalculation(dim: DimensionKey) {
    setMathDimension(dim);
    setDeepDive("math");
    scrollToDeepDive();
  }

  function handleInspectEvidenceOrClaim(targetId: string) {
    setActiveAnnotationId(targetId);
    if (!analysis) return;

    const ev = analysis.evidence.find((e) => e.id === targetId);
    if (ev) {
      const hasDocSpan = ev.source_refs.some((r) => r.kind === "document");
      if (hasDocSpan) {
        setDeepDive("reader");
      } else {
        setMathDimension(SINGLE_FAMILIES[ev.family] ? "single" : "coordinated");
        setDeepDive("math");
        requestAnimationFrame(() => {
          document
            .getElementById(`evidence-${ev.id}`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      }
      return;
    }

    // Claim ID -> open Annotated Source Text
    setDeepDive("reader");
  }

  async function handleCopyShareLink() {
    if (!id) return;
    const shareUrl = `${window.location.origin}/analyses/${id}`;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard failures
    }
  }

  function handleTriggerReplay() {
    setDeepDive(null);
    const next = new URLSearchParams(searchParams);
    if (replay) {
      reconnect();
    } else {
      next.set("replay", "true");
      setSearchParams(next, { replace: true });
    }
  }

  function handleExitReplay() {
    const next = new URLSearchParams(searchParams);
    next.delete("replay");
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
      <div className="max-w-lg mx-auto mt-8 editorial-card rounded-3xl p-7 space-y-4 text-center">
        <h1 className="text-lg font-bold text-[var(--fg-primary)] m-0">Analysis not found</h1>
        <p className="text-sm text-[var(--fg-secondary)] m-0">
          No stored record exists with ID <code className="font-mono-num">{id}</code>.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-[var(--accent)] text-white text-xs font-semibold hover:bg-[var(--accent-hover)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Investigate a new item</span>
        </Link>
      </div>
    );
  }

  if (loading && !analysis) {
    return (
      <div
        aria-busy="true"
        className="max-w-[760px] mx-auto py-16 flex flex-col items-center justify-center gap-3 text-center"
      >
        <div className="h-10 w-10 rounded-2xl glass-pill inline-flex items-center justify-center text-[var(--accent)]">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
        <p className="text-sm font-medium text-[var(--fg-secondary)] m-0">
          Connecting to live analysis stream…
        </p>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="max-w-lg mx-auto mt-8 rounded-3xl border border-[var(--danger-border)] bg-[var(--danger-soft)] p-6 space-y-3">
        <h1 className="text-base font-bold text-[var(--danger)] m-0">Could not load analysis</h1>
        <p className="text-xs text-[var(--danger)] m-0">{error ?? "Connection error."}</p>
        <button
          type="button"
          onClick={reconnect}
          className="px-4 py-1.5 rounded-full bg-[var(--bg-surface)] border border-[var(--border-strong)] text-xs font-semibold text-[var(--fg-primary)] cursor-pointer"
        >
          Retry connection
        </button>
      </div>
    );
  }

  const isFinished = analysis.status === "done" || analysis.status === "failed";
  const isLiveOrReplaying = !isFinished || isStreaming;

  const docOutlet = cleanDomain(analysis.document?.outlet ?? analysis.document?.url);
  const outletProfile = docOutlet
    ? analysis.sources.find((s) => cleanDomain(s.domain) === docOutlet) ?? null
    : null;
  const outletTypeMeta = outletProfile?.outlet_type
    ? OUTLET_TYPE_LABELS[outletProfile.outlet_type]
    : null;
  const outletAge = formatDomainAge(
    outletProfile?.registered_at,
    outletProfile?.first_cert_at,
    analysis.document?.published_at,
  );

  const langSupportMeta = analysis.language
    ? LANGUAGE_SUPPORT_LABELS[analysis.language.support]
    : null;
  const cappedAt85 = analysis.language?.support === "supported";

  const headlineTitle =
    analysis.document?.title ||
    (analysis.input.kind === "url"
      ? analysis.input.value
      : analysis.input.value.length > 100
        ? `${Array.from(analysis.input.value).slice(0, 100).join("")}…`
        : analysis.input.value);

  const isPreliminaryEstimate = Boolean(
    analysis.explanation?.summary &&
      /preliminary|preliminari|vorläufig|préliminaire|preliminar|wstępne|voorlopige|предварительные|попередні/i.test(
        analysis.explanation.summary,
      ),
  );

  return (
    <div className="max-w-[940px] mx-auto space-y-6">
      {/* Top Floating Control Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/"
          className="glass-pill rounded-full h-8 px-3 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          <span>New investigation</span>
        </Link>

        <div className="flex flex-wrap items-center gap-2">
          {/* Slide-Over Pipeline Trace Trigger */}
          <PipelineStepper
            analysis={analysis}
            open={pipelineDrawerOpen}
            onOpenChange={setPipelineDrawerOpen}
          />

          {isLiveOrReplaying && replay ? (
            <button
              type="button"
              onClick={handleExitReplay}
              className="glass-pill rounded-full h-8 px-3 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--accent)] cursor-pointer"
            >
              <span>Skip to result →</span>
            </button>
          ) : (
            isFinished && (
              <>
                <button
                  type="button"
                  onClick={handleTriggerReplay}
                  className="glass-pill rounded-full h-8 px-3 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition-colors cursor-pointer"
                >
                  <Play className="h-3 w-3 text-[var(--accent)] fill-current" aria-hidden="true" />
                  <span>Replay steps</span>
                </button>

                <button
                  type="button"
                  disabled={forcingRun}
                  onClick={() => void handleRunFresh()}
                  title="Bypass cache and scrape fresh sources"
                  className="glass-pill rounded-full h-8 px-3 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] disabled:opacity-50 transition-colors cursor-pointer"
                >
                  <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                  <span className="hidden sm:inline">{forcingRun ? "Starting…" : "Run fresh"}</span>
                </button>
              </>
            )
          )}

          <button
            type="button"
            onClick={() => void handleCopyShareLink()}
            className="glass-pill rounded-full h-8 px-3 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition-colors cursor-pointer"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-[var(--teal)]" aria-hidden="true" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Share</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error / Interrupted Stream Banner */}
      {(analysis.status === "failed" || error) && (
        <div
          role="alert"
          className="rounded-2xl border border-[var(--danger-border)] bg-[var(--danger-soft)] p-4 flex items-start justify-between gap-3"
        >
          <div className="flex items-start gap-2.5 text-xs sm:text-sm text-[var(--danger)]">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-0.5">
              <div className="font-bold">
                {analysis.status === "failed"
                  ? "Analysis failed before completing all stages"
                  : "Progress stream interrupted"}
              </div>
              <p className="m-0">{analysis.error ?? error}</p>
            </div>
          </div>

          {error && analysis.status !== "failed" && (
            <button
              type="button"
              onClick={reconnect}
              className="px-3 py-1.5 rounded-full bg-[var(--bg-surface)] border border-[var(--border-strong)] text-xs font-semibold text-[var(--fg-primary)] shrink-0 cursor-pointer"
            >
              Reconnect
            </button>
          )}
        </div>
      )}

      {/* PHASE 1: LIVE RESEARCH THEATER (While Running or Replaying) */}
      {isLiveOrReplaying ? (
        <LiveInvestigationStream analysis={analysis} />
      ) : (
        /* PHASE 2: CLEAN VERDICT + PROGRESSIVE DISCLOSURE DEEP DIVE */
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={GENTLE_SPRING}
          className="space-y-6"
        >
          {/* Compact Analysed Item Header */}
          <div className="space-y-2.5 px-1">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--fg-primary)] leading-snug m-0 break-words">
              {headlineTitle}
            </h1>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              {docOutlet && (
                <span className="px-2.5 py-0.5 rounded-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] font-mono-num font-medium text-[var(--fg-primary)]">
                  {docOutlet}
                </span>
              )}

              {outletTypeMeta && (
                <span
                  className={cn(
                    "px-2.5 py-0.5 rounded-full font-medium border",
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

              {outletProfile?.known_network && (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-[var(--caution-soft)] border border-[var(--caution-border)] font-semibold text-[var(--caution)]">
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{networkLabel(outletProfile.known_network)}</span>
                </span>
              )}

              {outletAge && (
                <span className="px-2.5 py-0.5 rounded-full bg-[var(--bg-subtle)] font-mono-num text-[var(--fg-secondary)]">
                  {outletAge}
                </span>
              )}

              {analysis.language && langSupportMeta && (
                <span
                  title={langSupportMeta.detail}
                  className={cn(
                    "px-2.5 py-0.5 rounded-full border font-medium",
                    langSupportMeta.tone === "teal"
                      ? "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)]"
                      : langSupportMeta.tone === "caution"
                        ? "bg-[var(--caution-soft)] text-[var(--caution)] border-[var(--caution-border)]"
                        : "bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-[var(--border-subtle)]",
                  )}
                >
                  {languageName(analysis.language.code)} · {langSupportMeta.badge}
                </span>
              )}
            </div>
          </div>

          {/* Dual Calibrated Confidence Spectrum Cards */}
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

          {/* Executive Summary & 3 Plain-Language Reasons */}
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

          {/* ON-DEMAND PROGRESSIVE DISCLOSURE DOCK (Collapsed until requested!) */}
          <div id="deep-dive-anchor" className="pt-2 space-y-4">
            <div className="glass-panel rounded-2xl p-2 flex flex-wrap items-center justify-between gap-2">
              <span className="px-2.5 text-xs font-semibold text-[var(--fg-secondary)]">
                Inspect underlying evidence &amp; plots:
              </span>

              <div className="flex flex-wrap items-center gap-1.5">
                {(
                  [
                    {
                      id: "math",
                      label: "Score Math & Waterfall",
                      icon: Calculator,
                    },
                    {
                      id: "coverage",
                      label: `Visited Sites & Plots (${analysis.context.length})`,
                      icon: Globe,
                    },
                    {
                      id: "reader",
                      label: `Annotated Text (${analysis.document?.paragraphs.length ?? 0} ¶)`,
                      icon: FileText,
                    },
                  ] as const
                ).map((item) => {
                  const Icon = item.icon;
                  const isOpen = deepDive === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      aria-expanded={isOpen}
                      onClick={() => {
                        const opening = deepDive !== item.id;
                        setDeepDive(opening ? item.id : null);
                        if (opening) scrollToDeepDive();
                      }}
                      className={cn(
                        "inline-flex items-center gap-1.5 h-9 px-3.5 rounded-xl text-xs font-semibold transition-all cursor-pointer",
                        isOpen
                          ? "bg-[var(--accent)] text-white shadow-xs"
                          : "bg-[var(--bg-surface)]/80 border border-[var(--border-subtle)] text-[var(--fg-primary)] hover:border-[var(--accent-border)]",
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                      <span>{item.label}</span>
                      <ChevronDown
                        className={cn(
                          "h-3.5 w-3.5 transition-transform",
                          isOpen && "rotate-180",
                        )}
                        aria-hidden="true"
                      />
                    </button>
                  );
                })}
              </div>
            </div>

            <AnimatePresence mode="wait">
              {deepDive === "math" && (
                <motion.div
                  key="panel-math"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={SPATIAL_SPRING}
                >
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
                </motion.div>
              )}

              {deepDive === "coverage" && (
                <motion.div
                  key="panel-coverage"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={SPATIAL_SPRING}
                >
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
                </motion.div>
              )}

              {deepDive === "reader" && (
                <motion.div
                  key="panel-reader"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={SPATIAL_SPRING}
                >
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
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      )}
    </div>
  );
}
