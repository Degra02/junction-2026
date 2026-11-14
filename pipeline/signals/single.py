"""`run_single`: the single-actor evidence (plan §4 step 5a). Importing it loads the models."""

from itertools import count

from pipeline.common import progress
from pipeline.common.contracts import Analysis, SignalsPatch
from pipeline.common.errors import StageError
from pipeline.signals import models
from pipeline.signals.claims import claim_support_evidence, fact_check_evidence
from pipeline.signals.source_profile import source_profile_evidence
from pipeline.signals.techniques import charge, technique_evidence, tone_evidence
from pipeline.signals.text import chunks, story_peers

# CPU budget on 2 vCPU (D13): the technique model is XLM-R large.
MAX_PARAGRAPHS = 30
MAX_PEERS = 10
CHUNKS_PER_PEER_FOR_TONE = 3


def run_single(analysis: Analysis) -> SignalsPatch:
    document = analysis.document
    if document is None:
        raise StageError("There is no text to analyse")
    indices = [i for i, p in enumerate(document.paragraphs) if p.strip()][:MAX_PARAGRAPHS]
    if not indices:
        raise StageError("There is no text to analyse")
    next_id = (f"s{n}" for n in count(1)).__next__
    peers = story_peers(analysis, MAX_PEERS)

    progress.report("Looking for persuasion techniques")
    peer_chunks = [chunks(p.text)[:CHUNKS_PER_PEER_FOR_TONE] for p in peers]
    texts = [document.paragraphs[i] for i in indices] + [c for cs in peer_chunks for c in cs]
    probabilities = models.technique_probabilities(texts)
    mine, theirs = probabilities[: len(indices)], probabilities[len(indices) :]

    evidence = technique_evidence(
        document.paragraphs,
        indices,
        mine,
        models.TECHNIQUE_LABELS,
        models.TECHNIQUE_THRESHOLDS,
        next_id,
    )
    peer_charge, at = [], 0
    for cs in peer_chunks:
        peer_charge.append(float(charge(theirs[at : at + len(cs)], models.TECHNIQUE_LABELS).mean()))
        at += len(cs)
    evidence += tone_evidence(
        document.paragraphs,
        indices,
        charge(mine, models.TECHNIQUE_LABELS),
        peers,
        peer_charge,
        next_id,
    )

    if analysis.claims:
        progress.report(f"Checking {len(analysis.claims)} claims against {len(peers)} sources")
    evidence += claim_support_evidence(analysis.claims, peers, models.nli, next_id)
    evidence += fact_check_evidence(analysis.claims, analysis.context, models.nli, next_id)
    evidence += source_profile_evidence(analysis, next_id)
    return SignalsPatch(evidence=evidence)
