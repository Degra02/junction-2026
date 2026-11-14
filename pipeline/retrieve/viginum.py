"""VIGINUM's Portal Kombat domain list: `known_network = "portal_kombat"` for listed outlets.

The CSV (`domain,create date,first seen,type`) is published by SGDSN/VIGINUM without a licence,
so it is never committed. Where it comes from, first match wins:
1. the file at `VIGINUM_CSV` (the integrator can bake it into the worker image);
2. the local eval data path, filled by `bash evals/download_data.sh`;
3. otherwise retrieve downloads it from VIGINUM's GitHub repository at run time (`fetch_listing`)
   and keeps it in the retrieval cache for a week, so the Hostinger worker has it without an
   image change.
Domains are written defanged
(`pravda-de[.]com`). Rows of type `domain` cover their subdomains; `subdomain` rows only
themselves and what lies below them.

Since Nov 2026 the Pravda domains redirect to `*.news-pravda.com` subdomains (`pravda-de.com` ->
`deutsch.news-pravda.com`). Extract and retrieve keep the final URL, so outlets appear under the
new hosts; the list has `news-pravda.com` as a `domain` row, so every such subdomain matches.
For sites that move to a domain not listed yet, `sources.Profiler` also checks the submitted
URL's host.
"""

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path

from pipeline.extract.fetch import FetchFailed
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.web import Web

log = logging.getLogger(__name__)

NETWORK = "portal_kombat"
DEFAULT_PATH = Path("evals/data/viginum/portal_kombat_domains.csv")
SOURCE_URL = (
    "https://raw.githubusercontent.com/VIGINUM-FR/Rapports-Techniques/main/"
    "202402%20-%20Portal%20Kombat/20241227_SGDSN_VIGINUM_NP_TLP-CLEAR_Portal-Kombat-domains.csv"
)
SOURCE_MAX_AGE = timedelta(days=7)
SOURCE_MAX_BYTES = 1_000_000


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
        log.info("no VIGINUM file at %s: it will be downloaded", path)
        return Listing()
    result = parse(text)
    log.info("VIGINUM list: %d domains", len(result))
    return result


async def fetch_listing(web: Web, cache: Cache | NoCache) -> Listing:
    """The list from the cache or from VIGINUM's repository; empty when neither answers.

    A list that parses to nothing (a changed file layout, an error page) is not cached, so the
    next analysis tries again.
    """
    text = cache.get("viginum", SOURCE_URL, SOURCE_MAX_AGE)
    if text is not None:
        return parse(text)
    try:
        page = await web.get(SOURCE_URL, max_bytes=SOURCE_MAX_BYTES)
    except FetchFailed as e:
        log.warning("VIGINUM list download failed (%s): known_network stays empty", e.reason)
        return Listing()
    if page.status != 200 or page.truncated:
        log.warning("VIGINUM list download: HTTP %s; known_network stays empty", page.status)
        return Listing()
    text = page.body.decode("utf-8", errors="replace")
    result = parse(text)
    if len(result):
        cache.put("viginum", SOURCE_URL, text)
        log.info("VIGINUM list downloaded: %d domains", len(result))
    return result
