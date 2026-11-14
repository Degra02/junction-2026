"""Jev-style System-One decision primitives: calibrated probabilities, conformal margin gating,
and selective cascade guardrails.

A System-One decision never generates free-form text: its output space is the question's type
(`ChoiceDecision` over a fixed label set, or `BinaryDecision` / `noul` in `[0, 1]`), carrying
calibrated probabilities, a certainty margin in `[0, 1]`, and an explicit `abstain` flag when
the input falls inside the uncertainty band ("Accept When Confident, Escalate When Unsure").

Compliance guard (`cascade_enabled`):
- Consumer OAuth tokens (`sk-ant-oat*`) are refused at runtime so personal subscription
  credentials can never be routed through automated backend decisions.
- Cascade outputs are transient runtime verifications only and are never persisted as training
  labels or used to distil/calibrate model weights (`score/fit.py` trains solely on third-party
  human labels: ClaimReview, EUvsDisinfo, VIGINUM).
"""

import logging
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

type Tier = Literal["system1", "cascade"]


@dataclass(frozen=True, slots=True)
class ChoiceDecision[L: str]:
    """A typed multiple-choice decision with calibrated probabilities summing to 1."""

    choice: L
    probabilities: dict[L, float]
    confidence: float
    abstain: bool
    tier: Tier = "system1"


@dataclass(frozen=True, slots=True)
class BinaryDecision:
    """A typed yes/no (`noul`) decision with calibrated P(yes) in `[0, 1]`."""

    noul: float
    confidence: float
    abstain: bool
    tier: Tier = "system1"

    @property
    def yes(self) -> bool:
        return self.noul >= 0.5


def calibrate_choice[L: str](
    probabilities: Mapping[L, float],
    *,
    temperature: float = 1.0,
    min_margin: float = 0.25,
    tier: Tier = "system1",
) -> ChoiceDecision[L]:
    """Temperature-scales `probabilities` onto the simplex and gates on top-1 vs top-2 margin."""
    if not probabilities:
        raise ValueError("probabilities must not be empty")
    temp = max(temperature, 1e-3)
    eps = 1e-12
    logits = {k: math.log(max(float(p), eps)) / temp for k, p in probabilities.items()}
    peak = max(logits.values())
    exps = {k: math.exp(v - peak) for k, v in logits.items()}
    total = sum(exps.values())
    scaled = {k: v / total for k, v in exps.items()}

    ranked = sorted(scaled.items(), key=lambda kv: kv[1], reverse=True)
    winner, top1 = ranked[0]
    top2 = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = max(0.0, min(1.0, top1 - top2))
    return ChoiceDecision(
        choice=winner,
        probabilities={k: round(v, 4) for k, v in scaled.items()},
        confidence=round(margin, 4),
        abstain=margin < min_margin,
        tier=tier,
    )


def calibrate_binary(
    score: float,
    *,
    threshold: float,
    grey_zone: tuple[float, float],
    scale: float = 0.03,
    tier: Tier = "system1",
) -> BinaryDecision:
    """Maps a continuous System-1 score (e.g. cosine similarity) to calibrated `noul` P(yes)."""
    z = max(-40.0, min(40.0, (score - threshold) / max(scale, 1e-4)))
    p_yes = 1.0 / (1.0 + math.exp(-z))
    low, high = grey_zone
    in_band = low <= score < high
    return BinaryDecision(
        noul=round(p_yes, 4),
        confidence=round(abs(2.0 * p_yes - 1.0), 4),
        abstain=in_band,
        tier=tier,
    )


def cascade_enabled() -> bool:
    """Whether uncertain System-1 decisions may escalate to the configured LLM endpoint.

    Returns False when `DECISION_CASCADE=0` or when a consumer OAuth token (`sk-ant-oat*`)
    is present in `LLM_API_KEY`.
    """
    flag = os.environ.get("DECISION_CASCADE", "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if api_key.startswith("sk-ant-oat"):
        log.warning("refusing consumer OAuth token in automated decision cascade (ToS guard)")
        return False
    return True
