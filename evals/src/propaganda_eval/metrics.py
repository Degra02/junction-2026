"""Evaluation metrics for propaganda technique detection.

Two levels of evaluation:
1. Technique classification: given gold spans, how well are techniques classified?
   → per-technique precision, recall, F1, support; macro/micro averages.
2. Span identification: given an article, how well are propaganda spans found?
   → character-level precision, recall, F1.

Plus:
- Category-level metrics (techniques grouped into 6 coarse categories).
- Per-set false-positive rate for hard-negative sets.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .dataset import Article, Span
from .taxonomy import (
    CATEGORIES,
    SEMEVAL2020_TECHNIQUES,
    technique_display,
    technique_to_category,
)


@dataclass
class TechniqueMetrics:
    technique: str
    display_name: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    support: int = 0

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


@dataclass
class EvalResult:
    technique_metrics: dict[str, TechniqueMetrics] = field(default_factory=dict)
    category_metrics: dict[str, TechniqueMetrics] = field(default_factory=dict)
    hard_negative_results: dict[str, HardNegativeResult] = field(default_factory=dict)
    model_name: str = ""
    total_spans: int = 0
    total_articles: int = 0

    @property
    def micro_precision(self) -> float:
        tp = sum(m.tp for m in self.technique_metrics.values())
        fp = sum(m.fp for m in self.technique_metrics.values())
        return tp / (tp + fp) if (tp + fp) > 0 else 0.0

    @property
    def micro_recall(self) -> float:
        tp = sum(m.tp for m in self.technique_metrics.values())
        fn = sum(m.fn for m in self.technique_metrics.values())
        return tp / (tp + fn) if (tp + fn) > 0 else 0.0

    @property
    def micro_f1(self) -> float:
        p, r = self.micro_precision, self.micro_recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def macro_f1(self) -> float:
        scores = [m.f1 for m in self.technique_metrics.values() if m.support > 0]
        return sum(scores) / len(scores) if scores else 0.0


@dataclass
class HardNegativeResult:
    set_name: str
    total_items: int = 0
    false_positives: int = 0
    false_positive_details: list[dict] = field(default_factory=list)

    @property
    def fpr(self) -> float:
        return self.false_positives / self.total_items if self.total_items > 0 else 0.0


@dataclass
class Prediction:
    article_id: str
    technique: str
    start: int
    end: int
    confidence: float = 1.0


def evaluate_technique_classification(
    gold_spans: list[Span],
    pred_spans: list[Prediction],
    iou_threshold: float = 0.5,
) -> EvalResult:
    """Evaluate technique classification with span matching.

    A predicted span matches a gold span if:
    1. Same article
    2. IoU (char-level intersection over union) >= threshold
    3. Technique label matches (for TP; mismatch → FP for pred technique + FN for gold technique)
    """
    result = EvalResult()
    result.total_spans = len(gold_spans)

    for t in SEMEVAL2020_TECHNIQUES:
        result.technique_metrics[t] = TechniqueMetrics(
            technique=t, display_name=technique_display(t)
        )

    gold_by_article: dict[str, list[Span]] = defaultdict(list)
    for s in gold_spans:
        gold_by_article[s.article_id].append(s)

    pred_by_article: dict[str, list[Prediction]] = defaultdict(list)
    for p in pred_spans:
        pred_by_article[p.article_id].append(p)

    all_article_ids = set(gold_by_article) | set(pred_by_article)

    for article_id in all_article_ids:
        golds = gold_by_article.get(article_id, [])
        preds = pred_by_article.get(article_id, [])
        matched_golds: set[int] = set()
        matched_preds: set[int] = set()

        for pi, pred in enumerate(preds):
            best_iou = 0.0
            best_gi = -1
            for gi, gold in enumerate(golds):
                iou = _char_iou(pred.start, pred.end, gold.start, gold.end)
                if iou > best_iou:
                    best_iou = iou
                    best_gi = gi

            if best_iou >= iou_threshold and best_gi not in matched_golds:
                gold = golds[best_gi]
                matched_golds.add(best_gi)
                matched_preds.add(pi)
                if pred.technique == gold.technique:
                    result.technique_metrics[gold.technique].tp += 1
                else:
                    result.technique_metrics[pred.technique].fp += 1
                    result.technique_metrics[gold.technique].fn += 1
            else:
                if pred.technique in result.technique_metrics:
                    result.technique_metrics[pred.technique].fp += 1

        for gi, gold in enumerate(golds):
            if gi not in matched_golds:
                result.technique_metrics[gold.technique].fn += 1

    for t in SEMEVAL2020_TECHNIQUES:
        m = result.technique_metrics[t]
        m.support = sum(1 for s in gold_spans if s.technique == t)

    result.category_metrics = _aggregate_to_categories(result.technique_metrics)
    return result


def evaluate_span_identification(
    articles: dict[str, Article],
    pred_spans: list[Prediction],
) -> dict[str, float]:
    """Character-level precision, recall, F1 for span identification (binary)."""
    total_tp = 0
    total_pred_chars = 0
    total_gold_chars = 0

    pred_by_article: dict[str, list[Prediction]] = defaultdict(list)
    for p in pred_spans:
        pred_by_article[p.article_id].append(p)

    for article_id, article in articles.items():
        n = len(article.text)
        gold_mask = bytearray(n)
        pred_mask = bytearray(n)

        for span in article.spans:
            for i in range(span.start, min(span.end, n)):
                gold_mask[i] = 1

        for pred in pred_by_article.get(article_id, []):
            for i in range(pred.start, min(pred.end, n)):
                pred_mask[i] = 1

        for i in range(n):
            if gold_mask[i] and pred_mask[i]:
                total_tp += 1
            if pred_mask[i]:
                total_pred_chars += 1
            if gold_mask[i]:
                total_gold_chars += 1

    precision = total_tp / total_pred_chars if total_pred_chars > 0 else 0.0
    recall = total_tp / total_gold_chars if total_gold_chars > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_hard_negatives(
    set_name: str,
    texts: list[str],
    predictions: list[list[Prediction]],
) -> HardNegativeResult:
    """Evaluate FPR on a hard-negative set (texts that should have zero detections)."""
    result = HardNegativeResult(set_name=set_name, total_items=len(texts))
    for i, preds in enumerate(predictions):
        if preds:
            result.false_positives += 1
            result.false_positive_details.append({
                "item_index": i,
                "text_preview": texts[i][:200],
                "predicted_techniques": [p.technique for p in preds],
            })
    return result


def _char_iou(s1: int, e1: int, s2: int, e2: int) -> float:
    overlap_start = max(s1, s2)
    overlap_end = min(e1, e2)
    if overlap_start >= overlap_end:
        return 0.0
    intersection = overlap_end - overlap_start
    union = (e1 - s1) + (e2 - s2) - intersection
    return intersection / union if union > 0 else 0.0


def _aggregate_to_categories(
    technique_metrics: dict[str, TechniqueMetrics],
) -> dict[str, TechniqueMetrics]:
    cat_metrics: dict[str, TechniqueMetrics] = {}
    for cat in CATEGORIES:
        cat_metrics[cat] = TechniqueMetrics(technique=cat, display_name=cat)

    for tech, m in technique_metrics.items():
        cat = technique_to_category(tech)
        cm = cat_metrics[cat]
        cm.tp += m.tp
        cm.fp += m.fp
        cm.fn += m.fn
        cm.support += m.support

    return cat_metrics
