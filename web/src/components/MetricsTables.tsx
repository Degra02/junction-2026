import type { ReactNode } from "react";
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
import { cn } from "../lib/utils";
import { AnimatedNumber } from "./ui/AnimatedNumber";

const SERIES_COLOR: Record<DimensionKey, string> = {
  single: "var(--accent)",
  coordinated: "var(--indigo)",
};

const TH = "sticky top-0 z-[1] bg-[var(--bg-subtle)] py-2 px-3 text-xs font-medium text-[var(--fg-muted)] whitespace-nowrap";
const TH_NUM = cn(TH, "text-right");
const TD = "py-2 px-3 align-top";
const TD_NUM = "py-2 px-3 align-top text-right font-mono-num text-xs whitespace-nowrap";

/** Bordered, scrollable table shell with a sticky header row. */
function DataTable({
  head,
  children,
  className,
}: Readonly<{ head: ReactNode; children: ReactNode; className?: string }>) {
  return (
    <div className={cn("editorial-card rounded-xl overflow-auto max-h-[32rem]", className)}>
      <table className="w-full border-collapse text-left text-[13px]">
        <thead>
          <tr className="border-b border-[var(--border-subtle)]">{head}</tr>
        </thead>
        <tbody className="divide-y divide-[var(--border-subtle)]">{children}</tbody>
      </table>
    </div>
  );
}

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
  return (
    <td className={TD_NUM}>
      <div className={rate == null ? "text-[var(--fg-muted)]" : "text-[var(--fg-primary)]"}>
        {formatPct(rate, 1)}
      </div>
      {rate != null && ci && <div className="text-[11px] text-[var(--fg-muted)]">{formatCi(ci, 0)}</div>}
      {coverage != null && (
        <div className="text-[11px] text-[var(--fg-muted)]">
          {coverageLabel} {formatPct(coverage, 0)}
        </div>
      )}
    </td>
  );
}

const RATE_HEAD = (
  <>
    <th className={TH_NUM}>+ / −</th>
    <th className={TH_NUM}>Precision</th>
    <th className={TH_NUM}>Recall</th>
    <th className={TH_NUM}>Recall (all)</th>
    <th className={TH_NUM}>FPR</th>
    <th className={TH_NUM}>Abstain</th>
    <th className={TH_NUM}>Failed</th>
  </>
);

function MetricsRowCells({ m }: Readonly<{ m: BinaryMetrics }>) {
  return (
    <>
      <td className={cn(TD_NUM, "text-[var(--fg-muted)]")}>
        {m.positives} / {m.negatives}
      </td>
      <RateCell rate={m.precision} ci={m.precision_ci} coverage={m.coverage} />
      <RateCell rate={m.recall} ci={m.recall_ci} coverage={m.coverage_pos} coverageLabel="pos" />
      <RateCell rate={m.recall_all} ci={m.recall_all_ci} />
      <RateCell rate={m.fpr} ci={m.fpr_ci} coverage={m.coverage_neg} coverageLabel="neg" />
      <td className={cn(TD_NUM, "text-[var(--fg-secondary)]")}>{formatPct(m.abstain_rate, 1)}</td>
      <td className={cn(TD_NUM, "text-[var(--fg-muted)]")}>{formatPct(m.failure_rate, 1)}</td>
    </>
  );
}

function CalibrationChart({
  bins,
  color,
}: Readonly<{ bins: readonly CalibrationBin[]; color: string }>) {
  if (bins.length === 0) {
    return <p className="text-[13px] text-[var(--fg-muted)]">No scored items yet.</p>;
  }

  const x0 = 36;
  const x1 = 256;
  const y0 = 184;
  const y1 = 16;
  const px = (p: number) => x0 + p * (x1 - x0);
  const py = (p: number) => y0 - p * (y0 - y1);
  const ticks = [0, 0.5, 1];

  return (
    <div className="editorial-card rounded-xl grid grid-cols-1 md:grid-cols-[minmax(0,18rem)_minmax(0,1fr)] items-start">
      <svg
        viewBox="0 0 272 216"
        className="w-full max-w-[18rem] h-auto p-3"
        role="img"
        aria-label="Calibration: mean predicted confidence against observed positive rate"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={px(t)} y1={y1} x2={px(t)} y2={y0} stroke="var(--border-subtle)" />
            <line x1={x0} y1={py(t)} x2={x1} y2={py(t)} stroke="var(--border-subtle)" />
            <text
              x={px(t)}
              y={y0 + 14}
              textAnchor="middle"
              fontSize="10"
              fontFamily="var(--font-mono)"
              fill="var(--fg-muted)"
            >
              {Math.round(t * 100)}
            </text>
            <text
              x={x0 - 6}
              y={py(t) + 3}
              textAnchor="end"
              fontSize="10"
              fontFamily="var(--font-mono)"
              fill="var(--fg-muted)"
            >
              {Math.round(t * 100)}
            </text>
          </g>
        ))}
        <line
          x1={px(0)}
          y1={py(0)}
          x2={px(1)}
          y2={py(1)}
          stroke="var(--border-strong)"
          strokeDasharray="3 3"
        />
        <text x={(x0 + x1) / 2} y={y0 + 28} textAnchor="middle" fontSize="10" fill="var(--fg-muted)">
          predicted %
        </text>
        <text
          x={10}
          y={(y0 + y1) / 2}
          textAnchor="middle"
          fontSize="10"
          fill="var(--fg-muted)"
          transform={`rotate(-90 10 ${(y0 + y1) / 2})`}
        >
          observed %
        </text>
        {bins.map((b, idx) => {
          if (b.mean_confidence == null || b.positive_rate == null) return null;
          const r = Math.max(3, Math.min(8, 2 + Math.sqrt(b.n)));
          return (
            <circle
              key={idx}
              cx={px(b.mean_confidence)}
              cy={py(b.positive_rate)}
              r={r}
              fill={color}
              fillOpacity="0.85"
            >
              <title>
                {formatPct(b.bin[0], 0)}–{formatPct(b.bin[1], 0)}: predicted {formatPct(b.mean_confidence, 1)},
                observed {formatPct(b.positive_rate, 1)}, n={b.n}
              </title>
            </circle>
          );
        })}
      </svg>

      <div className="overflow-auto md:border-l border-t md:border-t-0 border-[var(--border-subtle)]">
        <table className="w-full border-collapse text-left text-[13px]">
          <thead>
            <tr className="border-b border-[var(--border-subtle)]">
              <th className={TH}>Bin</th>
              <th className={TH_NUM}>Predicted</th>
              <th className={TH_NUM}>Observed</th>
              <th className={TH_NUM}>n</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-subtle)]">
            {bins.map((b, idx) => (
              <tr key={idx}>
                <td className={cn(TD, "font-mono-num text-xs text-[var(--fg-secondary)] whitespace-nowrap")}>
                  {formatPct(b.bin[0], 0)}–{formatPct(b.bin[1], 0)}
                </td>
                <td className={cn(TD_NUM, "text-[var(--fg-secondary)]")}>{formatPct(b.mean_confidence, 1)}</td>
                <td className={cn(TD_NUM, "text-[var(--fg-primary)]")}>{formatPct(b.positive_rate, 1)}</td>
                <td className={cn(TD_NUM, "text-[var(--fg-muted)]")}>{b.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SubSection({ title, children }: Readonly<{ title: string; children: ReactNode }>) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-[var(--fg-primary)]">{title}</h3>
      {children}
    </div>
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
    <section aria-labelledby={`metrics-${dimension}`} className="space-y-5 pt-6 border-t border-[var(--border-subtle)]">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 id={`metrics-${dimension}`} className="display text-xl text-[var(--fg-primary)]">
            {meta.shortTitle}
          </h2>
          <p className="text-[13px] text-[var(--fg-muted)] mt-0.5">{meta.subtitle}</p>
        </div>
        {data.missing > 0 && (
          <span className="font-mono-num text-xs text-[var(--caution)]">{data.missing} pending</span>
        )}
      </div>

      <SubSection title="By dataset">
        <DataTable
          head={
            <>
              <th className={TH}>Set</th>
              {RATE_HEAD}
            </>
          }
        >
          <tr className="bg-[var(--bg-subtle)]/50">
            <td className={cn(TD, "font-medium text-[var(--fg-primary)]")}>Overall</td>
            <MetricsRowCells m={data.overall} />
          </tr>
          {setEntries.map(([setName, m]) => (
            <tr key={setName}>
              <td className={TD}>
                <div className="text-[var(--fg-primary)]">{SET_LABELS[setName]?.label ?? setName}</div>
                <div className="font-mono-num text-[11px] text-[var(--fg-muted)]">{setName}</div>
              </td>
              <MetricsRowCells m={m} />
            </tr>
          ))}
        </DataTable>
      </SubSection>

      <SubSection title="Calibration">
        <CalibrationChart bins={data.calibration} color={SERIES_COLOR[dimension]} />
      </SubSection>

      {ablationEntries.length > 0 && (
        <SubSection title="Ablation">
          <DataTable
            head={
              <>
                <th className={TH}>Without</th>
                {RATE_HEAD}
              </>
            }
          >
            {ablationEntries.map(([key, m]) => {
              const fam = key.replace(/^without_/, "") as Family;
              return (
                <tr key={key}>
                  <td className={cn(TD, "text-[var(--fg-primary)]")}>{FAMILY_LABELS[fam]?.name ?? fam}</td>
                  <MetricsRowCells m={m} />
                </tr>
              );
            })}
          </DataTable>
        </SubSection>
      )}

      {langEntries.length > 0 && (
        <details className="group space-y-2">
          <summary className="cursor-pointer select-none text-sm font-medium text-[var(--fg-primary)]">
            By language <span className="font-mono-num text-xs text-[var(--fg-muted)]">{langEntries.length}</span>
          </summary>
          <DataTable
            className="mt-2"
            head={
              <>
                <th className={TH}>Language</th>
                {RATE_HEAD}
              </>
            }
          >
            {langEntries.map(([lang, m]) => (
              <tr key={lang}>
                <td className={cn(TD, "text-[var(--fg-primary)] whitespace-nowrap")}>
                  {languageName(lang)} <span className="font-mono-num text-xs text-[var(--fg-muted)]">{lang}</span>
                </td>
                <MetricsRowCells m={m} />
              </tr>
            ))}
          </DataTable>
        </details>
      )}
    </section>
  );
}

function Stat({
  label,
  children,
  sub,
}: Readonly<{ label: string; children: ReactNode; sub?: ReactNode }>) {
  return (
    <div className="min-w-0 py-1 sm:px-5 sm:first:pl-0">
      <dt className="text-xs text-[var(--fg-muted)]">{label}</dt>
      <dd className="mt-1 text-3xl font-semibold tracking-tight tabular text-[var(--fg-primary)] truncate">
        {children}
      </dd>
      {sub && <dd className="mt-0.5 font-mono-num text-xs text-[var(--fg-muted)] truncate">{sub}</dd>}
    </div>
  );
}

const formatInt = (n: number) => String(Math.round(n));
const formatAuc = (n: number) => n.toFixed(3);

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
    <div className="space-y-8">
      {!metrics ? (
        notPublishedYet && (
        <section className="editorial-card rounded-xl p-4 sm:p-5 space-y-1">
          <h2 className="text-sm font-medium text-[var(--fg-primary)]">Not published yet</h2>
          <p className="text-[13px] text-[var(--fg-secondary)]">
            Results appear here when the benchmark run publishes{" "}
            <code className="font-mono-num text-xs">evals/metrics.json</code>.
          </p>
        </section>
        )
      ) : (
        <>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-y-4 sm:divide-x divide-[var(--border-subtle)]">
            <Stat label="Labelled items" sub={`threshold ${formatPct(metrics.threshold, 0)}`}>
              <AnimatedNumber value={metrics.items} format={formatInt} />
            </Stat>
            {(["single", "coordinated"] as const).map((dim) => {
              const fit = metrics.fit[dim];
              return (
                <Stat
                  key={dim}
                  label={`${DIMENSION_META[dim].shortTitle} AUC`}
                  sub={fit ? `n=${fit.n} · Brier ${fit.brier?.toFixed(3) ?? "n/a"}` : "prior weights"}
                >
                  {fit?.auc != null ? <AnimatedNumber value={fit.auc} format={formatAuc} /> : "—"}
                </Stat>
              );
            })}
            <Stat label="Pipeline">
              <span className="font-mono-num text-base font-medium">
                {metrics.pipeline_versions.join(", ") || "current"}
              </span>
            </Stat>
          </dl>

          {Object.keys(metrics.headline).length > 0 && (
            <SubSection title="Headline">
              <p className="text-[13px] text-[var(--fg-muted)]">
                Each slice with and without the family that shares its label source.
              </p>
              <DataTable
                head={
                  <>
                    <th className={TH}>Slice</th>
                    <th className={TH_NUM}>Precision</th>
                    <th className={TH_NUM}>Recall</th>
                    <th className={TH_NUM}>FPR</th>
                    <th className={TH_NUM}>Abstain</th>
                    <th className={TH_NUM}>CV AUC</th>
                  </>
                }
              >
                {Object.entries(metrics.headline).flatMap(([sliceKey, entry]) => {
                  const famLabel =
                    FAMILY_LABELS[entry.family_removed as Family]?.name ?? entry.family_removed;
                  const rows: { rowKey: string; variant: string; m: BinaryMetrics; auc: number | null }[] = [
                    { rowKey: `${sliceKey}-with`, variant: "all signals", m: entry.with, auc: entry.fit?.auc ?? null },
                  ];
                  if (entry.without) {
                    rows.push({
                      rowKey: `${sliceKey}-without`,
                      variant: `without ${famLabel}`,
                      m: entry.without,
                      auc: entry.fit?.auc_without ?? null,
                    });
                  }
                  return rows.map((r) => (
                    <tr key={r.rowKey}>
                      <td className={TD}>
                        <span className="font-mono-num text-xs text-[var(--fg-primary)]">{sliceKey}</span>{" "}
                        <span className="text-[var(--fg-muted)]">{r.variant}</span>
                      </td>
                      <RateCell rate={r.m.precision} ci={r.m.precision_ci} coverage={r.m.coverage} />
                      <RateCell rate={r.m.recall} ci={r.m.recall_ci} coverage={r.m.coverage_pos} coverageLabel="pos" />
                      <RateCell rate={r.m.fpr} ci={r.m.fpr_ci} coverage={r.m.coverage_neg} coverageLabel="neg" />
                      <td className={cn(TD_NUM, "text-[var(--fg-secondary)]")}>{formatPct(r.m.abstain_rate, 1)}</td>
                      <td className={cn(TD_NUM, "text-[var(--fg-primary)]")}>
                        {r.auc != null ? r.auc.toFixed(3) : "—"}
                      </td>
                    </tr>
                  ));
                })}
              </DataTable>
            </SubSection>
          )}

          {metrics.dimensions.single && (
            <DimensionSection dimension="single" data={metrics.dimensions.single} />
          )}
          {metrics.dimensions.coordinated && (
            <DimensionSection dimension="coordinated" data={metrics.dimensions.coordinated} />
          )}
        </>
      )}

      {stats && (
        <section
          aria-labelledby="runtime-stats-heading"
          className="space-y-3 pt-6 border-t border-[var(--border-subtle)]"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 id="runtime-stats-heading" className="display text-xl text-[var(--fg-primary)]">
                Runtime
              </h2>
              <p className="text-[13px] text-[var(--fg-muted)] mt-0.5">
                Stored runs on a 2 vCPU, 8 GB VPS, CPU only.
              </p>
            </div>
            <div className="flex flex-wrap gap-x-4 font-mono-num text-xs text-[var(--fg-secondary)]">
              <span>{stats.submissions} runs</span>
              <span>
                {stats.submissions > 0 ? formatPct(stats.cache_hits / stats.submissions, 0) : "0%"} cached
              </span>
              {stats.analysis_ms && (
                <span>
                  p50 {formatDurationMs(stats.analysis_ms.p50)} · p95 {formatDurationMs(stats.analysis_ms.p95)}
                </span>
              )}
            </div>
          </div>

          <DataTable
            head={
              <>
                <th className={TH}>Stage</th>
                <th className={TH_NUM}>Done</th>
                <th className={TH_NUM}>Skipped</th>
                <th className={TH_NUM}>Failed</th>
                <th className={TH_NUM}>p50</th>
                <th className={TH_NUM}>p95</th>
              </>
            }
          >
            {stats.stages.map((st) => (
              <tr key={st.name}>
                <td className={TD}>
                  <span className="font-mono-num text-xs text-[var(--fg-primary)]">{st.name}</span>
                  <span className="ml-2 text-[var(--fg-muted)]">{STAGE_LABELS[st.name]?.label}</span>
                </td>
                <td className={cn(TD_NUM, "text-[var(--fg-primary)]")}>{st.done}</td>
                <td className={cn(TD_NUM, "text-[var(--fg-muted)]")}>{st.skipped}</td>
                <td className={cn(TD_NUM, st.failed > 0 ? "text-[var(--danger)]" : "text-[var(--fg-muted)]")}>
                  {st.failed}
                </td>
                <td className={cn(TD_NUM, "text-[var(--fg-secondary)]")}>{formatDurationMs(st.duration_ms?.p50)}</td>
                <td className={cn(TD_NUM, "text-[var(--fg-secondary)]")}>{formatDurationMs(st.duration_ms?.p95)}</td>
              </tr>
            ))}
          </DataTable>
        </section>
      )}
    </div>
  );
}
