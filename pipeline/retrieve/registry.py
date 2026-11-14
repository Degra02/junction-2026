"""The curated outlet list (`outlets.json`): type, country and feeds of known newsrooms.

Typing outlets is what keeps syndication from looking like coordination: the signals never count
a `wire_service`, `fact_checker`, `national` or `local` outlet as a copier, but an untyped one can
be. So every outlet we know is typed, and an outlet is left untyped only when we truly do not
know it; a type is never guessed.

Rules for the list:
- `wire_service`: news agencies whose copy other newsrooms republish (ANSA, Reuters, AFP...).
- `state_affiliated`: agencies and broadcasters under government editorial control (TASS, RIA,
  Xinhua, Sputnik, RT...). Descriptive, not a verdict. A mirror domain is listed only after
  opening it: it must serve the broadcaster's own edition (same pages, same analytics ID, the
  broadcaster named as the publisher), as RT's do (`rtrunews.com`, `rt-english.com`,
  `actualidad-rt.com`, `esrt.press`, `de-rt.com`). A site that only republishes its articles
  is not a mirror.
- `fact_checker`: organisations that publish fact-checks (IFCN signatories and similar).
- `national`: established mainstream newsrooms, including public-service broadcasters.
- No `partisan` entries: D9 rules out political-bias ratings.

A host matches the longest listed domain it ends with: `bologna.repubblica.it` is
`repubblica.it`, while `factcheck.afp.com` is the fact-checker and not the AFP wire.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pipeline.common.contracts import OutletType

DATA = Path(__file__).with_name("outlets.json")


@dataclass(frozen=True)
class Feed:
    url: str
    language: str  # ISO 639-1 code of the feed's items


@dataclass(frozen=True)
class Outlet:
    domain: str
    outlet_type: OutletType
    country: str | None  # ISO 3166-1 alpha-2; None when the outlet is not tied to one country
    feeds: tuple[Feed, ...] = ()


class Registry:
    def __init__(self, outlets: list[Outlet]):
        self._by_domain: dict[str, Outlet] = {}
        for outlet in outlets:
            if outlet.domain in self._by_domain:
                raise ValueError(f"outlet listed twice: {outlet.domain}")
            self._by_domain[outlet.domain] = outlet

    def __len__(self) -> int:
        return len(self._by_domain)

    def lookup(self, host: str | None) -> Outlet | None:
        """The listed outlet `host` belongs to (longest matching domain), or None."""
        if not host:
            return None
        labels = host.lower().rstrip(".").removeprefix("www.").split(".")
        for start in range(len(labels) - 1):
            outlet = self._by_domain.get(".".join(labels[start:]))
            if outlet is not None:
                return outlet
        return None

    def feeds(self) -> list[tuple[Outlet, Feed]]:
        return [(outlet, feed) for outlet in self._by_domain.values() for feed in outlet.feeds]


def parse(data: dict) -> Registry:
    outlets = []
    for type_name, entries in data.items():
        outlet_type = OutletType(type_name)
        for entry in entries:
            feeds = tuple(Feed(f["url"], f["language"]) for f in entry.get("feeds", []))
            outlets.append(Outlet(entry["domain"], outlet_type, entry.get("country"), feeds))
    return Registry(outlets)


@cache
def load_registry() -> Registry:
    return parse(json.loads(DATA.read_text(encoding="utf-8")))
