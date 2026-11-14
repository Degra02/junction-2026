import { RefreshCw } from "lucide-react";
import { MetricsTables } from "../components/MetricsTables";
import { useMetrics } from "../hooks/useMetrics";
import { buttonClass } from "../lib/ui";
import { cn } from "../lib/utils";

export type MetricsPageProps = Record<string, never>;

export function MetricsPage(_props: Readonly<MetricsPageProps>) {
  const { metrics, stats, notPublishedYet, loading, error, refresh } = useMetrics();

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="display text-3xl text-[var(--fg-primary)]">Benchmarks</h1>
          <p className="text-sm text-[var(--fg-secondary)]">
            Third-party labels only, with 95% Wilson intervals and coverage.
          </p>
        </div>
        <button type="button" onClick={refresh} disabled={loading} className={buttonClass("secondary", "md")}>
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} aria-hidden="true" />
          Refresh
        </button>
      </header>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-[var(--danger-border)] bg-[var(--danger-soft)] px-3 py-2 text-[13px] text-[var(--danger)]"
        >
          {error}
        </p>
      )}

      {loading && !metrics && !stats ? (
        <div className="space-y-6" aria-busy="true">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="space-y-2">
                <div className="h-3 w-20 rounded-md bg-[var(--bg-subtle)] animate-pulse" />
                <div className="h-8 w-24 rounded-md bg-[var(--bg-subtle)] animate-pulse" />
              </div>
            ))}
          </div>
          <div className="h-64 rounded-xl bg-[var(--bg-subtle)] animate-pulse" />
        </div>
      ) : (
        <MetricsTables metrics={metrics} stats={stats} notPublishedYet={notPublishedYet} />
      )}
    </div>
  );
}
