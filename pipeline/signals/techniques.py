"""Families `techniques` and `tone`, from the persuasion model's per-paragraph probabilities.

Technique labels are noisy (micro-F1 ≈ 0.45 on the model card), so they are aggregated to the
six SemEval-2023 categories, one evidence item per category found.

- `techniques` / `<category>`: value = highest probability of a detected technique of the
  category, in `[0, 1]`.
- `tone` / `tone_vs_peers`: value = z-score of the document's emotional charge against the
  other reports of the same story (positive = more charged), clipped to `[-5, 5]`. Charge of a
  text = mean over its paragraphs of the strongest emotive technique probability.
"""

from collections.abc import Callable, Sequence

import numpy as np

from pipeline.common.contracts import ContextItem, Evidence, Family
from pipeline.signals.text import context_ref, paragraph_ref

CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "attack_on_reputation": (
        "Attacks people instead of arguing",
        [
            "Name_Calling-Labeling",
            "Guilt_by_Association",
            "Doubt",
            "Appeal_to_Hypocrisy",
            "Questioning_the_Reputation",
        ],
    ),
    "justification": (
        "Appeals to fear, values, authority or popularity instead of facts",
        [
            "Flag_Waving",
            "Appeal_to_Authority",
            "Appeal_to_Popularity",
            "Appeal_to_Values",
            "Appeal_to_Fear-Prejudice",
        ],
    ),
    "simplification": (
        "Oversimplifies causes and consequences or offers false choices",
        [
            "Causal_Oversimplification",
            "False_Dilemma-No_Choice",
            "Consequential_Oversimplification",
        ],
    ),
    "distraction": (
        "Distracts from the issue (straw man, red herring, whataboutism)",
        ["Straw_Man", "Red_Herring", "Whataboutism"],
    ),
    "call": (
        "Uses slogans or phrases that shut down discussion",
        ["Slogans", "Conversation_Killer", "Appeal_to_Time"],
    ),
    "manipulative_wording": (
        "Emotionally charged, exaggerated or vague wording",
        [
            "Loaded_Language",
            "Exaggeration-Minimisation",
            "Obfuscation-Vagueness-Confusion",
            "Repetition",
        ],
    ),
}
EMOTIVE = [
    "Loaded_Language",
    "Appeal_to_Fear-Prejudice",
    "Name_Calling-Labeling",
    "Exaggeration-Minimisation",
]
MIN_PEERS_FOR_TONE = 3
_MAX_REFS = 3


def technique_evidence(
    paragraphs: list[str],
    indices: list[int],
    probabilities: np.ndarray,
    labels: list[str],
    thresholds: np.ndarray,
    next_id: Callable[[], str],
) -> list[Evidence]:
    """One item per category with a detected technique; `probabilities[k]` belongs to
    `paragraphs[indices[k]]`."""
    detected = probabilities >= thresholds
    evidence = []
    for signal, (description, techniques) in CATEGORIES.items():
        columns = [labels.index(t) for t in techniques if t in labels]
        hits = np.where(detected[:, columns], probabilities[:, columns], 0.0)
        strongest = hits.max(axis=1) if columns else np.zeros(len(indices))
        rows = [k for k in np.argsort(-strongest) if strongest[k] > 0]
        if not rows:
            continue
        best = hits.max(axis=0)
        found = [labels[columns[c]] for c in np.argsort(-best) if best[c] > 0]
        names = ", ".join(t.replace("_", " ").replace("-", " / ").lower() for t in found)
        count = len(rows)
        evidence.append(
            Evidence(
                id=next_id(),
                family=Family.techniques,
                signal=signal,
                value=round(float(strongest[rows[0]]), 3),
                detail=f"{description} ({names}) in {count} paragraph{'s' if count > 1 else ''}.",
                source_refs=[paragraph_ref(paragraphs, indices[k]) for k in rows[:_MAX_REFS]],
            )
        )
    return evidence


def charge(probabilities: np.ndarray, labels: list[str]) -> np.ndarray:
    """Emotional charge of each row: its strongest emotive technique probability."""
    columns = [labels.index(t) for t in EMOTIVE if t in labels]
    if len(probabilities) == 0:
        return np.zeros(0)
    return probabilities[:, columns].max(axis=1)


def tone_evidence(
    paragraphs: list[str],
    indices: list[int],
    document_charge: np.ndarray,
    peers: Sequence[ContextItem],
    peer_charges: Sequence[float],
    next_id: Callable[[], str],
) -> list[Evidence]:
    """The document's charge against its peers'; nothing with fewer than
    MIN_PEERS_FOR_TONE peers."""
    if len(peers) < MIN_PEERS_FOR_TONE or len(document_charge) == 0:
        return []
    mine = float(document_charge.mean())
    others = np.asarray(peer_charges, dtype=float)
    # Floor the spread: near-identical peers would turn tiny differences into huge z-scores.
    z = (mine - others.mean()) / max(float(others.std()), 0.05)
    z = float(np.clip(z, -5.0, 5.0))
    calmer = int((others < mine).sum())
    n = len(others)
    if z >= 0:
        detail = f"More emotionally charged than {calmer} of {n} other reports on the same event."
    else:
        detail = (
            f"Less emotionally charged than {n - calmer} of {n} other reports on the same event."
        )
    hottest = indices[int(np.argmax(document_charge))]
    return [
        Evidence(
            id=next_id(),
            family=Family.tone,
            signal="tone_vs_peers",
            value=round(z, 2),
            detail=detail,
            source_refs=[paragraph_ref(paragraphs, hottest)]
            + [context_ref(p) for p in peers[:_MAX_REFS]],
        )
    ]
