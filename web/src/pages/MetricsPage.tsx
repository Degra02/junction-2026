import { AlertCircle, RefreshCw } from "lucide-react";
import { MetricsTables } from "../components/MetricsTables";
import { useMetrics } from "../hooks/useMetrics";

export type MetricsPageProps = Record<string, never>;

export function MetricsPage(_props: Readonly<MetricsPageProps>) {
  const { metrics, stats, notPublishedYet, loading, error, refresh } = useMetrics();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5 max-w-[75ch]">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--fg-primary)] m-0">
            Evaluation, Hard-Negative FPR &amp; Calibration
          </h1>
          <p className="text-sm text-[var(--fg-secondary)] leading-relaxed m-0">
            Measured exclusively on third-party ground-truth labels (ClaimReview fact-checkers, EUvsDisinfo, VIGINUM Portal Kombat, wire agencies, satire, and opinion desks) — never self-labelled. Every rate shows its 95% Wilson confidence interval alongside the share of items that received a score (coverage).
          </p>
        </div>

        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] text-xs font-medium text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] hover:bg-[var(--bg-subtle)] disabled:opacity-50 cursor-pointer"
        >
          <RefreshCw className={loading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} aria-hidden="true" />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-xl border border-[var(--danger-border)] bg-[var(--danger-soft)] p-4 text-xs sm:text-sm text-[var(--danger)]"
        >
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {loading && !metrics && !stats ? (
        <div className="space-y-4" aria-busy="true">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-24 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-subtle)] animate-pulse"
              />
            ))}
          </div>
          <div className="h-64 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-subtle)] animate-pulse" />
        </div>
      ) : (
        <MetricsTables
          metrics={metrics}
          stats={stats}
          notPublishedYet={notPublishedYet}
        />
      )}
    </div>
  );
}
