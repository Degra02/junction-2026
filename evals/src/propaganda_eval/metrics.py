"""Evaluation metrics aligned with the pipeline (plan §5, §8).

Two dimensions scored separately: single_actor, coordinated.
Metrics per dimension:
  - precision, recall, F1 (binary: positive vs negative)
  - FPR overall and per hard-negative set
  - calibration table (reliability)
  - abstain rate
  - Wilson 95% confidence intervals (small labelled sets, plan §5)

Plus: ablation per signal family (what each family adds to the combiner).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from .labelled import DIMENSIONS, HARD_NEGATIVE_SETS, LabelledItem


@dataclass
class BinaryMetrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    abstained: int = 0

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
        return self.tp + self.fp + self.fn + self.tn

    @property
    def abstain_rate(self) -> float:
        total = self.total + self.abstained
        return self.abstained / total if total > 0 else 0.0

    @property
    def precision_ci(self) -> tuple[float, float]:
        return _wilson(self.tp, self.tp + self.fp)

    @property
    def fpr_ci(self) -> tuple[float, float]:
        return _wilson(self.fp, self.fp + self.tn)


@dataclass
class DimensionResult:
    dimension: str
    overall: BinaryMetrics = field(default_factory=BinaryMetrics)
    per_set: dict[str, BinaryMetrics] = field(default_factory=dict)


@dataclass
class EvalResult:
    dimensions: dict[str, DimensionResult] = field(default_factory=dict)
    total_items: int = 0
    calibration: dict[str, list[CalibrationBin]] = field(default_factory=dict)


@dataclass
class CalibrationBin:
    bin_start: float
    bin_end: float
    predicted_positive: float
    actual_positive: float
    count: int


@dataclass
class Prediction:
    """One pipeline result for a labelled item."""
    item_id: str
    scores: dict[str, float | None]  # dimension → confidence (None = abstained)


def evaluate(
    items: list[LabelledItem],
    predictions: dict[str, Prediction],
    threshold: float = 0.5,
) -> EvalResult:
    result = EvalResult(total_items=len(items))

    for dim in DIMENSIONS:
        dim_result = DimensionResult(dimension=dim)
        score_label_pairs: list[tuple[float, bool]] = []

        for item in items:
            pred = predictions.get(item.id)
            gold = item.labels[dim]

            if pred is None or pred.scores.get(dim) is None:
                dim_result.overall.abstained += 1
                _get_set_metrics(dim_result, item.set_name).abstained += 1
                continue

            score = pred.scores[dim]
            predicted_positive = score >= threshold
            score_label_pairs.append((score, gold))

            _update_binary(dim_result.overall, predicted_positive, gold)
            _update_binary(
                _get_set_metrics(dim_result, item.set_name),
                predicted_positive, gold,
            )

        result.dimensions[dim] = dim_result
        result.calibration[dim] = _calibrate(score_label_pairs)

    return result


def _update_binary(m: BinaryMetrics, predicted: bool, gold: bool) -> None:
    if predicted and gold:
        m.tp += 1
    elif predicted and not gold:
        m.fp += 1
    elif not predicted and gold:
        m.fn += 1
    else:
        m.tn += 1


def _get_set_metrics(dim_result: DimensionResult, set_name: str) -> BinaryMetrics:
    if set_name not in dim_result.per_set:
        dim_result.per_set[set_name] = BinaryMetrics()
    return dim_result.per_set[set_name]


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


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% confidence interval."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return (max(0.0, centre - spread), min(1.0, centre + spread))
