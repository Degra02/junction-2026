"""From evidence to one number per family (plan §5): the combiner's input features.

Every signal is mapped to a *strength* in `[-1, 1]`: positive points toward propaganda,
negative away from it (a fact-checker rating the claim true, a news agency as the outlet),
0 is neutral. Inside a family only the strongest signal (largest |strength|) counts, so
correlated evidence is not double-counted. A family without evidence has value 0.

Signals not listed in STRENGTH are ignored (logged), so a new signal never breaks scoring
before it gets a mapping here.
"""

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pipeline.common.contracts import Evidence, Family

log = logging.getLogger(__name__)

SINGLE: tuple[Family, ...] = (
    Family.techniques,
    Family.rhetoric,
    Family.tone,
    Family.claim_support,
    Family.fact_checks,
    Family.source_profile,
)
INTRINSIC_SINGLE: frozenset[Family] = frozenset(
    {Family.techniques, Family.rhetoric, Family.source_profile}
)
COORDINATED: tuple[Family, ...] = (
    Family.text_reuse,
    Family.timing,
    Family.infrastructure,
    Family.known_networks,
)


def _saturating(scale: float) -> Callable[[float], float]:
    """Counts: 0 → 0, `scale` → 0.63, 3×`scale` → 0.95."""
    return lambda n: 1.0 - math.exp(-max(n, 0.0) / scale)


def _domain_age(days: float) -> float:
    """1.0 for a domain born the day of the article, ~0.66 at 15 days, ~0.28 at a year, 0 at
    ten years or more."""
    return min(max(1.0 - math.log10(max(days, 0.0) + 1.0) / math.log10(3650.0), 0.0), 1.0)


def _clip(
    low: float, high: float, scale: float = 1.0, offset: float = 0.0
) -> Callable[[float], float]:
    return lambda v: min(max(v * scale + offset, low), high)


# (family, signal) -> strength. Signal scales are documented in the signal modules.
STRENGTH: dict[tuple[Family, str], Callable[[float], float]] = {
    # techniques: share of paragraphs with a technique of the category; half of them saturates.
    **{
        (Family.techniques, category): _clip(0.0, 1.0, 2.0)
        for category in (
            "attack_on_reputation",
            "justification",
            "simplification",
            "distraction",
            "call",
            "manipulative_wording",
        )
    },
    # rhetoric (plans/persuasion-analysis.md): 1.0 clear, 0.5 weak.
    **{
        (Family.rhetoric, category): _clip(0.0, 1.0)
        for category in (
            "attack_on_reputation",
            "justification",
            "simplification",
            "distraction",
            "call",
            "manipulative_wording",
        )
    },
    # tone: z-score vs peers, z = 3 saturates. Calmer than the peers points away, but at most
    # -0.5: being calm is weaker evidence than being charged.
    (Family.tone, "tone_vs_peers"): _clip(-0.5, 1.0, 1 / 3),
    # claim_support: v = smoothed share of addressing sources that contradict the claim
    # (`signals.claims`). 2v - 1 maps "all contradict" toward 1, a split to 0, "all support"
    # toward -1, floored at -0.6 so corroboration alone never makes the result abstain on
    # disagreement (DISAGREEMENT = 0.7).
    (Family.claim_support, "contradicted"): _clip(-0.6, 1.0, 2.0, -1.0),
    # Nobody else reports the claim: common in honest original reporting, so weak.
    (Family.claim_support, "unaddressed"): lambda _: 0.2,
    # fact_checks: rating value (1 false, 0.6 misleading); a "true" rating points away.
    (Family.fact_checks, "rated_false"): _clip(0.0, 1.0),
    (Family.fact_checks, "rated_misleading"): _clip(0.0, 1.0),
    (Family.fact_checks, "rated_true"): lambda _: -1.0,
    # source_profile
    (Family.source_profile, "domain_age_days"): _domain_age,
    (Family.source_profile, "outlet_state_affiliated"): lambda _: 0.8,
    (Family.source_profile, "outlet_partisan"): lambda _: 0.6,
    (Family.source_profile, "outlet_local"): lambda _: 0.0,
    (Family.source_profile, "outlet_national"): lambda _: -0.2,
    (Family.source_profile, "outlet_wire_service"): lambda _: -0.5,
    (Family.source_profile, "outlet_fact_checker"): lambda _: -1.0,
    (Family.source_profile, "outlet_satire"): lambda _: -1.0,
    # coordinated: counts of sites.
    (Family.text_reuse, "copied_passages"): _saturating(2.0),
    (Family.timing, "copies_within_window"): _saturating(2.0),
    (Family.infrastructure, "shared_tracking_id"): _saturating(1.0),
    (Family.infrastructure, "young_copying_domains"): lambda n: 0.6 * _saturating(2.0)(n),
    (Family.known_networks, "listed_domain"): lambda n: 1.0 if n >= 1 else 0.0,
}


@dataclass(frozen=True)
class FamilyValue:
    family: Family
    # Strength of the strongest signal in [-1, 1]; 0 without evidence.
    value: float
    # Evidence of the family, strongest first; the first one gives the value.
    evidence_ids: list[str]


def strength(item: Evidence) -> float | None:
    """The item's strength in `[-1, 1]`, or None for a signal without a mapping."""
    mapping = STRENGTH.get((item.family, item.signal))
    if mapping is None:
        log.warning("no strength mapping for %s/%s; ignored", item.family.value, item.signal)
        return None
    return min(max(float(mapping(item.value)), -1.0), 1.0)


def family_values(evidence: Sequence[Evidence], families: Sequence[Family]) -> list[FamilyValue]:
    """One value per family of `families`, in that order."""
    scored: dict[Family, list[tuple[float, str]]] = {f: [] for f in families}
    for item in evidence:
        if item.family in scored and (s := strength(item)) is not None:
            scored[item.family].append((s, item.id))
    out = []
    for family in families:
        items = sorted(scored[family], key=lambda x: -abs(x[0]))
        out.append(
            FamilyValue(
                family=family,
                value=items[0][0] if items else 0.0,
                evidence_ids=[evidence_id for _, evidence_id in items],
            )
        )
    return out
