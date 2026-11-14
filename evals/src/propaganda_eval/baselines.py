"""Baselines for testing the eval harness: oracle (copies gold) and random."""

from __future__ import annotations

import json
import random
from pathlib import Path

from .dataset import Article, Span, load_semeval2020, train_dev_split
from .metrics import Prediction
from .taxonomy import SEMEVAL2020_TECHNIQUES


def oracle_predictions(articles: dict[str, Article]) -> list[Prediction]:
    """Perfect predictions: copies gold spans exactly."""
    return [
        Prediction(
            article_id=s.article_id,
            technique=s.technique,
            start=s.start,
            end=s.end,
            confidence=1.0,
        )
        for a in articles.values()
        for s in a.spans
    ]


def random_predictions(
    articles: dict[str, Article],
    spans_per_article: int = 5,
    seed: int = 42,
) -> list[Prediction]:
    """Random spans and techniques — expected to score poorly."""
    rng = random.Random(seed)
    preds = []
    for a in articles.values():
        n = len(a.text)
        if n < 20:
            continue
        for _ in range(spans_per_article):
            start = rng.randint(0, n - 10)
            end = start + rng.randint(5, min(200, n - start))
            preds.append(Prediction(
                article_id=a.article_id,
                technique=rng.choice(SEMEVAL2020_TECHNIQUES),
                start=start,
                end=end,
                confidence=rng.random(),
            ))
    return preds


def write_predictions(preds: list[Prediction], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for p in preds:
            json.dump({
                "article_id": p.article_id,
                "technique": p.technique,
                "start": p.start,
                "end": p.end,
                "confidence": p.confidence,
            }, f)
            f.write("\n")


def generate_baselines(data_dir: str, output_dir: str) -> None:
    train, _ = load_semeval2020(data_dir)
    _, eval_articles = train_dev_split(train)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    oracle = oracle_predictions(eval_articles)
    write_predictions(oracle, out / "oracle.jsonl")

    rand = random_predictions(eval_articles)
    write_predictions(rand, out / "random.jsonl")

    print(f"Generated baselines in {out}/")
    print(f"  oracle.jsonl: {len(oracle)} predictions (perfect copy of gold)")
    print(f"  random.jsonl: {len(rand)} predictions (random spans + techniques)")
