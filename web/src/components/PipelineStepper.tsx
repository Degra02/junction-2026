import { useState } from "react";
import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Loader2,
  MinusCircle,
  RotateCcw,
  X,
} from "lucide-react";
import { rerunAnalysis } from "../lib/api";
import type { Analysis, StageName, Step } from "../lib/contracts";
import { formatDurationMs } from "../lib/format";
import { ALL_STAGES, STAGE_LABELS } from "../lib/labels";

export interface PipelineStepperProps {
  readonly analysis: Analysis;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

/**
 * Compact Floating Pipeline Pill + On-Demand Slide-Over Liquid Glass Inspector Sheet.
 * Keeps technical pipeline traces out of the main reading flow until requested.
 */
export function PipelineStepper({
  analysis,
  open,
  onOpenChange,
}: Readonly<PipelineStepperProps>) {
  const navigate = useNavigate();
  const [rerunStage, setRerunStage] = useState<StageName>("signals_single");
  const [rerunning, setRerunning] = useState<boolean>(false);
  const [rerunError, setRerunError] = useState<string | null>(null);

  const stepMap = new Map(analysis.steps.map((s) => [s.name, s]));
  const ordered: Step[] = ALL_STAGES.map(
    (name) =>
      stepMap.get(name) ?? {
        name,
        state: "pending",
        duration_ms: null,
        detail: null,
        error: null,
      },
  );

  const completedCount = ordered.filter(
    (s) => s.state === "done" || s.state === "skipped",
  ).length;
  const totalDurationMs = ordered.reduce((acc, s) => acc + (s.duration_ms ?? 0), 0);
  const maxStageMs = Math.max(100, ...ordered.map((s) => s.duration_ms ?? 0));

  async function handleRerun() {
    setRerunError(null);
    setRerunning(true);
    try {
      const created = await rerunAnalysis(analysis.id, rerunStage);
      onOpenChange(false);
      navigate(`/analyses/${created.id}`);
    } catch (err: unknown) {
      setRerunError(err instanceof Error ? err.message : "Could not re-run from stage.");
    } finally {
      setRerunning(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="glass-pill rounded-full h-8 px-3 inline-flex items-center gap-2 text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] transition-colors cursor-pointer"
        >
          <Activity className="h-3.5 w-3.5 text-[var(--teal)]" aria-hidden="true" />
          <span>
            {completedCount}/{ALL_STAGES.length} stages ·{" "}
            <strong className="font-mono-num font-semibold text-[var(--fg-primary)]">
              {formatDurationMs(totalDurationMs)}
            </strong>
          </span>
          <ChevronRight className="h-3.5 w-3.5 text-[var(--fg-muted)]" aria-hidden="true" />
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-xs" />
        <Dialog.Content className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md glass-popover border-l border-[var(--border-glass)] p-5 sm:p-6 overflow-y-auto overflow-x-hidden flex flex-col justify-between gap-6 outline-none">
          <div className="space-y-5">
            <div className="flex items-start justify-between gap-3 pb-4 border-b border-[var(--border-subtle)]">
              <div className="space-y-1">
                <Dialog.Title className="text-base font-bold text-[var(--fg-primary)] m-0">
                  Pipeline Execution Trace
                </Dialog.Title>
                <Dialog.Description className="text-xs text-[var(--fg-secondary)] m-0">
                  8-stage verification DAG · Total stage compute{" "}
                  <span className="font-mono-num font-semibold">
                    {formatDurationMs(totalDurationMs)}
                  </span>
                </Dialog.Description>
              </div>

              <Dialog.Close asChild>
                <button
                  type="button"
                  aria-label="Close pipeline inspector"
                  className="h-8 w-8 rounded-full inline-flex items-center justify-center text-[var(--fg-muted)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] cursor-pointer"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>

            {/* Stage Latency Waterfall & Output Audit */}
            <ol className="space-y-3 list-none p-0 m-0">
              {ordered.map((step, idx) => {
                const meta = STAGE_LABELS[step.name];
                const pctWidth =
                  step.duration_ms != null
                    ? Math.max(4, Math.round((step.duration_ms / maxStageMs) * 100))
                    : 0;

                const isParallelSignal =
                  step.name === "signals_single" || step.name === "signals_coordinated";

                return (
                  <li
                    key={step.name}
                    className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)]/80 p-3.5 space-y-2"
                  >
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <div className="inline-flex items-center gap-2 font-semibold text-[var(--fg-primary)] min-w-0">
                        {step.state === "done" ? (
                          <CheckCircle2 className="h-4 w-4 text-[var(--teal)] shrink-0" aria-hidden="true" />
                        ) : step.state === "failed" ? (
                          <AlertTriangle className="h-4 w-4 text-[var(--danger)] shrink-0" aria-hidden="true" />
                        ) : step.state === "skipped" ? (
                          <MinusCircle className="h-4 w-4 text-[var(--fg-muted)] shrink-0" aria-hidden="true" />
                        ) : (
                          <Loader2 className="h-4 w-4 text-[var(--accent)] animate-spin shrink-0" aria-hidden="true" />
                        )}
                        <span className="truncate">
                          {idx + 1}. {meta.label}
                        </span>
                      </div>

                      <span className="font-mono-num text-[11px] text-[var(--fg-muted)] shrink-0">
                        {formatDurationMs(step.duration_ms)}
                      </span>
                    </div>

                    {isParallelSignal && (
                      <div className="text-[10px] font-mono-num text-[var(--accent)]">
                        ∥ Parallel signal branch
                      </div>
                    )}

                    {step.duration_ms != null && (
                      <div className="h-1.5 rounded-full bg-[var(--bg-subtle)] overflow-hidden">
                        <div
                          style={{ width: `${pctWidth}%` }}
                          className="h-full rounded-full bg-[var(--accent)]/80"
                        />
                      </div>
                    )}

                    {step.detail && (
                      <p className="text-[11px] text-[var(--fg-secondary)] m-0 leading-snug">
                        {step.detail}
                      </p>
                    )}

                    {step.error && (
                      <p className="text-[11px] text-[var(--danger)] m-0 leading-snug">
                        {step.error}
                      </p>
                    )}
                  </li>
                );
              })}
            </ol>

            {/* Search Queries Used */}
            {analysis.queries.length > 0 && (
              <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)]/80 p-3.5 space-y-2">
                <div className="text-xs font-bold text-[var(--fg-primary)]">
                  Generated multilingual search queries ({analysis.queries.length})
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {analysis.queries.map((q, i) => (
                    <span
                      key={`${q.language}-${i}`}
                      className="px-2.5 py-0.5 rounded-full bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[11px] text-[var(--fg-secondary)] break-words max-w-full"
                    >
                      {q.text}{" "}
                      <strong className="font-mono-num uppercase text-[10px] text-[var(--fg-muted)]">
                        {q.language}
                      </strong>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Re-run From Stage Utility */}
          {(analysis.status === "done" || analysis.status === "failed") && (
            <div className="pt-4 border-t border-[var(--border-subtle)] space-y-2.5">
              <div className="text-xs font-bold text-[var(--fg-primary)]">
                Re-run pipeline from stage
              </div>
              <p className="text-[11px] text-[var(--fg-muted)] m-0 leading-snug">
                Reuses stored outputs from earlier stages to iterate on signal, scoring, or explanation changes.
              </p>

              <div className="flex items-center gap-2">
                <select
                  value={rerunStage}
                  onChange={(e) => setRerunStage(e.target.value as StageName)}
                  className="flex-1 h-8 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-surface)] px-2.5 text-xs text-[var(--fg-primary)]"
                >
                  {ALL_STAGES.map((st) => (
                    <option key={st} value={st}>
                      {st} — {STAGE_LABELS[st].label}
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  disabled={rerunning}
                  onClick={() => void handleRerun()}
                  className="inline-flex items-center gap-1.5 h-8 px-3 rounded-xl bg-[var(--accent)] text-white text-xs font-semibold hover:bg-[var(--accent-hover)] disabled:opacity-50 cursor-pointer shrink-0"
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{rerunning ? "Starting…" : "Re-run"}</span>
                </button>
              </div>

              {rerunError && (
                <p className="text-xs text-[var(--danger)] m-0">{rerunError}</p>
              )}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
