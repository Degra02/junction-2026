"""Hard-negative set management.

Hard negatives are texts that should NOT be flagged as propaganda.
Each set targets a specific failure mode:
- fact_checks: articles that quote propaganda to debunk it
- satire: satirical articles using exaggeration for humour
- op_eds: legitimate opinion journalism with strong language
- wire_copy: syndicated news (AP, Reuters) that appears on many sites
- press_releases: corporate/government press releases

Sources are recorded per item. Data lives in evals/data/hard_negatives/<set_name>/
as individual .txt files with a companion .meta.json per file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

HARD_NEGATIVE_SETS = [
    "fact_checks",
    "satire",
    "op_eds",
    "wire_copy",
    "press_releases",
]


@dataclass
class HardNegativeItem:
    text: str
    source_url: str = ""
    source_name: str = ""
    set_name: str = ""
    notes: str = ""


def load_hard_negative_set(data_dir: Path, set_name: str) -> list[HardNegativeItem]:
    set_dir = data_dir / "hard_negatives" / set_name
    if not set_dir.exists():
        return []

    items = []
    for txt_file in sorted(set_dir.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8")
        meta_file = txt_file.with_suffix(".meta.json")
        meta = {}
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))

        items.append(HardNegativeItem(
            text=text,
            source_url=meta.get("source_url", ""),
            source_name=meta.get("source_name", ""),
            set_name=set_name,
            notes=meta.get("notes", ""),
        ))
    return items


def save_hard_negative(data_dir: Path, item: HardNegativeItem, filename: str) -> Path:
    set_dir = data_dir / "hard_negatives" / item.set_name
    set_dir.mkdir(parents=True, exist_ok=True)

    txt_path = set_dir / f"{filename}.txt"
    txt_path.write_text(item.text, encoding="utf-8")

    meta_path = set_dir / f"{filename}.meta.json"
    meta_path.write_text(json.dumps({
        "source_url": item.source_url,
        "source_name": item.source_name,
        "set_name": item.set_name,
        "notes": item.notes,
    }, indent=2), encoding="utf-8")

    return txt_path


def init_hard_negative_dirs(data_dir: Path) -> None:
    for set_name in HARD_NEGATIVE_SETS:
        (data_dir / "hard_negatives" / set_name).mkdir(parents=True, exist_ok=True)
    print(f"Initialized hard-negative directories in {data_dir / 'hard_negatives'}/")
    for s in HARD_NEGATIVE_SETS:
        n = len(list((data_dir / "hard_negatives" / s).glob("*.txt")))
        print(f"  {s}: {n} items")
