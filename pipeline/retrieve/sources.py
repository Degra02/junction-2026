"""`sources[]`: one `SourceProfile` per outlet domain of the document and the context.

- `outlet_type`, `country`: the curated registry; left empty for outlets we do not know.
- `known_network`: `portal_kombat` when VIGINUM lists the domain.
- `registered_at`: RDAP (rdap.org redirects to the registry's server) for the registrable domain;
  VIGINUM's creation date when RDAP has none.
- `first_cert_at`: Certificate Transparency via crt.sh, best effort and only where domain age
  matters: the document's outlet and outlets we do not know. crt.sh is slow and often down, so a
  miss just leaves the field empty.
Lookups are cached per registrable domain; failures are not cached, so the next analysis retries.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from tld import get_fld

from pipeline.common.contracts import SourceProfile
from pipeline.extract.document import published_utc
from pipeline.extract.fetch import FetchFailed
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.registry import Registry
from pipeline.retrieve.viginum import NETWORK, Listing
from pipeline.retrieve.web import Web

log = logging.getLogger(__name__)

RDAP_URL = "https://rdap.org/domain/{}"
CRT_URL = "https://crt.sh/?q={}&output=json"
DOMAIN_MAX_AGE = timedelta(days=30)
RDAP_TIMEOUT_S = 10.0
CRT_TIMEOUT_S = 20.0
CRT_MAX_BYTES = 4_000_000


def registrable(host: str) -> str | None:
    """`bologna.repubblica.it` -> `repubblica.it`; None for hosts without a public suffix."""
    try:
        return get_fld(host, fix_protocol=True)
    except Exception:
        return None


def rdap_registration(body: bytes) -> datetime | None:
    try:
        events = json.loads(body).get("events") or []
    except ValueError, AttributeError:
        return None
    for event in events:
        if isinstance(event, dict) and event.get("eventAction") == "registration":
            return published_utc(event.get("eventDate"))
    return None


def first_certificate(body: bytes) -> datetime | None:
    try:
        certs = json.loads(body)
    except ValueError:
        return None
    dates = [
        d
        for c in certs
        if isinstance(c, dict) and (d := published_utc(c.get("not_before"))) is not None
    ]
    return min(dates, default=None)


class Profiler:
    def __init__(
        self,
        web: Web,
        cache: Cache | NoCache,
        registry: Registry,
        listing: Listing,
        *,
        redirected_from: dict[str, str] | None = None,
    ):
        """`redirected_from` maps a domain to the host it was reached from (the submitted URL's
        host when the page redirected elsewhere). Network sites move: since Nov 2026 the Pravda
        domains (`pravda-de.com`...) redirect to `*.news-pravda.com`. VIGINUM lists
        `news-pravda.com` too, but a listed site that moves to a domain not on the list yet is
        still caught through the address it was reached from."""
        self._web = web
        self._cache = cache
        self._registry = registry
        self._listing = listing
        self._redirected_from = redirected_from or {}

    async def _lookup(self, ns, url, domain, parse, timeout_s, max_bytes) -> datetime | None:
        cached = self._cache.get(ns, domain, DOMAIN_MAX_AGE)
        if cached is not None:
            return published_utc(cached.get("at"))
        try:
            async with asyncio.timeout(timeout_s):
                page = await self._web.get(url.format(domain), max_bytes=max_bytes)
        except FetchFailed, TimeoutError:
            return None
        if page.status == 404:
            # RDAP/crt.sh know nothing about it: a real answer, worth remembering.
            self._cache.put(ns, domain, {"at": None})
            return None
        if page.status != 200 or page.truncated:
            return None
        found = parse(page.body)
        self._cache.put(ns, domain, {"at": found.isoformat() if found else None})
        return found

    async def profile(self, domain: str, *, check_certificates: bool) -> SourceProfile:
        offline = self.offline_profile(domain)
        base = registrable(domain)
        if not base:
            return offline
        lookups = [
            self._lookup("rdap", RDAP_URL, base, rdap_registration, RDAP_TIMEOUT_S, 1_000_000)
        ]
        if check_certificates or offline.outlet_type is None:
            lookups.append(
                self._lookup(
                    "crtsh", CRT_URL, base, first_certificate, CRT_TIMEOUT_S, CRT_MAX_BYTES
                )
            )
        found = await asyncio.gather(*lookups)
        return offline.model_copy(
            update={
                # VIGINUM's creation date stays as the fallback when RDAP has none.
                "registered_at": found[0] or offline.registered_at,
                "first_cert_at": found[1] if len(found) > 1 else None,
            }
        )

    async def profiles(
        self, domains: list[str], document_outlet: str | None, timeout_s: float
    ) -> list[SourceProfile]:
        """Profiles for `domains` (unique, order kept); a lookup that runs out of time is left
        empty rather than dropping the profile, since type and network need no network."""
        unique = list(dict.fromkeys(d for d in domains if d))
        tasks = [
            asyncio.create_task(self.profile(d, check_certificates=d == document_outlet))
            for d in unique
        ]
        done, pending = await asyncio.wait(tasks, timeout=timeout_s) if tasks else (set(), set())
        for task in pending:
            task.cancel()
        result = []
        for domain, task in zip(unique, tasks, strict=True):
            if task in done and task.exception() is None:
                result.append(task.result())
            else:
                if task in done:
                    log.warning("profile of %s failed", domain, exc_info=task.exception())
                result.append(self.offline_profile(domain))
        return result

    def offline_profile(self, domain: str) -> SourceProfile:
        """What is known without the network: registry type and country, VIGINUM listing."""
        outlet = self._registry.lookup(domain)
        listed = self._listing.match(domain)
        # Only the network membership carries over from the original address; its creation
        # date belongs to that other domain, not to this one.
        via = self._listing.match(self._redirected_from.get(domain))
        return SourceProfile(
            domain=domain,
            registered_at=self._listing.created.get(listed) if listed else None,
            outlet_type=outlet.outlet_type if outlet else None,
            country=outlet.country if outlet else None,
            known_network=NETWORK if listed or via else None,
        )
