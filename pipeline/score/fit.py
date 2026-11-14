"""Fit the combiner on the labelled set and write `pipeline/score/weights.json` (plan §5).

    uv run python -m pipeline.score.fit labelled.jsonl            # fit, report, write
    uv run python -m pipeline.score.fit labelled.jsonl --dry-run  # report only

Input: JSON Lines, one labelled item per line:

    {"analysis": <finished Analysis record, e.g. GET /api/analyses/{id}>,
     "single": 1 | 0 | null, "coordinated": 1 | 0 | null}

`null` (or a missing key) leaves the item out of that dimension. Labels come from third
parties (plan §8), never from our own opinion.

Model: L2-regularised logistic regression on the family values (`families.family_values`),
fitted by Newton's method; the intercept is not regularised. The report gives out-of-fold
(k-fold cross-validated) log loss, Brier score, ROC AUC and a reliability table, which are
also stored in `weights.json` under `cv` for the metrics page.

Only analyses whose score is shown are used: when a dimension abstains (too little coverage,
unsupported language, evidence both ways) no confidence reaches the reader, so those items
say nothing about calibration, and their empty comparison families would teach the combiner
"no coverage found" instead of the signal. The report counts them per dimension.

`cv.ablation` says what each family adds (plan §8): for every family with evidence in the
set, the out-of-fold AUC and log loss of the combiner refitted without it, and of that family
alone. Read it before trusting a headline number: a family whose evidence is the label's own
source (the VIGINUM list for `known_networks`, the fact-check that defines a debunked claim
for `fact_checks`) separates the classes by construction.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import numpy as np

from pipeline.common.contracts import Analysis, Family
from pipeline.score import WEIGHTS, DimensionWeights, Weights, save_weights
from pipeline.score import run as score
from pipeline.score.families import COORDINATED, SINGLE, family_values

L2 = 1.0
FOLDS = 5
BINS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def features(analysis: Analysis, families: tuple[Family, ...]) -> list[float]:
    return [v.value for v in family_values(analysis.evidence, families)]


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = L2) -> tuple[float, np.ndarray]:
    """`(intercept, coefficients)` of an L2-regularised logistic regression."""
    design = np.hstack([np.ones((len(x), 1)), x])
    w = np.zeros(design.shape[1])
    penalty = np.eye(design.shape[1]) * l2
    penalty[0, 0] = 0.0
    for _ in range(100):
        p = 1.0 / (1.0 + np.exp(-design @ w))
        gradient = design.T @ (p - y) + penalty @ w
        hessian = design.T @ (design * (p * (1 - p))[:, None]) + penalty + 1e-9 * np.eye(len(w))
        step = np.linalg.solve(hessian, gradient)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return float(w[0]), w[1:]


def predict(x: np.ndarray, intercept: float, coefficients: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-(intercept + x @ coefficients)))


def cross_validate(x: np.ndarray, y: np.ndarray, folds: int = FOLDS) -> dict[str, object]:
    """Out-of-fold metrics; folds keep both classes' proportions (round-robin per class)."""
    rng = np.random.default_rng(0)
    fold_of = np.zeros(len(y), dtype=int)
    for label in (0, 1):
        members = rng.permutation(np.flatnonzero(y == label))
        fold_of[members] = np.arange(len(members)) % folds
    oof = np.zeros(len(y))
    for k in range(folds):
        test = fold_of == k
        if not test.any():
            continue
        intercept, coefficients = fit_logistic(x[~test], y[~test])
        oof[test] = predict(x[test], intercept, coefficients)
    return {"folds": folds, **metrics(oof, y)}


def ablation(
    x: np.ndarray, y: np.ndarray, families: tuple[Family, ...], folds: int
) -> dict[str, dict[str, object]]:
    """Per family with evidence: how often it fired, and the out-of-fold AUC and log loss
    of the combiner refitted without it and with it alone."""
    out: dict[str, dict[str, object]] = {}
    for column, family in enumerate(families):
        fired = int(np.count_nonzero(x[:, column]))
        if not fired:
            continue
        without = cross_validate(np.delete(x, column, axis=1), y, folds)
        alone = cross_validate(x[:, [column]], y, folds)
        out[family.value] = {
            "items_with_evidence": fired,
            "auc_without": without["auc"],
            "log_loss_without": without["log_loss"],
            "auc_alone": alone["auc"],
        }
    return out


def metrics(p: np.ndarray, y: np.ndarray) -> dict[str, object]:
    eps = 1e-12
    log_loss = float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))
    reliability = []
    for low, high in pairwise(BINS):
        inside = (p >= low) & ((p < high) if high < 1.0 else (p <= high))
        if inside.any():
            reliability.append(
                {
                    "bin": f"{low:.1f}-{high:.1f}",
                    "n": int(inside.sum()),
                    "mean_confidence": round(float(p[inside].mean()), 3),
                    "positive_rate": round(float(y[inside].mean()), 3),
                }
            )
    return {
        "log_loss": round(log_loss, 4),
        "brier": round(float(np.mean((p - y) ** 2)), 4),
        "auc": _auc(p, y),
        "reliability": reliability,
    }


def _auc(p: np.ndarray, y: np.ndarray) -> float | None:
    """Probability that a random positive scores above a random negative (ties count half)."""
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    greater = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return round(float(greater / (len(pos) * len(neg))), 4)


def fit_dimension(
    rows: list[tuple[Analysis, int]], families: tuple[Family, ...]
) -> DimensionWeights | None:
    labels = [label for _, label in rows]
    if min(labels.count(0), labels.count(1)) < 2:
        return None
    x = np.array([features(analysis, families) for analysis, _ in rows])
    y = np.array(labels, dtype=float)
    folds = min(FOLDS, labels.count(0), labels.count(1))
    intercept, coefficients = fit_logistic(x, y)
    return DimensionWeights(
        intercept=round(intercept, 4),
        coefficients={f: round(float(c), 4) for f, c in zip(families, coefficients, strict=True)},
        n=len(rows),
        cv={**cross_validate(x, y, folds), "ablation": ablation(x, y, families, folds)},
    )


def load(path: Path) -> tuple[dict[str, list[tuple[Analysis, int]]], dict[str, int]]:
    """Labelled analyses per dimension, and how many were left out because it abstained."""
    rows: dict[str, list[tuple[Analysis, int]]] = {"single": [], "coordinated": []}
    abstained = dict.fromkeys(rows, 0)
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        analysis = Analysis.model_validate(item["analysis"])
        # Abstention does not depend on the weights, so today's rules apply to stored records.
        scores = score(analysis).scores
        for dimension in rows:
            label = item.get(dimension)
            if label is None:
                continue
            if label not in (0, 1):
                raise SystemExit(f"line {number}: {dimension} label must be 0, 1 or null")
            if getattr(scores, dimension).abstained:
                abstained[dimension] += 1
            else:
                rows[dimension].append((analysis, int(label)))
    return rows, abstained


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("labelled", type=Path, help="JSON Lines of labelled analyses")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    rows, abstained = load(args.labelled)
    fitted = {
        "single": fit_dimension(rows["single"], SINGLE),
        "coordinated": fit_dimension(rows["coordinated"], COORDINATED),
    }
    for dimension, weights in fitted.items():
        labels = [label for _, label in rows[dimension]]
        print(
            f"{dimension}: {labels.count(1)} positive and {labels.count(0)} negative scored "
            f"items; {abstained[dimension]} abstained and left out"
        )
        if weights is None:
            print(f"{dimension}: not enough labels of both classes, prior weights kept")
        else:
            print(f"{dimension}: {json.dumps(weights.model_dump(mode='json'), indent=2)}")
    if args.dry_run:
        return
    result = Weights(
        source=f"fitted on {args.labelled.name} on {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        single=fitted["single"] or WEIGHTS.single,
        coordinated=fitted["coordinated"] or WEIGHTS.coordinated,
    )
    save_weights(result)
    print("wrote pipeline/score/weights.json", file=sys.stderr)


if __name__ == "__main__":
    main()
