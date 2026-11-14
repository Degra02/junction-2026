import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Play,
  RotateCw,
  Share2,
  ShieldAlert,
} from "lucide-react";
import { CoverageView } from "../components/CoverageView";
import { DimensionScoreCard } from "../components/DimensionScoreCard";
import { DocumentReader } from "../components/DocumentReader";
import { ExplanationPanel } from "../components/ExplanationPanel";
import { PipelineStepper } from "../components/PipelineStepper";
import { ScoreBreakdown } from "../components/ScoreBreakdown";
import { useAnalysisStream } from "../hooks/useAnalysisStream";
import { createAnalysis } from "../lib/api";
import { formatDomainAge } from "../lib/format";
import {
  LANGUAGE_SUPPORT_LABELS,
  OUTLET_TYPE_LABELS,
  languageName,
  networkLabel,
} from "../lib/labels";
import { cn } from "../lib/utils";

export type AnalysisPageProps = Record<string, never>;

export function AnalysisPage(_props: Readonly<AnalysisPageProps>) {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const replay = searchParams.get("replay") === "true" || searchParams.get("replay") === "1";
  const { analysis, loading, isStreaming, error, notFound, reconnect } = useAnalysisStream(
    id,
    replay,
  );

  const [activeAnnotationId, setActiveAnnotationId] = useState<string | null>(null);
  const [breakdownOpen, setBreakdownOpen] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [forcingRun, setForcingRun] = useState<boolean>(false);

  function handleSelectEvidenceOrClaim(targetId: string) {
    setActiveAnnotationId((prev) => (prev === targetId ? null : targetId));
    if (!analysis) return;

    const ev = analysis.evidence.find((e) => e.id === targetId);
    if (ev) {
      const hasDocSpan = ev.source_refs.some((r) => r.kind === "document");
      if (!hasDocSpan) {
        setBreakdownOpen(true);
        requestAnimationFrame(() => {
          document
            .getElementById(`evidence-${ev.id}`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      }
    }
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
    const next = new URLSearchParams(searchParams);
    if (replay) {
      reconnect();
    } else {
      next.set("replay", "true");
      setSearchParams(next, { replace: true });
    }
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
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-8 space-y-4 max-w-xl mx-auto mt-6">
        <h1 className="text-lg font-bold text-[var(--fg-primary)] m-0">Analysis not found</h1>
        <p className="text-sm text-[var(--fg-secondary)] m-0">
          No stored analysis exists with ID <code className="font-mono-num">{id}</code> on this server.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-semibold hover:bg-[var(--accent-hover)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          <span>Start a new analysis</span>
        </Link>
      </div>
    );
  }

  if (loading && !analysis) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-20 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-subtle)] animate-pulse" />
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 space-y-4">
            <div className="h-40 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-subtle)] animate-pulse" />
            <div className="h-52 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-subtle)] animate-pulse" />
          </div>
          <div className="lg:col-span-5">
            <div className="h-80 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-subtle)] animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="rounded-xl border border-[var(--danger-border)] bg-[var(--danger-soft)] p-6 space-y-3">
        <h1 className="text-base font-bold text-[var(--danger)] m-0">Could not load analysis</h1>
        <p className="text-xs text-[var(--danger)] m-0">{error ?? "Connection error."}</p>
        <button
          type="button"
          onClick={reconnect}
          className="px-3.5 py-1.5 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-strong)] text-xs font-semibold text-[var(--fg-primary)] cursor-pointer"
        >
          Retry connection
        </button>
      </div>
    );
  }

  const isFinished = analysis.status === "done" || analysis.status === "failed";
  const isPending = !isFinished || isStreaming;

  const docOutlet = analysis.document?.outlet?.toLowerCase().replace(/^www\./, "") ?? null;
  const outletProfile = docOutlet
    ? analysis.sources.find((s) => s.domain.toLowerCase().replace(/^www\./, "") === docOutlet) ??
      null
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

  const headlineTitle =
    analysis.document?.title ||
    (analysis.input.kind === "url"
      ? analysis.input.value
      : analysis.input.value.length > 96
        ? `${Array.from(analysis.input.value).slice(0, 96).join("")}…`
        : analysis.input.value);

  const isPreliminaryEstimate = Boolean(
    analysis.explanation?.summary &&
      /preliminary|hand-set|uncalibrated|preliminari|vorläufig|préliminaire|preliminar/i.test(
        analysis.explanation.summary,
      ),
  );

  return (
    <div className="space-y-6">
      {/* Top Analysis Header Bar */}
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 sm:p-5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--fg-muted)] hover:text-[var(--fg-primary)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            <span>New analysis</span>
          </Link>

          <div className="flex flex-wrap items-center gap-2">
            {isFinished && (
              <button
                type="button"
                onClick={handleTriggerReplay}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] cursor-pointer"
              >
                <Play className="h-3.5 w-3.5 text-[var(--accent)]" aria-hidden="true" />
                <span>{isStreaming && replay ? "Restart replay" : "Replay steps"}</span>
              </button>
            )}

            {isFinished && (
              <button
                type="button"
                disabled={forcingRun}
                onClick={handleRunFresh}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-50 cursor-pointer"
              >
                <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{forcingRun ? "Starting…" : "Run fresh"}</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleCopyShareLink}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] cursor-pointer"
            >
              {copied ? (
                <>
                  <Check className="h-3.5 w-3.5 text-[var(--teal)]" aria-hidden="true" />
                  <span>Link copied</span>
                </>
              ) : (
                <>
                  <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Share link</span>
                </>
              )}
            </button>
          </div>
        </div>

        <h1 className="text-lg sm:text-xl font-bold tracking-tight text-[var(--fg-primary)] leading-snug m-0 break-words">
          {headlineTitle}
        </h1>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {analysis.document?.outlet && (
            <span className="px-2.5 py-0.5 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-subtle)] font-mono-num font-medium text-[var(--fg-primary)]">
              {analysis.document.outlet}
            </span>
          )}

          {outletTypeMeta && (
            <span
              className={cn(
                "px-2 py-0.5 rounded-md font-medium border",
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
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[var(--caution-soft)] border border-[var(--caution-border)] font-semibold text-[var(--caution)]">
              <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
              {networkLabel(outletProfile.known_network)}
            </span>
          )}

          {outletAge && (
            <span className="px-2 py-0.5 rounded-md bg-[var(--bg-subtle)] font-mono-num text-[var(--fg-secondary)]">
              {outletAge}
            </span>
          )}

          {analysis.language && langSupportMeta && (
            <span
              title={langSupportMeta.detail}
              className={cn(
                "px-2 py-0.5 rounded-md border font-medium",
                langSupportMeta.tone === "teal"
                  ? "bg-[var(--teal-soft)] text-[var(--teal)] border-[var(--teal-border)]"
                  : langSupportMeta.tone === "caution"
                    ? "bg-[var(--caution-soft)] text-[var(--caution)] border-[var(--caution-border)]"
                    : "bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-[var(--border-subtle)]",
              )}
            >
              {languageName(analysis.language.code)} ({analysis.language.code}) ·{" "}
              {langSupportMeta.badge}
            </span>
          )}

          <span className="font-mono-num text-[11px] text-[var(--fg-muted)] ml-auto">
            id {analysis.id.slice(0, 8)}
          </span>
        </div>
      </div>

      {/* Failed Analysis or Disconnected Stream Banner */}
      {(analysis.status === "failed" || error) && (
        <div
          role="alert"
          className="rounded-xl border border-[var(--danger-border)] bg-[var(--danger-soft)] p-4 flex items-start justify-between gap-3"
        >
          <div className="flex items-start gap-2.5 text-xs sm:text-sm text-[var(--danger)]">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-1">
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
              className="px-3 py-1.5 rounded-lg bg-[var(--bg-surface)] border border-[var(--border-strong)] text-xs font-semibold text-[var(--fg-primary)] shrink-0 cursor-pointer"
            >
              Reconnect
            </button>
          )}
        </div>
      )}

      {/* Asymmetric Two-Column Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Scores, Reasons, Coverage, Combiner Math */}
        <div className="lg:col-span-7 xl:col-span-8 space-y-6 min-w-0">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DimensionScoreCard
              dimension="single"
              score={analysis.scores?.single}
              evidence={analysis.evidence}
              isPreliminaryEstimate={isPreliminaryEstimate}
              isPending={isPending}
              onOpenBreakdown={() => {
                setBreakdownOpen(true);
                requestAnimationFrame(() => {
                  document
                    .getElementById("breakdown-toggle")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                });
              }}
            />
            <DimensionScoreCard
              dimension="coordinated"
              score={analysis.scores?.coordinated}
              evidence={analysis.evidence}
              isPreliminaryEstimate={isPreliminaryEstimate}
              isPending={isPending}
              onOpenBreakdown={() => {
                setBreakdownOpen(true);
                requestAnimationFrame(() => {
                  document
                    .getElementById("breakdown-toggle")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                });
              }}
            />
          </div>

          <ExplanationPanel
            explanation={analysis.explanation}
            evidence={analysis.evidence}
            input={analysis.input}
            detectedLanguage={analysis.language}
            activeEvidenceId={activeAnnotationId}
            onSelectEvidence={handleSelectEvidenceOrClaim}
            isPending={isPending}
          />

          <CoverageView
            context={analysis.context}
            sources={analysis.sources}
            evidence={analysis.evidence}
            claims={analysis.claims}
            documentLanguage={analysis.language}
            documentPublishedAt={analysis.document?.published_at}
            activeEvidenceId={activeAnnotationId}
            onSelectAnnotation={handleSelectEvidenceOrClaim}
            isPending={isPending}
          />

          <ScoreBreakdown
            analysisId={analysis.id}
            isFinished={isFinished}
            scores={analysis.scores}
            evidence={analysis.evidence}
            document={analysis.document}
            context={analysis.context}
            sources={analysis.sources}
            open={breakdownOpen}
            onToggle={() => setBreakdownOpen((v) => !v)}
            activeEvidenceId={activeAnnotationId}
            onSelectEvidence={handleSelectEvidenceOrClaim}
          />
        </div>

        {/* Right Column: Sticky Pipeline Stepper (top while running, below reader once done) & Verbatim Document Reader */}
        <div className="lg:col-span-5 xl:col-span-4 space-y-6 lg:sticky lg:top-20 min-w-0">
          {isPending && (
            <PipelineStepper
              status={analysis.status}
              queuePosition={analysis.queue_position}
              steps={analysis.steps}
              isStreaming={isStreaming}
            />
          )}

          <DocumentReader
            document={analysis.document}
            topic={analysis.topic}
            claims={analysis.claims}
            queries={analysis.queries}
            evidence={analysis.evidence}
            activeAnnotationId={activeAnnotationId}
            onSelectAnnotation={handleSelectEvidenceOrClaim}
            isPending={isPending}
          />

          {!isPending && (
            <PipelineStepper
              status={analysis.status}
              queuePosition={analysis.queue_position}
              steps={analysis.steps}
              isStreaming={isStreaming}
            />
          )}
        </div>
      </div>
    </div>
  );
}
