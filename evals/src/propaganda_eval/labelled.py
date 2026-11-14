"""Load and validate labelled.jsonl, the ground-truth set for the eval and the combiner fit.

Each line is one labelled item:
{
    "id":          "fcd_it_001",
    "url":         "https://…",                     // the content to analyse (fetched by us)
    "text":        "claim quoted by a fact-checker", // when there is no url, or as a quote
    "language":    "it",                            // ISO 639-1
    "labels": {
        "single":      true,                        // true | false | null (no third-party label)
        "coordinated": null
    },
    "set":         "fact_checker_debunk",           // which evaluation set
    "source":      "ClaimReview feed (Pagella Politica)",   // where the label comes from
    "source_url":  "https://…",                     // the page that establishes the label
    "notes":       "rating: Falso"
}

Article bodies are never committed (scraped text, research-only datasets): an item carries the
URL, or a short claim quoted verbatim by a fact-checker. A `null` label leaves the item out of
that dimension: a debunked claim says nothing about coordination, a Pravda-network article is
labelled by network membership, not by its techniques.

Sets (plan §8):
  Positives:
    fact_checker_debunk — claims debunked by fact-checkers (single=true)
    euvsDisinfo         — EUvsDisinfo database cases (single=true)
    viginum_pravda      — articles on VIGINUM Portal Kombat domains (coordinated=true)
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

# A claim quoted by a fact-checker is a sentence or two; anything longer is an article body.
MAX_TEXT_CHARS = 600


@dataclass
class LabelledItem:
    id: str
    language: str
    labels: dict[str, bool | None]
    set_name: str
    text: str = ""
    url: str = ""
    source: str = ""
    source_url: str = ""
    notes: str = ""


def load_labelled(path: Path) -> list[LabelledItem]:
    items: list[LabelledItem] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            item = LabelledItem(
                id=d.get("id", ""),
                text=d.get("text") or "",
                language=d.get("language", ""),
                labels=d.get("labels", {}),
                set_name=d.get("set", ""),
                url=d.get("url") or "",
                source=d.get("source", ""),
                source_url=d.get("source_url", ""),
                notes=d.get("notes", ""),
            )
            _validate(item, lineno)
            if item.id in seen:
                raise ValueError(f"line {lineno}: duplicate id '{item.id}'")
            seen.add(item.id)
            items.append(item)
    return items


def stats(items: list[LabelledItem]) -> dict:
    by_set: dict[str, int] = {}
    by_dim = {d: {"pos": 0, "neg": 0, "unlabelled": 0} for d in DIMENSIONS}
    by_lang: dict[str, int] = {}

    for item in items:
        by_set[item.set_name] = by_set.get(item.set_name, 0) + 1
        by_lang[item.language] = by_lang.get(item.language, 0) + 1
        for dim in DIMENSIONS:
            label = item.labels.get(dim)
            key = "unlabelled" if label is None else "pos" if label else "neg"
            by_dim[dim][key] += 1

    return {
        "total": len(items),
        "by_set": dict(sorted(by_set.items(), key=lambda kv: -kv[1])),
        "by_dimension": by_dim,
        "by_language": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
    }


def _validate(item: LabelledItem, lineno: int) -> None:
    where = f"line {lineno} ({item.id or 'no id'})"
    if not item.id:
        raise ValueError(f"line {lineno}: missing id")
    if not item.url and not item.text:
        raise ValueError(f"{where}: needs a url or a text")
    if len(item.text) > MAX_TEXT_CHARS:
        raise ValueError(
            f"{where}: text longer than {MAX_TEXT_CHARS} characters; commit the url, not the body"
        )
    if item.set_name not in POSITIVE_SETS | NEGATIVE_SETS:
        raise ValueError(f"{where}: unknown set '{item.set_name}'")
    for dim in DIMENSIONS:
        if dim not in item.labels:
            raise ValueError(f"{where}: missing label '{dim}'")
        if item.labels[dim] is not None and not isinstance(item.labels[dim], bool):
            raise ValueError(f"{where}: label '{dim}' must be true, false or null")
    if not any(item.labels[dim] is not None for dim in DIMENSIONS):
        raise ValueError(f"{where}: no dimension is labelled")
