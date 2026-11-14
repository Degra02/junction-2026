"""Build the `semeval_memes` set from the SemEval-2021 Task 6 meme corpus.

    mise run eval -- fetch-memes        # also run by evals/download_data.sh

Source: Dimitrov et al., "Detecting Propaganda Techniques in Memes" (ACL 2021) / SemEval-2021
Task 6, 950 English memes from US political and COVID Facebook groups, each annotated with the
persuasion techniques it uses (22 techniques, text and image). Terms: "These datasets are free
for general research use." (https://github.com/di-dimitrov/SEMEVAL-2021-task6-corpus#licensing).

Label mapping (ours, the annotators list techniques and never say "propagandistic"): at least
one technique → single = true; none → single = false. Only 36 memes have none, so the set is
every negative plus `POSITIVES` positives, chosen by a hash of the ID (stable across runs).
Images over the API's data-URI limit are skipped.

Writes `evals/data/semeval2021/images/` and `evals/data/semeval2021/labelled.jsonl` (both
gitignored): nothing from the dataset is committed, not even its labels.
"""

from __future__ import annotations

import base64
import hashlib
import json

import httpx

from .labelled import DATA, MEMES
from .runner import MAX_IMAGE_DATA_URI_CHARS, image_mime

BASE = (
    "https://raw.githubusercontent.com/di-dimitrov/propaganda-techniques-in-memes/main/"
    "data/datasets/propaganda/defaults"
)
SPLITS = ("train", "val", "test")
POSITIVES = 64
SOURCE_URL = "https://github.com/di-dimitrov/SEMEVAL-2021-task6-corpus"
IMAGES = MEMES.parent / "images"


def select(annotations: list[dict], positives: int = POSITIVES) -> list[dict]:
    """Every meme without a technique, then positives in a stable pseudo-random order."""
    negatives = [a for a in annotations if not a["labels"]]
    ranked = sorted(
        (a for a in annotations if a["labels"]),
        key=lambda a: hashlib.sha256(a["id"].encode()).hexdigest(),
    )
    return negatives + ranked[: positives + len(ranked) // 10]  # spares for skipped images


def fits(data: bytes) -> bool:
    """An image the runner can send: a known type, its data URI within the API's limit."""
    mime = image_mime(data)
    return (
        mime is not None
        and len(f"data:{mime};base64,") + len(base64.b64encode(data)) <= MAX_IMAGE_DATA_URI_CHARS
    )


def item(annotation: dict) -> dict:
    return {
        "id": f"m21_{annotation['id']}",
        "image": str((IMAGES / annotation["image"]).relative_to(DATA)),
        "language": "en",
        "labels": {"single": bool(annotation["labels"]), "coordinated": None},
        "set": "semeval_memes",
        "source": "SemEval-2021 Task 6 annotators (Dimitrov et al. 2021)",
        "source_url": SOURCE_URL,
        "notes": "; ".join(annotation["labels"]) or "no persuasion technique",
    }


def fetch(positives: int = POSITIVES) -> dict[str, int]:
    IMAGES.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        annotations = []
        for split in SPLITS:
            r = client.get(f"{BASE}/annotations/{split}.jsonl")
            r.raise_for_status()
            annotations += [json.loads(line) for line in r.text.splitlines() if line.strip()]

        rows, skipped, kept_pos = [], 0, 0
        for a in select(annotations, positives):
            if a["labels"] and kept_pos >= positives:
                continue
            path = IMAGES / a["image"]
            if not path.exists():
                r = client.get(f"{BASE}/images/{a['image']}")
                r.raise_for_status()
                path.write_bytes(r.content)
            if not fits(path.read_bytes()):
                skipped += 1
                continue
            rows.append(item(a))
            kept_pos += bool(a["labels"])

    MEMES.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    negatives = sum(not r["labels"]["single"] for r in rows)
    return {"items": len(rows), "positives": kept_pos, "negatives": negatives, "skipped": skipped}
