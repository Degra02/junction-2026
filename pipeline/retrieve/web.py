"""Shared HTTP access for the adapters: extract's safe fetcher plus a per-host limit.

Every request goes through `pipeline.extract.fetch.fetch_page`, so each redirect hop is checked
by `net.assert_public_url` (links in feeds and RDAP redirects come from third parties). At most
`PER_HOST` requests run against one host at a time, to stay polite and avoid rate limits.
"""

import asyncio
from collections import defaultdict
from collections.abc import Callable

import httpx

from pipeline.extract.fetch import MAX_BYTES, Page, fetch_page
from pipeline.extract.urls import outlet_host

PER_HOST = 2


class Web:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        guard: Callable[[str], None] | None = None,
        per_host: int = PER_HOST,
    ):
        self.client = client
        self._guard = guard
        self._slots: defaultdict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(per_host)
        )

    async def get(self, url: str, *, max_bytes: int = MAX_BYTES) -> Page:
        """GET `url`; raises `FetchFailed` (plain reason) when it cannot be read."""
        async with self._slots[outlet_host(url)]:
            return await fetch_page(url, self.client, guard=self._guard, max_bytes=max_bytes)
