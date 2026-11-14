"""Evaluation metrics aligned with the pipeline (plan §5, §8).

Two dimensions scored separately: single, coordinated. Per dimension:
  - precision, recall, F1, FPR on the items that got a score, with Wilson 95% intervals;
  - coverage next to each: the share of the labelled items (of that class for recall and FPR)
    that got a score, and `recall_all`, which counts abstained and failed positives as misses.
    A recall of 1.0 on 3 scored positives out of 40 is not a recall of 1.0;
  - `None` (`n/a` in tables, `null` in JSON) when a denominator is empty, never 0;
  - FPR per hard-negative set, metrics per set and per language;
  - calibration table (reliability);
  - abstain rate and failure rate, apart: an abstention is the pipeline saying "not enough
    evidence", a failure is the pipeline breaking (a stage failed, the analysis timed out);
  - ablation: the same metrics with each family's evidence removed (what each family adds),
    and the headline with the family that shares its source with the label removed.

Items whose label is null for a dimension are left out of that dimension.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .labelled import DIMENSIONS, MIXED_SETS, LabelledItem

# Families whose evidence comes from the same source as the label: the VIGINUM list labels
# `viginum_pravda` and is the `known_networks` signal; a ClaimReview defines a debunked claim
# and is the `fact_checks` signal. Their metrics are reported with and without the family.
LABEL_SOURCE_FAMILY = {"single": "fact_checks", "coordinated": "known_networks"}
# `outlet_fact_checker` (a fact-checker as the outlet) is a source_profile signal: the
# hard_fact_checks FPR is reported without that family as well.
SET_SOURCE_FAMILY = {("single", "hard_fact_checks"): "source_profile"}


@dataclass
class BinaryMetrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    abstained_pos: int = 0
    abstained_neg: int = 0
    failed_pos: int = 0
    failed_neg: int = 0

    @property
    def abstained(self) -> int:
        return self.abstained_pos + self.abstained_neg

    @property
    def failed(self) -> int:
        return self.failed_pos + self.failed_neg

    @property
    def total(self) -> int:
        """Items with a score."""
        return self.tp + self.fp + self.fn + self.tn

    @property
    def positives(self) -> int:
        """Labelled positives that were run (scored, abstained or failed)."""
        return self.tp + self.fn + self.abstained_pos + self.failed_pos

    @property
    def negatives(self) -> int:
        return self.fp + self.tn + self.abstained_neg + self.failed_neg

    @property
    def precision(self) -> float | None:
        return _ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        """On the scored positives: read it next to `coverage_pos`."""
        return _ratio(self.tp, self.tp + self.fn)

    @property
    def recall_all(self) -> float | None:
        """On every labelled positive: an abstention or a failure is a miss."""
        return _ratio(self.tp, self.positives)

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None:
            return None
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def fpr(self) -> float | None:
        """On the scored negatives: read it next to `coverage_neg`."""
        return _ratio(self.fp, self.fp + self.tn)

    @property
    def coverage(self) -> float | None:
        """Scored / labelled: the share of the items the precision is computed on."""
        return _ratio(self.total, self.positives + self.negatives)

    @property
    def coverage_pos(self) -> float | None:
        return _ratio(self.tp + self.fn, self.positives)

    @property
    def coverage_neg(self) -> float | None:
        return _ratio(self.fp + self.tn, self.negatives)

    @property
    def abstain_rate(self) -> float | None:
        """Share of the analyses that finished which abstained; failures are not abstentions."""
        return _ratio(self.abstained, self.total + self.abstained)

    @property
    def failure_rate(self) -> float | None:
        return _ratio(self.failed, self.positives + self.negatives)

    @property
    def precision_ci(self) -> tuple[float, float] | None:
        return _wilson(self.tp, self.tp + self.fp)

    @property
    def recall_ci(self) -> tuple[float, float] | None:
        return _wilson(self.tp, self.tp + self.fn)

    @property
    def recall_all_ci(self) -> tuple[float, float] | None:
        return _wilson(self.tp, self.positives)

    @property
    def fpr_ci(self) -> tuple[float, float] | None:
        return _wilson(self.fp, self.fp + self.tn)

    def update(self, score: float | None, gold: bool, threshold: float) -> None:
        if score is None:
            if gold:
                self.abstained_pos += 1
            else:
                self.abstained_neg += 1
        elif score >= threshold:
            if gold:
                self.tp += 1
            else:
                self.fp += 1
        elif gold:
            self.fn += 1
        else:
            self.tn += 1

    def fail(self, gold: bool) -> None:
        if gold:
            self.failed_pos += 1
        else:
            self.failed_neg += 1

    def as_dict(self) -> dict[str, object]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "positives": self.positives,
            "negatives": self.negatives,
            "abstained_pos": self.abstained_pos,
            "abstained_neg": self.abstained_neg,
            "failed_pos": self.failed_pos,
            "failed_neg": self.failed_neg,
            "precision": _round(self.precision),
            "precision_ci": _round_ci(self.precision_ci),
            "coverage": _round(self.coverage),
            "recall": _round(self.recall),
            "recall_ci": _round_ci(self.recall_ci),
            "coverage_pos": _round(self.coverage_pos),
            "recall_all": _round(self.recall_all),
            "recall_all_ci": _round_ci(self.recall_all_ci),
            "f1": _round(self.f1),
            "fpr": _round(self.fpr),
            "fpr_ci": _round_ci(self.fpr_ci),
            "coverage_neg": _round(self.coverage_neg),
            "abstain_rate": _round(self.abstain_rate),
            "failure_rate": _round(self.failure_rate),
        }


@dataclass
class CalibrationBin:
    bin_start: float
    bin_end: float
    predicted_positive: float
    actual_positive: float
    count: int


@dataclass
class DimensionResult:
    dimension: str
    overall: BinaryMetrics = field(default_factory=BinaryMetrics)
    per_set: dict[str, BinaryMetrics] = field(default_factory=dict)
    per_language: dict[str, BinaryMetrics] = field(default_factory=dict)
    calibration: list[CalibrationBin] = field(default_factory=list)
    # Family → metrics with that family's evidence removed (only when the runner recorded it).
    ablation: dict[str, BinaryMetrics] = field(default_factory=dict)
    # Family → set → the same, per labelled set.
    ablation_per_set: dict[str, dict[str, BinaryMetrics]] = field(default_factory=dict)
    # Labelled items without any prediction (the runner has not reached them).
    missing: int = 0


@dataclass
class EvalResult:
    threshold: float
    total_items: int = 0
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    pipeline_versions: list[str] = field(default_factory=list)
    # Dimension → the combiner fit's cross-validated numbers (`weights.json` → `cv`, `n`);
    # empty while the weights are priors.
    fit: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass
class Prediction:
    """One pipeline result for a labelled item."""

    item_id: str
    scores: dict[str, float | None]  # dimension → confidence (None = abstained)
    failed: bool = False
    # dimension → family → confidence with that family's evidence removed (None = abstained)
    ablation: dict[str, dict[str, float | None]] = field(default_factory=dict)
    pipeline_version: str = ""


def evaluate(
    items: list[LabelledItem],
    predictions: dict[str, Prediction],
    threshold: float = 0.5,
) -> EvalResult:
    result = EvalResult(
        threshold=threshold,
        total_items=len(items),
        pipeline_versions=sorted(
            {p.pipeline_version for p in predictions.values() if p.pipeline_version}
        ),
    )

    for dim in DIMENSIONS:
        dr = DimensionResult(dimension=dim)
        pairs: list[tuple[float, bool]] = []
        # The runner records a family's ablation only where its evidence fired; elsewhere
        # removing it changes nothing, so every item counts in every ablation row.
        families = sorted({f for p in predictions.values() for f in p.ablation.get(dim, {})})

        for item in items:
            gold = item.labels.get(dim)
            if gold is None:
                continue
            pred = predictions.get(item.id)
            if pred is None:
                dr.missing += 1
                continue
            # A mixed set (memes) is its own construct: only its per-set rows, never the
            # headline, the per-language rows or the calibration of the article set.
            article = item.set_name not in MIXED_SETS
            buckets = [_bucket(dr.per_set, item.set_name)]
            if article:
                buckets += [dr.overall, _bucket(dr.per_language, item.language or "unknown")]
            ablation_buckets = {
                f: [_bucket(dr.ablation_per_set.setdefault(f, {}), item.set_name)]
                + ([_bucket(dr.ablation, f)] if article else [])
                for f in families
            }
            if pred.failed:
                for m in buckets + [m for ms in ablation_buckets.values() for m in ms]:
                    m.fail(gold)
                continue
            score = pred.scores.get(dim)
            for m in buckets:
                m.update(score, gold, threshold)
            if score is not None and article:
                pairs.append((score, gold))
            recorded = pred.ablation.get(dim, {})
            for f, ms in ablation_buckets.items():
                for m in ms:
                    m.update(recorded.get(f, score), gold, threshold)

        dr.calibration = _calibrate(pairs)
        result.dimensions[dim] = dr

    return result


def headline(result: EvalResult) -> dict[str, object]:
    """Each dimension with and without the family that shares its source with the label."""
    out: dict[str, object] = {}
    for dim, dr in result.dimensions.items():
        family = LABEL_SOURCE_FAMILY[dim]
        without = dr.ablation.get(family)
        out[dim] = {
            "family_removed": family,
            "with": dr.overall.as_dict(),
            # None: the predictions carry no ablation for it (the family never fired).
            "without": without.as_dict() if without else None,
            "fit": _fit_headline(result.fit.get(dim), family),
        }
    for (dim, set_name), family in sorted(SET_SOURCE_FAMILY.items()):
        dr = result.dimensions.get(dim)
        if dr is None or set_name not in dr.per_set:
            continue
        without = dr.ablation_per_set.get(family, {}).get(set_name)
        out[f"{dim}/{set_name}"] = {
            "family_removed": family,
            "with": dr.per_set[set_name].as_dict(),
            "without": without.as_dict() if without else None,
        }
    return out


def to_json(result: EvalResult) -> dict[str, object]:
    """Numbers only, no item text or URLs: committed and served by `/api/metrics`."""
    return {
        "threshold": result.threshold,
        "items": result.total_items,
        "pipeline_versions": result.pipeline_versions,
        "headline": headline(result),
        "fit": result.fit,
        "dimensions": {
            dim: {
                "overall": dr.overall.as_dict(),
                "missing": dr.missing,
                "per_set": {k: m.as_dict() for k, m in sorted(dr.per_set.items())},
                "per_language": {k: m.as_dict() for k, m in sorted(dr.per_language.items())},
                "calibration": [
                    {
                        "bin": [b.bin_start, b.bin_end],
                        "mean_confidence": _round(b.predicted_positive),
                        "positive_rate": _round(b.actual_positive),
                        "n": b.count,
                    }
                    for b in dr.calibration
                ],
                "ablation": {
                    f"without_{family}": m.as_dict() for family, m in sorted(dr.ablation.items())
                },
            }
            for dim, dr in result.dimensions.items()
        },
    }


def fit_summary(weights: dict[str, object]) -> dict[str, dict[str, object]]:
    """The numbers of `pipeline/score/weights.json` the report quotes; empty for priors."""
    out: dict[str, dict[str, object]] = {}
    for dim in DIMENSIONS:
        w = weights.get(dim)
        if not isinstance(w, dict) or not w.get("cv"):
            continue
        cv = w["cv"]
        out[dim] = {
            "n": w.get("n"),
            "auc": cv.get("auc"),
            "log_loss": cv.get("log_loss"),
            "brier": cv.get("brier"),
            "ablation": cv.get("ablation") or {},
        }
    return out


def _fit_headline(fit: dict[str, object] | None, family: str) -> dict[str, object] | None:
    if not fit:
        return None
    ablation = fit.get("ablation") or {}
    report = ablation.get(family) if isinstance(ablation, dict) else None
    return {
        "n": fit.get("n"),
        "auc": fit.get("auc"),
        # Refit without the family (pipeline.score.fit), not a re-score with the same weights.
        "auc_without": report.get("auc_without") if report else None,
        "auc_alone": report.get("auc_alone") if report else None,
    }


def _bucket(groups: dict[str, BinaryMetrics], key: str) -> BinaryMetrics:
    if key not in groups:
        groups[key] = BinaryMetrics()
    return groups[key]


def _calibrate(pairs: list[tuple[float, bool]], n_bins: int = 5) -> list[CalibrationBin]:
    if not pairs:
        return []
    bins: list[CalibrationBin] = []
    step = 1.0 / n_bins
    for i in range(n_bins):
        lo = i * step
        hi = (i + 1) * step
        in_bin = [(s, g) for s, g in pairs if lo <= s < hi or (i == n_bins - 1 and s == hi)]
        if not in_bin:
            continue
        avg_score = sum(s for s, _ in in_bin) / len(in_bin)
        actual_pos = sum(1 for _, g in in_bin if g) / len(in_bin)
        bins.append(CalibrationBin(lo, hi, avg_score, actual_pos, len(in_bin)))
    return bins


def _ratio(numerator: int, denominator: int) -> float | None:
    """None for an empty denominator: no data is not 0."""
    return numerator / denominator if denominator > 0 else None


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def _round_ci(ci: tuple[float, float] | None) -> list[float] | None:
    return None if ci is None else [round(ci[0], 4), round(ci[1], 4)]


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score 95% confidence interval; None without observations."""
    if total == 0:
        return None
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return (max(0.0, centre - spread), min(1.0, centre + spread))
