import { CheckCircle2, Circle, AlertTriangle, MinusCircle, Loader2, Clock } from "lucide-react";
import type { AnalysisStatus, Step } from "../lib/contracts";
import { formatDurationMs } from "../lib/format";
import { ALL_STAGES, STAGE_LABELS } from "../lib/labels";
import { cn } from "../lib/utils";

export interface PipelineStepperProps {
  readonly status: AnalysisStatus;
  readonly queuePosition?: number | null;
  readonly steps: readonly Step[];
  readonly isStreaming: boolean;
}

export function PipelineStepper({
  status,
  queuePosition,
  steps,
  isStreaming,
}: Readonly<PipelineStepperProps>) {
  const stepMap = new Map(steps.map((s) => [s.name, s]));
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

  return (
    <section
      aria-label="Pipeline execution trace"
      aria-live="polite"
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4 space-y-3"
    >
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-secondary)] m-0">
            Pipeline trace
          </h2>
          {isStreaming && (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[var(--accent-soft)] text-[11px] font-medium text-[var(--accent)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse" />
              Live
            </span>
          )}
        </div>
        <span className="text-xs font-mono-num text-[var(--fg-muted)]">
          {completedCount}/{ordered.length} stages
          {totalDurationMs > 0 ? ` · ${formatDurationMs(totalDurationMs)}` : ""}
        </span>
      </div>

      {status === "queued" && (
        <div className="flex items-center gap-2 rounded-lg border border-[var(--caution-border)] bg-[var(--caution-soft)] px-3 py-2 text-xs text-[var(--caution)]">
          <Clock className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            Waiting in worker queue
            {queuePosition != null ? ` (position #${queuePosition})` : ""}…
          </span>
        </div>
      )}

      <ol className="space-y-2 list-none p-0 m-0">
        {ordered.map((step) => {
          const meta = STAGE_LABELS[step.name];
          const isRunning = step.state === "running";
          const isDone = step.state === "done";
          const isFailed = step.state === "failed";
          const isSkipped = step.state === "skipped";

          return (
            <li
              key={step.name}
              className={cn(
                "rounded-lg px-2.5 py-2 transition-colors",
                isRunning && "bg-[var(--accent-soft)] border border-[var(--accent-border)]",
                isFailed && "bg-[var(--danger-soft)] border border-[var(--danger-border)]",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2 min-w-0">
                  <span className="mt-0.5 shrink-0">
                    {isDone && (
                      <CheckCircle2 className="h-4 w-4 text-[var(--teal)]" aria-hidden="true" />
                    )}
                    {isRunning && (
                      <Loader2
                        className="h-4 w-4 text-[var(--accent)] animate-spin"
                        aria-hidden="true"
                      />
                    )}
                    {isFailed && (
                      <AlertTriangle className="h-4 w-4 text-[var(--danger)]" aria-hidden="true" />
                    )}
                    {isSkipped && (
                      <MinusCircle className="h-4 w-4 text-[var(--fg-muted)]" aria-hidden="true" />
                    )}
                    {step.state === "pending" && (
                      <Circle className="h-4 w-4 text-[var(--border-strong)]" aria-hidden="true" />
                    )}
                  </span>

                  <div className="min-w-0 space-y-0.5">
                    <div
                      className={cn(
                        "text-xs font-medium leading-snug",
                        isRunning
                          ? "text-[var(--accent)] font-semibold"
                          : isDone
                            ? "text-[var(--fg-primary)]"
                            : isFailed
                              ? "text-[var(--danger)] font-semibold"
                              : "text-[var(--fg-muted)]",
                      )}
                    >
                      {isRunning ? meta.activeVerb : meta.label}
                    </div>

                    {step.detail && (
                      <p className="text-[11px] text-[var(--fg-secondary)] leading-snug m-0">
                        {step.detail}
                      </p>
                    )}

                    {step.error && (
                      <p className="text-[11px] text-[var(--danger)] leading-snug m-0 font-medium">
                        {step.error}
                      </p>
                    )}
                  </div>
                </div>

                <span className="text-[11px] font-mono-num text-[var(--fg-muted)] shrink-0">
                  {step.duration_ms != null
                    ? formatDurationMs(step.duration_ms)
                    : isSkipped
                      ? "skipped"
                      : ""}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
