import type {
  BinaryMetrics,
  CalibrationBin,
  DimensionKey,
  DimensionMetrics,
  Family,
  MetricsPayload,
  Stats,
} from "../lib/contracts";
import { formatCi, formatDurationMs, formatPct } from "../lib/format";
import {
  DIMENSION_META,
  FAMILY_LABELS,
  SET_LABELS,
  STAGE_LABELS,
  languageName,
} from "../lib/labels";

function RateCell({
  rate,
  ci,
  coverage,
  coverageLabel = "cov",
}: Readonly<{
  rate: number | null;
  ci?: readonly [number, number] | null;
  coverage?: number | null;
  coverageLabel?: string;
}>) {
  if (rate === null || rate === undefined) {
    return (
      <div className="space-y-0.5">
        <span className="font-mono-num text-xs text-[var(--fg-muted)]">n/a</span>
        {coverage !== undefined && coverage !== null && (
          <div className="font-mono-num text-[10px] text-[var(--fg-muted)]">
            {coverageLabel} {formatPct(coverage, 0)}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      <div className="font-mono-num text-xs font-semibold text-[var(--fg-primary)]">
        {formatPct(rate, 1)}
      </div>
      {ci && (
        <div className="font-mono-num text-[10px] text-[var(--fg-muted)]">{formatCi(ci, 0)}</div>
      )}
      {coverage !== undefined && coverage !== null && (
        <div className="font-mono-num text-[10px] text-[var(--fg-secondary)]">
          {coverageLabel} {formatPct(coverage, 0)}
        </div>
      )}
    </div>
  );
}

function CalibrationChart({ bins }: Readonly<{ bins: readonly CalibrationBin[] }>) {
  if (bins.length === 0) {
    return (
      <p className="text-xs text-[var(--fg-muted)] m-0">
        No scored items available yet for reliability binning.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
      <svg
        viewBox="0 0 280 220"
        className="w-full max-w-[300px] h-auto"
        role="img"
        aria-label="Reliability calibration diagram comparing mean predicted confidence to observed positive rate"
      >
        {/* Axes */}
        <line
          x1="40"
          y1="20"
          x2="40"
          y2="180"
          stroke="var(--border-strong)"
          strokeWidth="1"
        />
        <line
          x1="40"
          y1="180"
          x2="250"
          y2="180"
          stroke="var(--border-strong)"
          strokeWidth="1"
        />
        {/* Diagonal ideal calibration line */}
        <line
          x1="40"
          y1="180"
          x2="250"
          y2="20"
          stroke="var(--fg-muted)"
          strokeDasharray="4 3"
          strokeWidth="1"
        />
        <text x="40" y="198" fontSize="10" fill="var(--fg-muted)">
          0%
        </text>
        <text x="132" y="198" fontSize="10" fill="var(--fg-muted)">
          Predicted
        </text>
        <text x="232" y="198" fontSize="10" fill="var(--fg-muted)">
          100%
        </text>
        <text x="8" y="26" fontSize="10" fill="var(--fg-muted)">
          100%
        </text>
        <text x="14" y="180" fontSize="10" fill="var(--fg-muted)">
          0%
        </text>

        {bins.map((b, idx) => {
          if (b.mean_confidence == null || b.positive_rate == null) return null;
          const cx = 40 + b.mean_confidence * 210;
          const cy = 180 - b.positive_rate * 160;
          const r = Math.max(4, Math.min(10, 3 + Math.sqrt(b.n)));
          return (
            <g key={idx}>
              <circle
                cx={cx}
                cy={cy}
                r={r}
                fill="var(--accent)"
                fillOpacity="0.85"
              />
              <title>
                Bin [{formatPct(b.bin[0], 0)}–{formatPct(b.bin[1], 0)}]: predicted{" "}
                {formatPct(b.mean_confidence, 1)}, observed {formatPct(b.positive_rate, 1)} (n={b.n})
              </title>
            </g>
          );
        })}
      </svg>

      <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-b border-[var(--border-subtle)]">
              <th className="py-2 px-3 font-semibold">Confidence bin</th>
              <th className="py-2 px-3 font-semibold">Mean score</th>
              <th className="py-2 px-3 font-semibold">Observed +</th>
              <th className="py-2 px-3 font-semibold">Items</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-subtle)]">
            {bins.map((b, idx) => (
              <tr key={idx} className="bg-[var(--bg-surface)] font-mono-num">
                <td className="py-1.5 px-3 text-[var(--fg-primary)]">
                  [{formatPct(b.bin[0], 0)}, {formatPct(b.bin[1], 0)}]
                </td>
                <td className="py-1.5 px-3 text-[var(--fg-secondary)]">
                  {formatPct(b.mean_confidence, 1)}
                </td>
                <td className="py-1.5 px-3 font-semibold text-[var(--fg-primary)]">
                  {formatPct(b.positive_rate, 1)}
                </td>
                <td className="py-1.5 px-3 text-[var(--fg-muted)]">{b.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MetricsRowCells({ m }: Readonly<{ m: BinaryMetrics }>) {
  return (
    <>
      <td className="py-2.5 px-3 font-mono-num text-xs text-[var(--fg-muted)]">
        +{m.positives} / −{m.negatives}
      </td>
      <td className="py-2.5 px-3">
        <RateCell rate={m.precision} ci={m.precision_ci} coverage={m.coverage} />
      </td>
      <td className="py-2.5 px-3">
        <RateCell rate={m.recall} ci={m.recall_ci} coverage={m.coverage_pos} coverageLabel="pos cov" />
      </td>
      <td className="py-2.5 px-3">
        <RateCell rate={m.recall_all} ci={m.recall_all_ci} />
      </td>
      <td className="py-2.5 px-3">
        <RateCell rate={m.fpr} ci={m.fpr_ci} coverage={m.coverage_neg} coverageLabel="neg cov" />
      </td>
      <td className="py-2.5 px-3 font-mono-num text-xs text-[var(--fg-secondary)]">
        {formatPct(m.abstain_rate, 1)}
      </td>
      <td className="py-2.5 px-3 font-mono-num text-xs text-[var(--fg-muted)]">
        {formatPct(m.failure_rate, 1)}
      </td>
    </>
  );
}

function DimensionSection({
  dimension,
  data,
}: Readonly<{
  dimension: DimensionKey;
  data: DimensionMetrics;
}>) {
  const meta = DIMENSION_META[dimension];
  const setEntries = Object.entries(data.per_set);
  const ablationEntries = Object.entries(data.ablation);
  const langEntries = Object.entries(data.per_language);

  return (
    <section
      aria-labelledby={`metrics-${dimension}`}
      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 space-y-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 pb-3 border-b border-[var(--border-subtle)]">
        <div>
          <h2 id={`metrics-${dimension}`} className="text-base font-bold text-[var(--fg-primary)] m-0">
            {meta.title} ({meta.shortTitle})
          </h2>
          <p className="text-xs text-[var(--fg-secondary)] m-0 mt-0.5">{meta.subtitle}</p>
        </div>
        {data.missing > 0 && (
          <span className="font-mono-num text-xs text-[var(--caution)]">
            {data.missing} labelled items pending
          </span>
        )}
      </div>

      {/* Overall + Per-Set (including Hard Negatives) */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-secondary)] m-0">
          Overall &amp; per-dataset breakdown (with Wilson 95% intervals &amp; scored coverage)
        </h3>
        <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-b border-[var(--border-subtle)]">
                <th className="py-2 px-3 font-semibold">Labelled set</th>
                <th className="py-2 px-3 font-semibold">Labels (+/−)</th>
                <th className="py-2 px-3 font-semibold">Precision (scored)</th>
                <th className="py-2 px-3 font-semibold">Recall (scored)</th>
                <th className="py-2 px-3 font-semibold">Recall (all)</th>
                <th className="py-2 px-3 font-semibold">False-Positive Rate</th>
                <th className="py-2 px-3 font-semibold">Abstain</th>
                <th className="py-2 px-3 font-semibold">Failed</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-subtle)]">
              <tr className="bg-[var(--accent-soft)]/35 font-medium">
                <td className="py-2.5 px-3 font-bold text-[var(--fg-primary)]">Overall</td>
                <MetricsRowCells m={data.overall} />
              </tr>
              {setEntries.map(([setName, m]) => {
                const info = SET_LABELS[setName];
                return (
                  <tr key={setName} className="bg-[var(--bg-surface)]">
                    <td className="py-2.5 px-3">
                      <div className="font-medium text-[var(--fg-primary)]">
                        {info?.label ?? setName}
                      </div>
                      <div className="font-mono-num text-[10px] text-[var(--fg-muted)]">{setName}</div>
                    </td>
                    <MetricsRowCells m={m} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Calibration */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-secondary)] m-0">
          Reliability &amp; calibration
        </h3>
        <CalibrationChart bins={data.calibration} />
      </div>

      {/* Family Ablation */}
      {ablationEntries.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-secondary)] m-0">
            Signal family ablation (re-scored without each family)
          </h3>
          <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-b border-[var(--border-subtle)]">
                  <th className="py-2 px-3 font-semibold">Ablated configuration</th>
                  <th className="py-2 px-3 font-semibold">Labels (+/−)</th>
                  <th className="py-2 px-3 font-semibold">Precision</th>
                  <th className="py-2 px-3 font-semibold">Recall (scored)</th>
                  <th className="py-2 px-3 font-semibold">Recall (all)</th>
                  <th className="py-2 px-3 font-semibold">FPR</th>
                  <th className="py-2 px-3 font-semibold">Abstain</th>
                  <th className="py-2 px-3 font-semibold">Failed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {ablationEntries.map(([key, m]) => {
                  const rawFam = key.replace(/^without_/, "") as Family;
                  const famName = FAMILY_LABELS[rawFam]?.name ?? rawFam;
                  return (
                    <tr key={key} className="bg-[var(--bg-surface)]">
                      <td className="py-2.5 px-3 font-medium text-[var(--fg-primary)]">
                        Without {famName}
                      </td>
                      <MetricsRowCells m={m} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Per-language */}
      {langEntries.length > 0 && (
        <details className="group rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)]">
          <summary className="px-3.5 py-2.5 text-xs font-semibold text-[var(--fg-secondary)] cursor-pointer select-none">
            Per-language breakdown ({langEntries.length} languages)
          </summary>
          <div className="overflow-x-auto border-t border-[var(--border-subtle)]">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-b border-[var(--border-subtle)]">
                  <th className="py-2 px-3 font-semibold">Language</th>
                  <th className="py-2 px-3 font-semibold">Labels (+/−)</th>
                  <th className="py-2 px-3 font-semibold">Precision</th>
                  <th className="py-2 px-3 font-semibold">Recall (scored)</th>
                  <th className="py-2 px-3 font-semibold">Recall (all)</th>
                  <th className="py-2 px-3 font-semibold">FPR</th>
                  <th className="py-2 px-3 font-semibold">Abstain</th>
                  <th className="py-2 px-3 font-semibold">Failed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {langEntries.map(([lang, m]) => (
                  <tr key={lang} className="bg-[var(--bg-surface)]">
                    <td className="py-2 px-3 font-medium text-[var(--fg-primary)]">
                      {languageName(lang)}{" "}
                      <span className="font-mono-num text-[var(--fg-muted)]">({lang})</span>
                    </td>
                    <MetricsRowCells m={m} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  );
}

export interface MetricsTablesProps {
  readonly metrics: MetricsPayload | null;
  readonly stats: Stats | null;
  readonly notPublishedYet: boolean;
}

export function MetricsTables({
  metrics,
  stats,
  notPublishedYet,
}: Readonly<MetricsTablesProps>) {
  return (
    <div className="space-y-6">
      {notPublishedYet || !metrics ? (
        <section className="rounded-xl border border-[var(--caution-border)] bg-[var(--caution-soft)] p-5 space-y-2">
          <h2 className="text-base font-bold text-[var(--fg-primary)] m-0">
            Evaluation metrics coming — benchmark run in progress
          </h2>
          <p className="text-xs sm:text-sm text-[var(--fg-secondary)] leading-relaxed m-0 max-w-[80ch]">
            <code>/api/metrics</code> has not published <code>evals/metrics.json</code> yet. Our 284-item benchmark across 12 languages (ClaimReview debunks, EUvsDisinfo cases, VIGINUM Portal Kombat articles, and hard-negative sets for fact-checks, wire copy, press releases, satire, op-eds, and emotional reporting) reports Wilson 95% intervals and coverage as soon as the evaluation run completes. No placeholder numbers are shown.
          </p>
        </section>
      ) : (
        <>
          {/* Summary KPI strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
              <div className="text-xs text-[var(--fg-muted)]">Third-party labelled items</div>
              <div className="font-mono-num text-2xl font-bold text-[var(--fg-primary)] mt-1">
                {metrics.items}
              </div>
              <div className="text-[11px] text-[var(--fg-secondary)] mt-0.5">
                Decision threshold {formatPct(metrics.threshold, 0)}
              </div>
            </div>

            {(["single", "coordinated"] as const).map((dim) => {
              const fit = metrics.fit[dim];
              return (
                <div
                  key={dim}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4"
                >
                  <div className="text-xs text-[var(--fg-muted)]">
                    {DIMENSION_META[dim].shortTitle} CV fit
                  </div>
                  <div className="font-mono-num text-2xl font-bold text-[var(--fg-primary)] mt-1">
                    {fit?.auc != null ? `AUC ${fit.auc.toFixed(3)}` : "Prior weights"}
                  </div>
                  <div className="font-mono-num text-[11px] text-[var(--fg-secondary)] mt-0.5">
                    {fit
                      ? `n=${fit.n} · Brier ${fit.brier?.toFixed(3) ?? "n/a"}`
                      : "n=0 (unfitted priors)"}
                  </div>
                </div>
              );
            })}

            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
              <div className="text-xs text-[var(--fg-muted)]">Evaluated pipeline build</div>
              <div className="font-mono-num text-sm font-bold text-[var(--fg-primary)] mt-2 truncate">
                {metrics.pipeline_versions.join(", ") || "current"}
              </div>
              <div className="text-[11px] text-[var(--fg-secondary)] mt-1">
                Abstentions tracked as coverage, never wins
              </div>
            </div>
          </div>

          {/* Headline with & without label-shared family */}
          {Object.keys(metrics.headline).length > 0 && (
            <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 space-y-3">
              <div className="space-y-1">
                <h2 className="text-base font-bold text-[var(--fg-primary)] m-0">
                  Headline results — with &amp; without label-source families
                </h2>
                <p className="text-xs text-[var(--fg-secondary)] m-0 max-w-[85ch]">
                  VIGINUM’s domain list defines the <code>viginum_pravda</code> ground-truth labels and also powers <code>known_networks</code>; ClaimReview defines <code>fact_checker_debunk</code> and powers <code>fact_checks</code>. To prevent circular inflation, we report each dimension both with all signals and with that label-shared family removed.
                </p>
              </div>

              <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-b border-[var(--border-subtle)]">
                      <th className="py-2 px-3 font-semibold">Slice &amp; configuration</th>
                      <th className="py-2 px-3 font-semibold">Precision (scored)</th>
                      <th className="py-2 px-3 font-semibold">Recall (scored)</th>
                      <th className="py-2 px-3 font-semibold">FPR (scored)</th>
                      <th className="py-2 px-3 font-semibold">Abstain</th>
                      <th className="py-2 px-3 font-semibold">CV AUC (refit)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-subtle)]">
                    {Object.entries(metrics.headline).flatMap(([sliceKey, entry]) => {
                      const famLabel =
                        FAMILY_LABELS[entry.family_removed as Family]?.name ?? entry.family_removed;
                      const rows = [
                        {
                          rowKey: `${sliceKey}-with`,
                          title: `${sliceKey} — Full pipeline`,
                          m: entry.with,
                          auc: entry.fit?.auc ?? null,
                        },
                      ];
                      if (entry.without) {
                        rows.push({
                          rowKey: `${sliceKey}-without`,
                          title: `${sliceKey} — Without ${famLabel}`,
                          m: entry.without,
                          auc: entry.fit?.auc_without ?? null,
                        });
                      }
                      return rows.map((r) => (
                        <tr key={r.rowKey} className="bg-[var(--bg-surface)]">
                          <td className="py-2.5 px-3 font-medium text-[var(--fg-primary)]">
                            {r.title}
                          </td>
                          <td className="py-2.5 px-3">
                            <RateCell
                              rate={r.m.precision}
                              ci={r.m.precision_ci}
                              coverage={r.m.coverage}
                            />
                          </td>
                          <td className="py-2.5 px-3">
                            <RateCell
                              rate={r.m.recall}
                              ci={r.m.recall_ci}
                              coverage={r.m.coverage_pos}
                              coverageLabel="pos cov"
                            />
                          </td>
                          <td className="py-2.5 px-3">
                            <RateCell
                              rate={r.m.fpr}
                              ci={r.m.fpr_ci}
                              coverage={r.m.coverage_neg}
                              coverageLabel="neg cov"
                            />
                          </td>
                          <td className="py-2.5 px-3 font-mono-num text-xs text-[var(--fg-secondary)]">
                            {formatPct(r.m.abstain_rate, 1)}
                          </td>
                          <td className="py-2.5 px-3 font-mono-num text-xs text-[var(--fg-primary)]">
                            {r.auc != null ? r.auc.toFixed(3) : "—"}
                          </td>
                        </tr>
                      ));
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {metrics.dimensions.single && (
            <DimensionSection dimension="single" data={metrics.dimensions.single} />
          )}
          {metrics.dimensions.coordinated && (
            <DimensionSection dimension="coordinated" data={metrics.dimensions.coordinated} />
          )}
        </>
      )}

      {/* Live VPS runtime stats (`GET /api/stats`) */}
      {stats && (
        <section
          aria-labelledby="runtime-stats-heading"
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 space-y-4"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2 pb-3 border-b border-[var(--border-subtle)]">
            <div>
              <h2 id="runtime-stats-heading" className="text-base font-bold text-[var(--fg-primary)] m-0">
                Live VPS throughput &amp; per-stage latency
              </h2>
              <p className="text-xs text-[var(--fg-secondary)] m-0 mt-0.5">
                Measured over stored runs on Hostinger KVM 2 (2 vCPU, 8 GB RAM, CPU-only inference).
              </p>
            </div>
            <div className="flex items-center gap-4 font-mono-num text-xs text-[var(--fg-secondary)]">
              <span>{stats.submissions} submissions</span>
              <span>
                {stats.submissions > 0
                  ? `${formatPct(stats.cache_hits / stats.submissions, 0)} cache hit rate`
                  : "0 cache hits"}
              </span>
              {stats.analysis_ms && (
                <span>
                  total p50 {formatDurationMs(stats.analysis_ms.p50)} / p95{" "}
                  {formatDurationMs(stats.analysis_ms.p95)}
                </span>
              )}
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-[var(--bg-subtle)] text-[var(--fg-secondary)] border-b border-[var(--border-subtle)]">
                  <th className="py-2 px-3 font-semibold">Stage</th>
                  <th className="py-2 px-3 font-semibold">Completed</th>
                  <th className="py-2 px-3 font-semibold">Skipped</th>
                  <th className="py-2 px-3 font-semibold">Failed</th>
                  <th className="py-2 px-3 font-semibold">Latency p50</th>
                  <th className="py-2 px-3 font-semibold">Latency p95</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {stats.stages.map((st) => (
                  <tr key={st.name} className="bg-[var(--bg-surface)]">
                    <td className="py-2 px-3">
                      <span className="font-mono-num font-semibold text-[var(--fg-primary)]">
                        {st.name}
                      </span>
                      <span className="text-[var(--fg-muted)] ml-2">
                        {STAGE_LABELS[st.name]?.label}
                      </span>
                    </td>
                    <td className="py-2 px-3 font-mono-num text-[var(--fg-primary)]">{st.done}</td>
                    <td className="py-2 px-3 font-mono-num text-[var(--fg-muted)]">{st.skipped}</td>
                    <td className="py-2 px-3 font-mono-num text-[var(--fg-muted)]">{st.failed}</td>
                    <td className="py-2 px-3 font-mono-num text-[var(--fg-secondary)]">
                      {formatDurationMs(st.duration_ms?.p50)}
                    </td>
                    <td className="py-2 px-3 font-mono-num text-[var(--fg-secondary)]">
                      {formatDurationMs(st.duration_ms?.p95)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
