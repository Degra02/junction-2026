"""Load and validate labelled.jsonl — the ground-truth set for the combiner and eval.

Each line is one labelled item:
{
    "id":          "sa_pos_042",
    "text":        "the article or post text…",
    "url":         "https://…",                    // optional, source URL
    "language":    "en",                            // ISO 639-1
    "labels": {
        "single":        true,                      // ground truth per dimension
        "coordinated":   false
    },
    "set":         "fact_checker_debunk",            // which evaluation set
    "source":      "Google Fact Check API",          // where the item came from
    "source_url":  "https://…",                     // original source URL
    "notes":       "Debunked by PolitiFact…"        // free text
}

Sets (plan §8):
  Positives:
    fact_checker_debunk — claims debunked by fact-checkers (single=true)
    euvsDisinfo         — EUvsDisinfo database cases (single=true)
    viginum_pravda      — VIGINUM Portal Kombat domains (coordinated=true)
  Negatives / hard negatives:
    mainstream          — mainstream reporting on the same events
    hard_fact_checks    — fact-checks quoting the claim
    hard_satire         — satirical articles
    hard_op_eds         — legitimate opinion journalism
    hard_emotional      — emotional but accurate reporting
    hard_wire_copy      — wire services (AP, Reuters, ANSA) republished
    hard_press_releases — corporate/government press releases
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DIMENSIONS = ("single", "coordinated")

POSITIVE_SETS = {
    "fact_checker_debunk",
    "euvsDisinfo",
    "viginum_pravda",
}

HARD_NEGATIVE_SETS = {
    "hard_fact_checks",
    "hard_satire",
    "hard_op_eds",
    "hard_emotional",
    "hard_wire_copy",
    "hard_press_releases",
}

NEGATIVE_SETS = {"mainstream"} | HARD_NEGATIVE_SETS


@dataclass
class LabelledItem:
    id: str
    text: str
    language: str
    labels: dict[str, bool]
    set_name: str
    url: str = ""
    source: str = ""
    source_url: str = ""
    notes: str = ""


def load_labelled(path: Path) -> list[LabelledItem]:
    items: list[LabelledItem] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            item = LabelledItem(
                id=d["id"],
                text=d["text"],
                language=d.get("language", ""),
                labels=d["labels"],
                set_name=d["set"],
                url=d.get("url", ""),
                source=d.get("source", ""),
                source_url=d.get("source_url", ""),
                notes=d.get("notes", ""),
            )
            _validate(item, lineno)
            items.append(item)
    return items


def save_labelled(items: list[LabelledItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            json.dump(
                {
                    "id": item.id,
                    "text": item.text,
                    "url": item.url,
                    "language": item.language,
                    "labels": item.labels,
                    "set": item.set_name,
                    "source": item.source,
                    "source_url": item.source_url,
                    "notes": item.notes,
                },
                f,
                ensure_ascii=False,
            )
            f.write("\n")


def stats(items: list[LabelledItem]) -> dict:
    by_set: dict[str, int] = {}
    by_dim: dict[str, dict[str, int]] = {d: {"pos": 0, "neg": 0} for d in DIMENSIONS}
    by_lang: dict[str, int] = {}

    for item in items:
        by_set[item.set_name] = by_set.get(item.set_name, 0) + 1
        by_lang[item.language] = by_lang.get(item.language, 0) + 1
        for dim in DIMENSIONS:
            if item.labels.get(dim, False):
                by_dim[dim]["pos"] += 1
            else:
                by_dim[dim]["neg"] += 1

    return {
        "total": len(items),
        "by_set": dict(sorted(by_set.items(), key=lambda kv: -kv[1])),
        "by_dimension": by_dim,
        "by_language": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
    }


def _validate(item: LabelledItem, lineno: int) -> None:
    if not item.id:
        raise ValueError(f"line {lineno}: missing id")
    if not item.text:
        raise ValueError(f"line {lineno}: missing text")
    for dim in DIMENSIONS:
        if dim not in item.labels:
            raise ValueError(f"line {lineno} ({item.id}): missing label '{dim}'")
        if not isinstance(item.labels[dim], bool):
            raise ValueError(f"line {lineno} ({item.id}): label '{dim}' must be bool")
