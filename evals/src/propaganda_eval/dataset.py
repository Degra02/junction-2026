"""Load and parse the SemEval-2020 Task 11 PTC corpus."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Span:
    article_id: str
    technique: str
    start: int
    end: int
    text: str = ""


@dataclass
class Article:
    article_id: str
    text: str
    spans: list[Span] = field(default_factory=list)


def load_articles(articles_dir: Path) -> dict[str, Article]:
    articles: dict[str, Article] = {}
    for f in sorted(articles_dir.iterdir()):
        if not f.name.endswith(".txt"):
            continue
        article_id = f.stem.removeprefix("article")
        text = f.read_text(encoding="utf-8")
        articles[article_id] = Article(article_id=article_id, text=text)
    return articles


def load_tc_labels(labels_path: Path) -> list[Span]:
    """Load Task 2 technique classification labels (article_id, technique, start, end)."""
    spans: list[Span] = []
    with open(labels_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            spans.append(Span(
                article_id=parts[0],
                technique=parts[1],
                start=int(parts[2]),
                end=int(parts[3]),
            ))
    return spans


def load_si_labels(labels_path: Path) -> list[Span]:
    """Load Task 1 span identification labels (article_id, start, end)."""
    spans: list[Span] = []
    with open(labels_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            spans.append(Span(
                article_id=parts[0],
                technique="propaganda",
                start=int(parts[1]),
                end=int(parts[2]),
            ))
    return spans


def load_semeval2020(data_dir: str | Path) -> tuple[dict[str, Article], dict[str, Article]]:
    """Load train and dev splits, attaching gold spans with extracted text.

    Returns (train_articles, dev_articles). Dev articles have gold spans from
    Task 1 (binary) only; technique labels are the ``?`` template.
    """
    data_dir = Path(data_dir) / "datasets"

    train_articles = load_articles(data_dir / "train-articles")
    dev_articles = load_articles(data_dir / "dev-articles")

    for span in load_tc_labels(data_dir / "train-task2-TC.labels"):
        art = train_articles.get(span.article_id)
        if art:
            span.text = art.text[span.start:span.end]
            art.spans.append(span)

    if (si := data_dir / "train-task1-SI.labels").exists():
        pass  # spans already loaded from TC labels with technique info

    per_article_dir = data_dir / "train-labels-task2-technique-classification"
    if per_article_dir.exists():
        pass  # consolidated labels already loaded from the flat file

    return train_articles, dev_articles


def train_dev_split(
    train_articles: dict[str, Article],
    held_out_fraction: float = 0.15,
    seed: int = 42,
) -> tuple[dict[str, Article], dict[str, Article]]:
    """Split train into train/eval since the official dev has no TC gold labels."""
    import random
    rng = random.Random(seed)
    ids = sorted(train_articles.keys())
    rng.shuffle(ids)
    split_idx = int(len(ids) * (1 - held_out_fraction))
    train_ids = set(ids[:split_idx])
    eval_ids = set(ids[split_idx:])
    train = {k: v for k, v in train_articles.items() if k in train_ids}
    held = {k: v for k, v in train_articles.items() if k in eval_ids}
    return train, held
