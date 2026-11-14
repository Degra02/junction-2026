"""VIGINUM's Portal Kombat domain list: `known_network = "portal_kombat"` for listed outlets.

The CSV (`domain,create date,first seen,type`) is published by SGDSN/VIGINUM without a licence,
so it is never committed: the worker image carries it at `VIGINUM_CSV`, and locally
`bash evals/download_data.sh` puts it in `evals/data/viginum/`. Domains are written defanged
(`pravda-de[.]com`). Rows of type `domain` cover their subdomains; `subdomain` rows only
themselves and what lies below them.
"""

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path

log = logging.getLogger(__name__)

NETWORK = "portal_kombat"
DEFAULT_PATH = Path("evals/data/viginum/portal_kombat_domains.csv")


@dataclass(frozen=True)
class Listing:
    # Listed domain -> creation date from the CSV (None when the cell is empty or unreadable).
    created: dict[str, datetime | None] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.created)

    def match(self, host: str | None) -> str | None:
        """The listed domain covering `host`, or None when it is on no list."""
        if not host:
            return None
        labels = host.lower().rstrip(".").removeprefix("www.").split(".")
        for start in range(len(labels) - 1):
            candidate = ".".join(labels[start:])
            if candidate in self.created:
                return candidate
        return None


def _created(cell: str) -> datetime | None:
    try:
        day = datetime.strptime(cell.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None
    if not date(1990, 1, 1) <= day <= datetime.now(UTC).date():
        return None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def parse(text: str) -> Listing:
    created: dict[str, datetime | None] = {}
    for row in csv.DictReader(text.lstrip("﻿").splitlines()):
        domain = (row.get("domain") or "").strip().lower().replace("[.]", ".").rstrip(".")
        if "." not in domain:
            continue
        created[domain] = _created(row.get("create date") or "")
    return Listing(created)


@cache
def load_listing() -> Listing:
    """The list from `VIGINUM_CSV` (or the local eval data path); empty when it is missing."""
    path = Path(os.environ.get("VIGINUM_CSV") or DEFAULT_PATH)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        log.warning("VIGINUM list not found at %s: known_network stays empty", path)
        return Listing()
    result = parse(text)
    log.info("VIGINUM list: %d domains", len(result))
    return result
