"""Evaluation metrics aligned with the pipeline (plan §5, §8).

Two dimensions scored separately: single, coordinated. Per dimension:
  - precision, recall, F1, FPR, with Wilson 95% intervals (small labelled sets);
  - FPR per hard-negative set, metrics per set and per language;
  - calibration table (reliability);
  - abstain rate and failure rate, apart: an abstention is the pipeline saying "not enough
    evidence", a failure is the pipeline breaking (a stage failed, the analysis timed out);
  - ablation: the same metrics with each family's evidence removed (what each family adds).

Items whose label is null for a dimension are left out of that dimension.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .labelled import DIMENSIONS, LabelledItem


@dataclass
class BinaryMetrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    abstained: int = 0
    failed: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def fpr(self) -> float:
        return self.fp / (self.fp + self.tn) if (self.fp + self.tn) > 0 else 0.0

    @property
    def total(self) -> int:
        """Items with a score."""
        return self.tp + self.fp + self.fn + self.tn

    @property
    def abstain_rate(self) -> float:
        """Share of the analyses that finished which abstained; failures are not abstentions."""
        finished = self.total + self.abstained
        return self.abstained / finished if finished > 0 else 0.0

    @property
    def failure_rate(self) -> float:
        runs = self.total + self.abstained + self.failed
        return self.failed / runs if runs > 0 else 0.0

    @property
    def precision_ci(self) -> tuple[float, float]:
        return _wilson(self.tp, self.tp + self.fp)

    @property
    def recall_ci(self) -> tuple[float, float]:
        return _wilson(self.tp, self.tp + self.fn)

    @property
    def fpr_ci(self) -> tuple[float, float]:
        return _wilson(self.fp, self.fp + self.tn)

    def update(self, score: float | None, gold: bool, threshold: float) -> None:
        if score is None:
            self.abstained += 1
        elif score >= threshold:
            if gold:
                self.tp += 1
            else:
                self.fp += 1
        elif gold:
            self.fn += 1
        else:
            self.tn += 1

    def as_dict(self) -> dict[str, object]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "abstained": self.abstained,
            "failed": self.failed,
            "precision": _round(self.precision),
            "precision_ci": [_round(x) for x in self.precision_ci],
            "recall": _round(self.recall),
            "recall_ci": [_round(x) for x in self.recall_ci],
            "f1": _round(self.f1),
            "fpr": _round(self.fpr),
            "fpr_ci": [_round(x) for x in self.fpr_ci],
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
    # Labelled items without any prediction (the runner has not reached them).
    missing: int = 0


@dataclass
class EvalResult:
    threshold: float
    total_items: int = 0
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    pipeline_versions: list[str] = field(default_factory=list)


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

        for item in items:
            gold = item.labels.get(dim)
            if gold is None:
                continue
            pred = predictions.get(item.id)
            if pred is None:
                dr.missing += 1
                continue
            buckets = [
                dr.overall,
                _bucket(dr.per_set, item.set_name),
                _bucket(dr.per_language, item.language or "unknown"),
            ]
            if pred.failed:
                for m in buckets:
                    m.failed += 1
                for family in pred.ablation.get(dim, {}):
                    _bucket(dr.ablation, family).failed += 1
                continue
            score = pred.scores.get(dim)
            for m in buckets:
                m.update(score, gold, threshold)
            if score is not None:
                pairs.append((score, gold))
            for family, ablated in pred.ablation.get(dim, {}).items():
                _bucket(dr.ablation, family).update(ablated, gold, threshold)

        dr.calibration = _calibrate(pairs)
        result.dimensions[dim] = dr

    return result


def to_json(result: EvalResult) -> dict[str, object]:
    """Numbers only, no item text or URLs: committed and served by `/api/metrics`."""
    return {
        "threshold": result.threshold,
        "items": result.total_items,
        "pipeline_versions": result.pipeline_versions,
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


def _round(x: float) -> float:
    return round(x, 4)


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% confidence interval."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return (max(0.0, centre - spread), min(1.0, centre + spread))
