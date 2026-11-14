"""Family `source_profile`: what is known about the document's outlet (D9: no bias ratings).

- `domain_age_days`: days between the domain's registration (or, when unknown, its first
  certificate) and the article's publication date (or the analysis date). Value in days.
- `outlet_<type>`: the outlet type found by `retrieve` (`outlet_state_affiliated`,
  `outlet_partisan`, `outlet_wire_service`, ...). Value 1.0.
"""

from collections.abc import Callable
from datetime import datetime

from pipeline.common.contracts import Analysis, Evidence, Family, OutletType, UrlRef

_TYPE_WORDS = {
    OutletType.wire_service: "a news agency",
    OutletType.national: "a national outlet",
    OutletType.local: "a local outlet",
    OutletType.partisan: "a partisan outlet",
    OutletType.state_affiliated: "a state-affiliated outlet",
    OutletType.fact_checker: "a fact-checker",
}


def source_profile_evidence(analysis: Analysis, next_id: Callable[[], str]) -> list[Evidence]:
    outlet = analysis.document.outlet if analysis.document else None
    profile = next((s for s in analysis.sources if s.domain == outlet), None)
    if outlet is None or profile is None:
        return []
    evidence = []
    published = (analysis.document and analysis.document.published_at) or analysis.created_at
    born, ref = _birth(profile.registered_at, profile.first_cert_at, outlet)
    if born is not None and ref is not None:
        days = max((published - born).days, 0)
        how = "registered" if profile.registered_at else "first given a certificate"
        evidence.append(
            Evidence(
                id=next_id(),
                family=Family.source_profile,
                signal="domain_age_days",
                value=float(days),
                detail=f"The site's domain was {how} {_age(days)} before the article was "
                "published.",
                source_refs=[ref],
            )
        )
    if profile.outlet_type is not None:
        evidence.append(
            Evidence(
                id=next_id(),
                family=Family.source_profile,
                signal=f"outlet_{profile.outlet_type.value}",
                value=1.0,
                detail=f"{outlet} is {_TYPE_WORDS[profile.outlet_type]}.",
                source_refs=[UrlRef(kind="url", url=f"https://{outlet}")],
            )
        )
    return evidence


def _birth(
    registered: datetime | None, first_cert: datetime | None, domain: str
) -> tuple[datetime | None, UrlRef | None]:
    if registered is not None:
        return registered, UrlRef(kind="url", url=f"https://rdap.org/domain/{domain}")
    if first_cert is not None:
        return first_cert, UrlRef(kind="url", url=f"https://crt.sh/?q={domain}")
    return None, None


def _age(days: int) -> str:
    if days < 60:
        return f"{days} day{'s' if days != 1 else ''}"
    if days < 730:
        return f"{days // 30} months"
    return f"{days // 365} years"
