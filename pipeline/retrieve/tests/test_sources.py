"""Source profiles: which lookups run, what is cached, and what survives a timeout."""

import asyncio
import json
from datetime import timedelta

from pipeline.common.contracts import OutletType
from pipeline.retrieve import sources
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.registry import parse
from pipeline.retrieve.sources import Profiler
from pipeline.retrieve.viginum import parse as parse_viginum

REGISTRY = parse({"wire_service": [{"domain": "agency.it", "country": "IT"}]})
LISTING = parse_viginum("domain,create date,first seen,type\npravda-it[.]com,01/03/2024,,domain\n")
RDAP = "https://rdap.org/domain/{}"
CRT = "https://crt.sh/?q={}&output=json"


def registration(day: str) -> str:
    return json.dumps({"events": [{"eventAction": "registration", "eventDate": day}]})


def profiles(server, domains, document_outlet=None, cache=None, timeout_s=5.0):
    async def go():
        async with server.client() as client:
            from pipeline.retrieve.web import Web

            profiler = Profiler(
                Web(client, guard=lambda u: None), cache or NoCache(), REGISTRY, LISTING
            )
            return await profiler.profiles(domains, document_outlet, timeout_s)

    return asyncio.run(go())


def test_known_outlets_skip_crtsh_unknown_ones_and_the_document_do_not(server):
    server.pages[RDAP.format("agency.it")] = (200, registration("1999-01-01T00:00:00Z"))
    server.pages[RDAP.format("blog.it")] = (200, registration("2026-10-01T00:00:00Z"))
    server.pages[CRT.format("blog.it")] = (200, json.dumps([{"not_before": "2026-10-02T00:00:00"}]))
    agency, blog = profiles(server, ["agency.it", "news.blog.it"])
    assert CRT.format("agency.it") not in server.seen
    assert agency.outlet_type == OutletType.wire_service and agency.country == "IT"
    assert agency.registered_at.year == 1999 and agency.first_cert_at is None
    assert blog.domain == "news.blog.it" and blog.outlet_type is None
    assert blog.first_cert_at.isoformat() == "2026-10-02T00:00:00+00:00"

    server.seen.clear()
    profiles(server, ["agency.it"], document_outlet="agency.it")
    assert CRT.format("agency.it") in server.seen  # the document's outlet: domain age matters


def test_domains_are_deduplicated_and_empty_ones_dropped(server):
    result = profiles(server, ["", "agency.it", "agency.it", "www.agency.it"])
    assert [p.domain for p in result] == ["agency.it", "www.agency.it"]
    assert profiles(server, ["", ""]) == []


def test_viginum_date_is_the_fallback_when_rdap_has_none(server):
    [profile] = profiles(server, ["pravda-it.com"])  # RDAP and crt.sh answer 404
    assert profile.known_network == "portal_kombat"
    assert profile.registered_at.isoformat() == "2024-03-01T00:00:00+00:00"


def test_lookups_that_run_out_of_time_leave_an_offline_profile(server, monkeypatch):
    server.delays[RDAP.format("pravda-it.com")] = 5
    [profile] = profiles(server, ["pravda-it.com"], timeout_s=0.3)
    # Type, network and the VIGINUM date need no network, so they survive.
    assert profile.known_network == "portal_kombat"
    assert profile.registered_at.isoformat() == "2024-03-01T00:00:00+00:00"

    # A slow RDAP server alone costs its own short timeout, not the whole phase.
    monkeypatch.setattr(sources, "RDAP_TIMEOUT_S", 0.2)
    server.pages[RDAP.format("agency.it")] = (200, registration("1999-01-01T00:00:00Z"))
    server.delays[RDAP.format("agency.it")] = 5
    [profile] = profiles(server, ["agency.it"])
    assert profile.outlet_type == OutletType.wire_service and profile.registered_at is None


def test_answers_and_404s_are_cached_failures_are_not(server, tmp_path):
    cache = Cache(tmp_path / "r.sqlite")
    server.pages[RDAP.format("agency.it")] = (200, registration("1999-01-01T00:00:00Z"))
    server.pages[RDAP.format("down.it")] = (502, "")
    profiles(server, ["agency.it", "gone.it", "down.it"], cache=cache)
    month = timedelta(days=30)
    assert cache.get("rdap", "agency.it", month) == {"at": "1999-01-01T00:00:00+00:00"}
    assert cache.get("rdap", "gone.it", month) == {"at": None}
    assert cache.get("rdap", "down.it", month) is None

    server.seen.clear()
    [agency] = profiles(server, ["agency.it"], cache=cache)
    assert agency.registered_at.year == 1999 and server.seen == []


def test_a_cut_off_crtsh_answer_is_ignored(server, monkeypatch):
    monkeypatch.setattr(sources, "CRT_MAX_BYTES", 50)
    certs = [{"not_before": f"2026-10-{d:02d}T00:00:00"} for d in range(1, 29)]
    server.pages[CRT.format("blog.it")] = (200, json.dumps(certs))
    [profile] = profiles(server, ["blog.it"])
    assert profile.first_cert_at is None


def test_hosts_without_a_public_suffix_get_no_lookups(server):
    [profile] = profiles(server, ["intranet"])
    assert profile.domain == "intranet" and server.seen == []


def test_a_crashing_lookup_keeps_the_offline_profile(server, monkeypatch):
    async def broken(self, domain, *, check_certificates):
        raise RuntimeError("bug")

    monkeypatch.setattr(Profiler, "profile", broken)
    [profile] = profiles(server, ["agency.it"])
    assert profile.outlet_type == OutletType.wire_service
