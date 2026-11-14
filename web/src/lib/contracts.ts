import type { components } from "../../../contracts/ts/api";

export type Analysis = components["schemas"]["Analysis"];
export type AnalysisEvent = components["schemas"]["AnalysisEvent"];
export type AnalysisStatus = components["schemas"]["AnalysisStatus"];
export type Claim = components["schemas"]["Claim"];
export type ContextItem = components["schemas"]["ContextItem"];
export type Contribution = components["schemas"]["Contribution"];
export type Created = components["schemas"]["Created"];
export type DocumentData = components["schemas"]["Document"];
export type ErrorBody = components["schemas"]["ErrorBody"];
export type Evidence = components["schemas"]["Evidence"];
export type Explanation = components["schemas"]["Explanation"];
export type FactCheck = components["schemas"]["FactCheck"];
export type Family = components["schemas"]["Family"];
export type Health = components["schemas"]["Health"];
export type Input = components["schemas"]["Input"];
export type InputKind = components["schemas"]["InputKind"];
export type Language = components["schemas"]["Language"];
export type LanguageSupport = components["schemas"]["LanguageSupport"];
export type OutletType = components["schemas"]["OutletType"];
export type Percentiles = components["schemas"]["Percentiles"];
export type Reason = components["schemas"]["Reason"];
export type Score = components["schemas"]["Score"];
export type Scores = components["schemas"]["Scores"];
export type SearchQuery = components["schemas"]["SearchQuery"];
export type SourceProfile = components["schemas"]["SourceProfile"];
export type SourceRef = components["schemas"]["SourceRef"];
export type Span = components["schemas"]["Span"];
export type StageName = components["schemas"]["StageName"];
export type StageStats = components["schemas"]["StageStats"];
export type Stats = components["schemas"]["Stats"];
export type Step = components["schemas"]["Step"];
export type StepState = components["schemas"]["StepState"];
export type Topic = components["schemas"]["Topic"];

export type DimensionKey = "single" | "coordinated";

/**
 * Exact shape emitted by `evals/src/propaganda_eval/metrics.py:to_json()`
 * and served unchanged at `GET /api/metrics`.
 */
export interface BinaryMetrics {
  readonly tp: number;
  readonly fp: number;
  readonly fn: number;
  readonly tn: number;
  readonly positives: number;
  readonly negatives: number;
  readonly abstained_pos: number;
  readonly abstained_neg: number;
  readonly failed_pos: number;
  readonly failed_neg: number;
  readonly precision: number | null;
  readonly precision_ci: readonly [number, number] | null;
  readonly coverage: number | null;
  readonly recall: number | null;
  readonly recall_ci: readonly [number, number] | null;
  readonly coverage_pos: number | null;
  readonly recall_all: number | null;
  readonly recall_all_ci: readonly [number, number] | null;
  readonly f1: number | null;
  readonly fpr: number | null;
  readonly fpr_ci: readonly [number, number] | null;
  readonly coverage_neg: number | null;
  readonly abstain_rate: number | null;
  readonly failure_rate: number | null;
}

export interface FitHeadline {
  readonly n: number | null;
  readonly auc: number | null;
  readonly auc_without: number | null;
  readonly auc_alone: number | null;
}

export interface HeadlineEntry {
  readonly family_removed: string;
  readonly with: BinaryMetrics;
  readonly without: BinaryMetrics | null;
  readonly fit?: FitHeadline | null;
}

export interface FitAblationEntry {
  readonly items_nonzero?: number;
  readonly auc_without?: number | null;
  readonly log_loss_without?: number | null;
  readonly auc_alone?: number | null;
}

export interface FitDimensionSummary {
  readonly n: number;
  readonly auc: number | null;
  readonly log_loss: number | null;
  readonly brier: number | null;
  readonly ablation: Readonly<Record<string, FitAblationEntry>>;
}

export interface CalibrationBin {
  readonly bin: readonly [number, number];
  readonly mean_confidence: number | null;
  readonly positive_rate: number | null;
  readonly n: number;
}

export interface DimensionMetrics {
  readonly overall: BinaryMetrics;
  readonly missing: number;
  readonly per_set: Readonly<Record<string, BinaryMetrics>>;
  readonly per_language: Readonly<Record<string, BinaryMetrics>>;
  readonly calibration: readonly CalibrationBin[];
  readonly ablation: Readonly<Record<string, BinaryMetrics>>;
}

export interface MetricsPayload {
  readonly threshold: number;
  readonly items: number;
  readonly pipeline_versions: readonly string[];
  readonly headline: Readonly<Record<string, HeadlineEntry>>;
  readonly fit: Readonly<Record<string, FitDimensionSummary>>;
  readonly dimensions: Readonly<Record<DimensionKey, DimensionMetrics>>;
}
