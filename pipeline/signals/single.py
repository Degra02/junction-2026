"""`run_single`: the single-actor evidence (plan §4 step 5a). Importing it loads the models.

Claim support runs cross-lingual NLI on CPU first and escalates only candidate contradictions
(`judge.verify_pairs`); `rhetoric` runs one multimodal call concurrently alongside CPU XLM-R."""

from concurrent.futures import ThreadPoolExecutor
from itertools import count

from pipeline.common import progress
from pipeline.common.contracts import Analysis, SignalsPatch
from pipeline.common.errors import StageError
from pipeline.signals import judge, models, rhetoric
from pipeline.signals.claims import claim_support_evidence, fact_check_evidence
from pipeline.signals.source_profile import source_profile_evidence
from pipeline.signals.techniques import (
    SentenceScores,
    charge,
    cited_paragraphs,
    technique_evidence,
    tone_evidence,
)
from pipeline.signals.text import (
    chunks,
    mask_quotations,
    own_words,
    sentence_spans,
    story_peers,
)

# CPU budget on 2 vCPU (D13): the technique model is XLM-R large.
MAX_PARAGRAPHS = 30
MAX_PEERS = 10
CHUNKS_PER_PEER_FOR_TONE = 3
# Sentences scored to point each technique at its words (cited paragraphs only).
MAX_SENTENCES = 24  # ~5-8 s on a laptop CPU for 20-28 sentences; the VPS has 2 vCPU


def run_single(analysis: Analysis) -> SignalsPatch:
    document = analysis.document
    if document is None:
        raise StageError("There is no text to analyse")
    if not any(p.strip() for p in document.paragraphs):
        raise StageError("There is no text to analyse")
    next_id = (f"s{n}" for n in count(1)).__next__
    indices = [
        i
        for i, p in enumerate(document.paragraphs)
        if p.strip() and not p.startswith(("[Visual context] ", "[Satire/humour meme] "))
    ][:MAX_PARAGRAPHS]
    peers = story_peers(analysis, MAX_PEERS)

    progress.report("Looking for persuasion techniques")
    with ThreadPoolExecutor(max_workers=1) as pool:
        rhetoric_future = (
            pool.submit(
                rhetoric.ask_rater,
                rhetoric.content_for_rater(document),
                rhetoric.image_for_rater(analysis),
            )
            if rhetoric.rhetoric_family() is not None
            and not any(p.startswith(rhetoric.SATIRE_MEME_PREFIX) for p in document.paragraphs)
            else None
        )
        evidence = []
        if indices:
            # Techniques and tone read what the texts say themselves, not what they quote.
            peer_chunks = [chunks(p.text)[:CHUNKS_PER_PEER_FOR_TONE] for p in peers]
            own = own_words(document.paragraphs)
            texts = [own[i] for i in indices] + [
                mask_quotations(c) for cs in peer_chunks for c in cs
            ]
            probabilities = models.technique_probabilities(texts)
            mine, theirs = probabilities[: len(indices)], probabilities[len(indices) :]

            cited = cited_paragraphs(
                indices, mine, models.TECHNIQUE_LABELS, models.TECHNIQUE_THRESHOLDS
            )
            evidence += technique_evidence(
                document.paragraphs,
                indices,
                mine,
                models.TECHNIQUE_LABELS,
                models.TECHNIQUE_THRESHOLDS,
                next_id,
                sentences=_sentence_scores(document.paragraphs, own, cited),
            )
            peer_charge, at = [], 0
            for cs in peer_chunks:
                peer_charge.append(
                    float(charge(theirs[at : at + len(cs)], models.TECHNIQUE_LABELS).mean())
                )
                at += len(cs)
            evidence += tone_evidence(
                document.paragraphs,
                indices,
                charge(mine, models.TECHNIQUE_LABELS),
                peers,
                peer_charge,
                next_id,
            )
        rhetoric_answer = rhetoric_future.result() if rhetoric_future is not None else None

    if rhetoric_future is not None:
        evidence += rhetoric.rhetoric_evidence(
            analysis, lambda _text, _img: rhetoric_answer, next_id
        )
    implied_claims = analysis.topic.implied_claims if analysis.topic else ()
    if indices and analysis.claims:
        progress.report(f"Checking {len(analysis.claims)} claims against {len(peers)} sources")
        evidence += claim_support_evidence(
            analysis.claims, peers, models.nli, next_id, cascade=judge.verify_pairs
        )
    if analysis.claims or implied_claims:
        evidence += fact_check_evidence(
            analysis.claims,
            analysis.context,
            models.nli,
            next_id,
            document.outlet,
            implied_claims=implied_claims,
        )
    evidence += source_profile_evidence(analysis, next_id)
    return SignalsPatch(evidence=evidence)


def _sentence_scores(paragraphs: list[str], own: list[str], cited: set[int]) -> SentenceScores:
    """Technique probabilities of each sentence of the cited paragraphs that have more than one,
    whole paragraphs only, at most MAX_SENTENCES in all. A sentence is read in the author's own
    words, like its paragraph."""
    where: list[tuple[int, tuple[int, int]]] = []
    texts: list[str] = []
    for index in sorted(cited):
        paragraph = paragraphs[index]
        spans = sentence_spans(paragraph)
        if len(spans) < 2 or len(where) + len(spans) > MAX_SENTENCES:
            continue
        masked = own[index] != paragraph
        for start, end in spans:
            where.append((index, (start, end)))
            text = paragraph[start:end]
            texts.append(mask_quotations(text) if masked else text)
    scores: SentenceScores = {}
    for (index, span), probabilities in zip(
        where, models.technique_probabilities(texts), strict=True
    ):
        scores.setdefault(index, []).append((span, probabilities))
    return scores
